"""Find and run Audiveris, the free optical music recognition (OMR) program.

Audiveris reads the picture of the sheet music and works out where every
staff, clef, key signature and note head is. We only need the project file
(.omr) it saves; see omr.py for how we read it.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

DOWNLOAD_URL = "https://github.com/Audiveris/audiveris/releases"

# Audiveris skips small (grace / cue) notes unless asked; we want them labelled.
_SWITCHES = [
    "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.smallHeads=true",
    "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.smallBeams=true",
]
# Audiveris processing steps, in order (used for the progress bar).
STEPS = ["LOAD", "BINARY", "SCALE", "GRID", "HEADERS", "STEM_SEEDS", "BEAMS",
         "LEDGERS", "HEADS", "STEMS", "REDUCTION", "CUE_BEAMS", "TEXTS",
         "MEASURES", "CHORDS", "CURVES", "SYMBOLS", "LINKS", "RHYTHMS", "PAGE"]


class AudiverisError(RuntimeError):
    pass


def bundled_locations() -> list[Path]:
    """Where a copy of Audiveris kept with this app would be: a folder named
    "Audiveris" in the project folder, or next to PianoNoteLabeler.exe."""
    bases = [Path(__file__).resolve().parent.parent]           # running from the source code
    if getattr(sys, "frozen", False):                          # running as the built app
        app_dir = Path(sys.executable).resolve().parent
        bases += [app_dir, app_dir.parent]                     # next to it, or above dist\
    if sys.platform == "win32":
        inside = ["Audiveris.exe"]
    elif sys.platform == "darwin":
        inside = ["Audiveris.app/Contents/MacOS/Audiveris", "Contents/MacOS/Audiveris"]
    else:
        inside = ["bin/Audiveris", "bin/audiveris"]
    return [base / folder / name for base in bases for folder in ("Audiveris", "audiveris")
            for name in inside]


def _usable(path: Path) -> bool:
    """The Windows/Linux starter only works beside its 'app' folder."""
    if not path.is_file():
        return False
    if path.name.lower() == "audiveris.exe":
        return (path.parent / "app").is_dir()
    return True


def _candidates() -> list[str]:
    found: list[str] = []
    env = os.environ.get("AUDIVERIS")
    if env:
        found.append(env)
    found += [str(p) for p in bundled_locations()]
    for name in ("Audiveris", "audiveris"):
        exe = shutil.which(name)
        if exe:
            found.append(exe)
    if sys.platform == "win32":
        roots = [os.environ.get(v) for v in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)", "LOCALAPPDATA")]
        for root in filter(None, roots):
            found += sorted(glob.glob(os.path.join(root, "Audiveris*", "Audiveris.exe")), reverse=True)
            found += sorted(glob.glob(os.path.join(root, "Programs", "Audiveris*", "Audiveris.exe")), reverse=True)
    elif sys.platform == "darwin":
        for root in ("/Applications", os.path.expanduser("~/Applications")):
            found += glob.glob(os.path.join(root, "Audiveris*.app", "Contents", "MacOS", "Audiveris"))
    else:
        found += ["/opt/audiveris/bin/Audiveris", "/opt/audiveris/bin/audiveris",
                  "/usr/bin/audiveris", "/usr/local/bin/audiveris"]
    return found


def find_audiveris(preferred: str | None = None) -> list[str] | None:
    """Command (as a list) that launches Audiveris, or None if not installed."""
    if preferred:
        if Path(preferred).is_file():
            return [preferred]
        if preferred.startswith("flatpak"):
            return preferred.split()
    for path in _candidates():
        if path and _usable(Path(path)):
            return [path]
    if sys.platform.startswith("linux") and shutil.which("flatpak"):
        try:
            out = subprocess.run(["flatpak", "list", "--app", "--columns=application"],
                                 capture_output=True, text=True, timeout=10).stdout
            if "org.audiveris.audiveris" in out:
                return ["flatpak", "run", "org.audiveris.audiveris"]
        except (OSError, subprocess.SubprocessError):
            pass
    return None


class Progress:
    """Turns Audiveris log lines into a 0..1 progress value and a message."""

    def __init__(self):
        self.pages = 1
        self.page = 1
        self.step = 0

    def feed(self, line: str) -> tuple[float, str] | None:
        if m := re.search(r"\b(\d+) sheets? in", line):
            self.pages = max(1, int(m.group(1)))
        elif m := re.search(r"Loaded image #(\d+)", line):
            self.page = int(m.group(1))
            self.step = 0
        elif m := re.search(r"StepMonitoring\s+\d+\s+\|\s+([A-Z_]+)", line):
            if m.group(1) in STEPS:
                self.step = STEPS.index(m.group(1))
                done = (self.page - 1 + self.step / len(STEPS)) / self.pages
                return done, f"Reading page {self.page} of {self.pages}: {m.group(1).lower().replace('_', ' ')}"
        return None


class Cancelled(Exception):
    pass


class Job:
    """One Audiveris run. Call cancel() from another thread to stop it."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def run(self, command: list[str], source: Path, out_dir: Path,
            on_line: Callable[[str], None] | None = None,
            on_progress: Callable[[float, str], None] | None = None) -> Path:
        """Run Audiveris on a PDF/image; return the path of the .omr it saved."""
        out_dir.mkdir(parents=True, exist_ok=True)
        args = [*command, "-batch", *_SWITCHES, "-export", "-output", str(out_dir), "--", str(source)]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self._proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                          stdin=subprocess.DEVNULL, creationflags=flags)
        except OSError as exc:
            raise AudiverisError(f"Could not start Audiveris ({command[0]}): {exc}") from exc
        if self.cancelled:
            self.cancel()
        progress = Progress()
        tail: list[str] = []
        assert self._proc.stdout is not None
        for raw in self._proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            tail = (tail + [line])[-15:]
            if on_line:
                on_line(line)
            update = progress.feed(line)
            if update and on_progress:
                on_progress(*update)
        code = self._proc.wait()
        self._proc.stdout.close()
        if self.cancelled:
            raise Cancelled()
        omr = out_dir / f"{source.stem}.omr"
        if not omr.exists():
            found = sorted(out_dir.glob("*.omr"))
            if not found:
                detail = "\n".join(l for l in tail if l.strip())
                raise AudiverisError(f"Audiveris could not read this file (exit code {code}).\n{detail}")
            omr = found[0]
        return omr
