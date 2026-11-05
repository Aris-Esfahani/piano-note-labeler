# Piano Note Labeler - writes the letter name above every note of sheet music.
# Copyright (C) 2026 Aris Esfahani
# Free software under the GNU Affero General Public License v3.0 or later;
# see the LICENSE file. Uses Audiveris (https://github.com/Audiveris/audiveris).
"""The whole job: sheet music file in, labelled PDF out."""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import music
from .audiveris import DOWNLOAD_URL, AudiverisError, Job, find_audiveris
from .omr import read_omr
from .render import LabelOptions, image_to_pdf, write_labeled_pdf

IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
SUPPORTED = {".pdf", ".omr"} | IMAGE_TYPES
_CACHE_KEEP = 25
_CACHE_VERSION = "1"  # bump if Audiveris settings change


class NoNotesFound(RuntimeError):
    pass


@dataclass
class Result:
    output_pdf: Path
    notes: int
    pages: int
    keys: list[str] = field(default_factory=list)
    musicxml: list[Path] = field(default_factory=list)


def default_output(source: Path) -> Path:
    return source.with_name(f"{source.stem} (labeled).pdf")


def cache_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "NoteLabeler" / "cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "NoteLabeler"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "note-labeler"


def _file_hash(path: Path) -> str:
    h = hashlib.sha1(_CACHE_VERSION.encode())
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _prune_cache(root: Path) -> None:
    entries = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in entries[_CACHE_KEEP:]:
        shutil.rmtree(old, ignore_errors=True)


def _source_of_omr(omr: Path) -> Path:
    """Find the original PDF/image an .omr file was made from."""
    with zipfile.ZipFile(omr) as zf:
        book = ET.fromstring(zf.read("book.xml"))
    candidates = []
    if book.get("path"):
        recorded = Path(book.get("path"))
        candidates += [recorded, omr.with_name(recorded.name)]
    candidates += [omr.with_suffix(ext) for ext in [".pdf", *sorted(IMAGE_TYPES)]]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(f"Can't find the PDF or image that {omr.name} was made from. "
                            "Put it in the same folder with the same name.")


def _writable(path: Path) -> Path:
    """If the output is open in a PDF viewer (locked on Windows), pick a new name."""
    candidate, n = path, 2
    while True:
        try:
            if candidate.exists():
                with open(candidate, "ab"):
                    pass
            return candidate
        except PermissionError:
            candidate = path.with_name(f"{path.stem} {n}{path.suffix}")
            n += 1


def label_file(source: Path | str, output: Path | str | None = None,
               options: LabelOptions | None = None,
               audiveris: str | None = None,
               job: Job | None = None,
               on_progress: Callable[[float, str], None] | None = None,
               on_line: Callable[[str], None] | None = None,
               use_cache: bool = True,
               save_musicxml: bool = False) -> Result:
    """Label every note in `source` (PDF, image or .omr) and save a PDF."""
    source = Path(source)
    options = options or LabelOptions()
    ext = source.suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"Unsupported file type '{ext}'. Use a PDF or an image (PNG, JPG, TIFF).")
    if not source.is_file():
        raise FileNotFoundError(f"File not found: {source}")
    out_pdf = Path(output) if output else default_output(source)
    progress = on_progress or (lambda f, m: None)

    with tempfile.TemporaryDirectory(prefix="note-labeler-") as tmp_name:
        tmp = Path(tmp_name)
        mxl_files: list[Path] = []
        if ext == ".omr":
            omr = source
            picture = _source_of_omr(source)
        else:
            picture = source
            entry = cache_root() / _file_hash(source)
            omr = entry / "book.omr"
            if not (use_cache and omr.is_file()):
                command = find_audiveris(audiveris)
                if command is None:
                    raise AudiverisError("Audiveris is not installed (or could not be found). "
                                         f"Download it free from {DOWNLOAD_URL}")
                progress(0.0, "Starting Audiveris (the note reader)...")
                made = (job or Job()).run(command, source, tmp / "omr", on_line=on_line,
                                          on_progress=lambda f, m: progress(0.9 * f, m))
                entry.mkdir(parents=True, exist_ok=True)
                shutil.copy2(made, omr)
                for mxl in made.parent.glob("*.mxl"):
                    shutil.copy2(mxl, entry / mxl.name)
                _prune_cache(entry.parent)
            else:
                progress(0.5, "Using the notes read last time (cached)...")
                os.utime(entry)
            mxl_files = sorted(omr.parent.glob("*.mxl"))

        progress(0.92, "Working out note names...")
        sheets = read_omr(omr)
        notes = sum(len(s.notes) for s in sheets)
        if notes == 0:
            raise NoNotesFound("No notes were recognised. Is this sheet music? A clean scan "
                               "(300 DPI, straight, black on white) or a digital PDF works best.")

        progress(0.96, "Writing labels onto the PDF...")
        base_pdf = picture
        if picture.suffix.lower() in IMAGE_TYPES:
            base_pdf = tmp / "page.pdf"
            image_to_pdf(picture, base_pdf)
        out_pdf = _writable(out_pdf)
        labelled = write_labeled_pdf(base_pdf, sheets, out_pdf, options)

        saved_mxl: list[Path] = []
        if save_musicxml:  # Audiveris names these after the input, e.g. song.mxl
            for mxl in mxl_files:
                target = out_pdf.with_name(mxl.name)
                shutil.copy2(mxl, target)
                saved_mxl.append(target)

    keys = []
    for fifths in (f for s in sheets for f in s.key_fifths):
        name = music.key_name(fifths)
        if name not in keys:
            keys.append(name)
    progress(1.0, "Done")
    return Result(out_pdf, labelled, len(sheets), keys, saved_mxl)
