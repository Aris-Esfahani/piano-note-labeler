"""The window app (Tkinter - comes with Python, nothing extra to install)."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import traceback
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, __version__
from .audiveris import DOWNLOAD_URL, AudiverisError, Cancelled, Job, find_audiveris
from .pipeline import IMAGE_TYPES, NoNotesFound, label_file
from .render import LabelOptions

COLOR_CHOICES = {"Black": "black", "Blue": "blue", "Red": "red", "Green": "green",
                 "Rainbow (a colour per letter)": "rainbow"}
SIZE_CHOICES = {"Small": 0.8, "Medium": 1.0, "Large": 1.25, "Extra large": 1.5}
HEIGHT_CHOICES = {"Close": 0.8, "Normal": 1.5, "High": 2.5}  # staff spaces


def _settings_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "NoteLabeler" / "settings.json"


def _load_settings() -> dict:
    try:
        return json.loads(_settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_settings(data: dict) -> None:
    try:
        path = _settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def open_path(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - opens in the user's PDF viewer
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def show_in_folder(path: Path) -> None:
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = _load_settings()
        self.files: list[Path] = []
        self.results: list[Path] = []
        self.events: queue.Queue = queue.Queue()
        self.job: Job | None = None
        self.worker: threading.Thread | None = None

        root.title(APP_NAME)
        root.minsize(560, 0)
        self._build()
        self._refresh_audiveris()
        root.after(100, self._poll)
        root.protocol("WM_DELETE_WINDOW", self._close)

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        pad = {"padx": 14, "pady": 6}
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill="both", expand=True)

        title = ttk.Frame(frame)
        title.pack(fill="x", **pad)
        ttk.Label(title, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Label(title, text=f"v{__version__}", foreground="#999").pack(side="right", anchor="n")
        ttk.Label(frame, text="Writes the letter name (C, D, F#, Bb...) above every note of your\n"
                              "sheet music, and names the sharps and flats of the key signature.",
                  justify="left").pack(anchor="w", padx=14)

        pick = ttk.Frame(frame)
        pick.pack(fill="x", **pad)
        ttk.Button(pick, text="Choose sheet music...", command=self._choose).pack(side="left")
        self.file_label = ttk.Label(pick, text="PDF, PNG, JPG or TIFF", foreground="#666")
        self.file_label.pack(side="left", padx=10)

        opts = ttk.LabelFrame(frame, text="Options", padding=10)
        opts.pack(fill="x", **pad)
        row = ttk.Frame(opts)
        row.pack(fill="x")
        ttk.Label(row, text="Label colour:").pack(side="left")
        self.color = tk.StringVar(value=self.settings.get("color", "Black"))
        ttk.Combobox(row, textvariable=self.color, values=list(COLOR_CHOICES), state="readonly",
                     width=26).pack(side="left", padx=(6, 18))
        ttk.Label(row, text="Size:").pack(side="left")
        self.size = tk.StringVar(value=self.settings.get("size", "Medium"))
        ttk.Combobox(row, textvariable=self.size, values=list(SIZE_CHOICES), state="readonly",
                     width=11).pack(side="left", padx=6)
        row2 = ttk.Frame(opts)
        row2.pack(fill="x", pady=(6, 2))
        ttk.Label(row2, text="Distance above the staff:").pack(side="left")
        self.height = tk.StringVar(value=self.settings.get("height", "Normal"))
        ttk.Combobox(row2, textvariable=self.height, values=list(HEIGHT_CHOICES), state="readonly",
                     width=11).pack(side="left", padx=6)
        ttk.Label(row2, text="(labels never sit on the staff lines)", foreground="#666").pack(side="left")

        self.keys =tk.BooleanVar(value=self.settings.get("keys", True))
        self.octaves = tk.BooleanVar(value=self.settings.get("octaves", False))
        self.tied = tk.BooleanVar(value=self.settings.get("tied", False))
        self.mxl = tk.BooleanVar(value=self.settings.get("musicxml", False))
        for var, text in [(self.keys, "Name each sharp/flat of the key signature (F#, Bb...)"),
                          (self.octaves, "Show octave numbers (C4 = middle C)"),
                          (self.tied, "Also label held notes (the second half of a tie)"),
                          (self.mxl, "Also save a MusicXML file (opens in MuseScore)")]:
            ttk.Checkbutton(opts, text=text, variable=var).pack(anchor="w", pady=2)

        run = ttk.Frame(frame)
        run.pack(fill="x", **pad)
        self.go = ttk.Button(run, text="Label the notes", command=self._start)
        self.go.pack(side="left")
        self.cancel_btn = ttk.Button(run, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=8)

        self.bar = ttk.Progressbar(frame, maximum=1.0)
        self.bar.pack(fill="x", padx=14, pady=(2, 2))
        self.status = ttk.Label(frame, text="", wraplength=520, justify="left")
        self.status.pack(anchor="w", padx=14, pady=(0, 4))

        done = ttk.Frame(frame)
        done.pack(fill="x", padx=14)
        self.open_btn = ttk.Button(done, text="Open labeled PDF", state="disabled",
                                   command=lambda: self.results and open_path(self.results[-1]))
        self.open_btn.pack(side="left")
        self.folder_btn = ttk.Button(done, text="Show in folder", state="disabled",
                                     command=lambda: self.results and show_in_folder(self.results[-1]))
        self.folder_btn.pack(side="left", padx=8)

        reader = ttk.LabelFrame(frame, text="Note reader (Audiveris)", padding=8)
        reader.pack(fill="x", **pad)
        self.reader_label = ttk.Label(reader, text="", wraplength=500, justify="left")
        self.reader_label.pack(anchor="w")
        btns = ttk.Frame(reader)
        btns.pack(anchor="w", pady=(4, 0))
        self.download_btn = ttk.Button(btns, text="Download Audiveris",
                                       command=lambda: webbrowser.open(DOWNLOAD_URL))
        self.download_btn.pack(side="left", padx=(0, 8))
        self.locate_btn = ttk.Button(btns, text="Locate Audiveris...", command=self._locate)
        self.locate_btn.pack(side="left", padx=(0, 8))
        self.check_btn = ttk.Button(btns, text="Check again", command=self._refresh_audiveris)
        self.check_btn.pack(side="left")

        self.show_log = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Show details", variable=self.show_log,
                        command=self._toggle_log).pack(anchor="w", padx=14)
        self.log = tk.Text(frame, height=10, width=80, font=("Consolas", 8), state="disabled")

    # --------------------------------------------------------------- actions
    def _refresh_audiveris(self) -> None:
        cmd = find_audiveris(self.settings.get("audiveris"))
        self.audiveris_cmd = cmd
        if cmd:
            self.reader_label.configure(text=f"Ready: {' '.join(cmd)}", foreground="#1a7f37")
            self.download_btn.pack_forget()
            self.check_btn.pack_forget()
        else:
            self.download_btn.pack(side="left", padx=(0, 8), before=self.locate_btn)
            self.check_btn.pack(side="left")
            self.reader_label.configure(
                text="Not found. Audiveris is the free program that reads the notes from your PDF. "
                     "Install it (Windows: the .msi file), then click 'Check again'.",
                foreground="#b42318")

    def _locate(self) -> None:
        types = [("Audiveris", "Audiveris.exe" if sys.platform == "win32" else "*"), ("All files", "*")]
        path = filedialog.askopenfilename(title="Find the Audiveris program", filetypes=types)
        if path:
            self.settings["audiveris"] = path
            _save_settings(self.settings)
            self._refresh_audiveris()

    def _choose(self) -> None:
        exts = " ".join(f"*{e}" for e in [".pdf", *sorted(IMAGE_TYPES)])
        paths = filedialog.askopenfilenames(
            title="Choose sheet music", initialdir=self.settings.get("last_dir") or str(Path.home()),
            filetypes=[("Sheet music", exts), ("PDF", "*.pdf"), ("All files", "*")])
        if not paths:
            return
        self.files = [Path(p) for p in paths]
        self.settings["last_dir"] = str(self.files[0].parent)
        names = ", ".join(p.name for p in self.files)
        self.file_label.configure(text=names if len(names) < 60 else f"{len(self.files)} files",
                                  foreground="#000")
        self._set_status("")

    def _options(self) -> LabelOptions:
        return LabelOptions(color=COLOR_CHOICES.get(self.color.get(), "black"),
                            size=SIZE_CHOICES.get(self.size.get(), 1.0),
                            height=HEIGHT_CHOICES.get(self.height.get(), 1.5),
                            octave_numbers=self.octaves.get(), label_keys=self.keys.get(),
                            label_tied=self.tied.get())

    def _start(self) -> None:
        if not self.files:
            self._choose()
            if not self.files:
                return
        self.settings.update(color=self.color.get(), size=self.size.get(), height=self.height.get(),
                             keys=self.keys.get(),
                             octaves=self.octaves.get(), tied=self.tied.get(), musicxml=self.mxl.get())
        _save_settings(self.settings)
        self.results = []
        self.go.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.open_btn.configure(state="disabled")
        self.folder_btn.configure(state="disabled")
        self.bar.configure(value=0)
        self.job = Job()
        args = (list(self.files), self._options(), self.mxl.get(), self.job)
        self.worker = threading.Thread(target=self._work, args=args, daemon=True)
        self.worker.start()

    def _cancel(self) -> None:
        if self.job:
            self.job.cancel()
            self._set_status("Cancelling...")

    def _work(self, files: list[Path], opts: LabelOptions, mxl: bool, job: Job) -> None:
        put = self.events.put
        summary = []
        for i, src in enumerate(files):
            def progress(fraction: float, message: str, i=i, src=src) -> None:
                prefix = f"{src.name}: " if len(files) > 1 else ""
                put(("progress", (i + fraction) / len(files), prefix + message))
            try:
                result = label_file(src, None, opts, audiveris=self.settings.get("audiveris"), job=job,
                                    on_progress=progress, on_line=lambda l: put(("log", l)),
                                    save_musicxml=mxl)
            except Cancelled:
                put(("finished", "Cancelled.", False))
                return
            except (AudiverisError, NoNotesFound, ValueError, FileNotFoundError) as exc:
                put(("log", str(exc)))
                summary.append(f"✗ {src.name}: {exc}")
                continue
            except Exception as exc:  # show anything unexpected instead of crashing
                put(("log", traceback.format_exc()))
                summary.append(f"✗ {src.name}: unexpected error ({exc}). Tick 'Show details' for more.")
                continue
            put(("result", result.output_pdf))
            key = f" Key: {', '.join(result.keys)}." if result.keys else ""
            summary.append(f"✓ Labelled {result.notes} notes on {result.pages} page(s) -> "
                           f"{result.output_pdf.name}.{key}")
        put(("finished", "\n".join(summary), True))

    # ----------------------------------------------------------- event loop
    def _poll(self) -> None:
        try:
            while True:
                kind, *data = self.events.get_nowait()
                if kind == "progress":
                    self.bar.configure(value=data[0])
                    self._set_status(data[1])
                elif kind == "log":
                    self._append_log(data[0])
                elif kind == "result":
                    self.results.append(data[0])
                elif kind == "finished":
                    self._finished(*data)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _finished(self, message: str, ok: bool) -> None:
        self.go.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.job = None
        if self.results:
            self.bar.configure(value=1.0)
            self.open_btn.configure(state="normal")
            self.folder_btn.configure(state="normal")
        else:
            self.bar.configure(value=0)
        failed = "✗" in message
        self._set_status(message, "#b42318" if failed and not self.results else None)
        if failed and "not installed" in message:
            self._refresh_audiveris()

    def _set_status(self, text: str, color: str | None = None) -> None:
        self.status.configure(text=text, foreground=color or "")

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _toggle_log(self) -> None:
        if self.show_log.get():
            self.log.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        else:
            self.log.pack_forget()

    def _close(self) -> None:
        if self.job and self.worker and self.worker.is_alive():
            if not messagebox.askyesno(APP_NAME, "Still working. Stop and quit?"):
                return
            self.job.cancel()
        self.root.destroy()


def run_gui() -> None:
    if sys.platform == "win32":
        try:  # sharp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()
