# Piano Note Labeler - writes the letter name above every note of sheet music.
# Copyright (C) 2026 Aris Esfahani
# Free software under the GNU Affero General Public License v3.0 or later;
# see the LICENSE file. Uses Audiveris (https://github.com/Audiveris/audiveris).
"""Make the all-in-one Windows download, PianoNoteLabeler-Windows.zip:

    PianoNoteLabeler/
        PianoNoteLabeler.exe   the app (build it first: build_exe.bat)
        Audiveris/             the note reader, ready to run - nothing to install
        READ ME.txt
        LICENSE.txt            this app's license (GNU AGPL 3.0)
        licenses/              credits, and where each program's source code is

People unzip it and double-click PianoNoteLabeler.exe. The app finds the
Audiveris folder sitting next to it by itself.

    python make_release_zip.py                       # uses .\Audiveris and dist\PianoNoteLabeler.exe
    python make_release_zip.py --audiveris D:\Audiveris --out my.zip
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOP = "PianoNoteLabeler"

READ_ME = """\
PIANO NOTE LABELER
==================
Writes the letter name (C, D, F#, Bb...) above every note of your piano sheet
music, and names the sharps and flats of the key signature.

HOW TO USE
1. Double-click PianoNoteLabeler.exe
2. Click "Choose sheet music..." and pick a PDF or a scan (PNG, JPG, TIFF).
3. Click "Label the notes". Reading the music takes about 15-25 seconds a page.
4. Click "Open labeled PDF". It is saved next to your file as
   "<name> (labeled).pdf". Your original file is never changed.

Nothing needs installing. Keep the Audiveris folder next to
PianoNoteLabeler.exe: it's the part that reads the notes off the page.
To remove the app, delete this folder.

If Windows shows "Windows protected your PC" the first time, click
"More info", then "Run anyway". (The app isn't signed with a paid
certificate, so Windows doesn't recognise it yet.)

TIPS
- Digital PDFs (from MuseScore, Sibelius, IMSLP typeset scores) work best.
- Scans: 300 DPI, straight, black on white. Handwritten music doesn't work.
- If a letter looks wrong, trust the printed note: reading isn't perfect.

CREDITS
The notes are read by Audiveris (https://github.com/Audiveris/audiveris),
free, open-source optical music recognition by Herve Bitteur and
contributors. It is included, unchanged, in the Audiveris folder.
PDFs are handled by PyMuPDF / MuPDF by Artifex.

LICENSE
Piano Note Labeler: Copyright (C) 2026 Aris Esfahani. Free software under
the GNU Affero General Public License, version 3 or later, with ABSOLUTELY
NO WARRANTY. Source code: https://github.com/Aris-Esfahani/piano-note-labeler
Audiveris and PyMuPDF are also under the GNU AGPL 3.0. The licenses folder
has the full license text and where to get each program's source code.
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Make the all-in-one Windows zip.")
    ap.add_argument("--audiveris", type=Path, default=ROOT / "Audiveris",
                    help="folder holding Audiveris.exe with its app and runtime folders")
    ap.add_argument("--exe", type=Path, default=ROOT / "dist" / "PianoNoteLabeler.exe")
    ap.add_argument("--out", type=Path, default=ROOT / "dist" / "PianoNoteLabeler-Windows.zip")
    args = ap.parse_args(argv)

    problems = []
    if not args.exe.is_file():
        problems.append(f"Missing {args.exe} - run build_exe.bat first.")
    for part in ("Audiveris.exe", "app", "runtime"):
        if not (args.audiveris / part).exists():
            problems.append(f"Missing {args.audiveris / part} - the Audiveris folder needs "
                            "Audiveris.exe together with its app and runtime folders.")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1

    files = [(args.exe, "PianoNoteLabeler.exe")]
    files += [(p, "Audiveris/" + p.relative_to(args.audiveris).as_posix())
              for p in sorted(args.audiveris.rglob("*")) if p.is_file()]
    files += [(ROOT / "LICENSE", "LICENSE.txt")]
    files += [(p, "licenses/" + p.name) for p in sorted((ROOT / "licenses").iterdir()) if p.is_file()]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    partial = args.out.with_name(args.out.name + ".part")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr(f"{TOP}/READ ME.txt", READ_ME.replace("\n", "\r\n"))
        for source, name in files:
            zf.write(source, f"{TOP}/{name}")
    partial.replace(args.out)
    size = args.out.stat().st_size / 1024 / 1024
    print(f"Built {args.out} ({size:.0f} MB, {len(files) + 1} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
