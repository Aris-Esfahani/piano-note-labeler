# Licenses and credits

**Piano Note Labeler** is Copyright (C) 2026 Aris Esfahani, free software under
the GNU Affero General Public License, version 3 or later, with no warranty.
Source code: https://github.com/Aris-Esfahani/piano-note-labeler

It is built on the free programs below. The full text of the GNU Affero General
Public License 3.0, which covers this app, Audiveris and PyMuPDF, is in
`AGPL-3.0.txt` in this folder (and in `LICENSE` in the source code).

## Audiveris (the note reader)

- Optical music recognition by Hervé Bitteur and contributors. Audiveris does
  all of the reading of the sheet music; Piano Note Labeler adds the letter
  names on top of what it finds.
- License: GNU AGPL 3.0.
- Source code: https://github.com/Audiveris/audiveris (version 5.11.0).
- The Windows download includes Audiveris, unchanged, in the `Audiveris` folder.
  Audiveris comes with its own Java runtime and libraries (including Tesseract
  OCR); their license files are inside that folder, for example under
  `Audiveris\runtime\legal`.

## PyMuPDF and MuPDF (reading and writing PDFs)

- By Artifex Software.
- License: GNU AGPL 3.0 (or a commercial license from Artifex).
- Source code: https://github.com/pymupdf/PyMuPDF
- Built into `PianoNoteLabeler.exe`.

## Python and Tkinter

- `PianoNoteLabeler.exe` contains the Python interpreter and its Tkinter window
  library (Tcl/Tk), packaged with PyInstaller.
- Python: Python Software Foundation License, https://www.python.org
- Tcl/Tk: BSD-style license, https://www.tcl.tk

## Sample score used in the tests

- J. S. Bach, Menuet in G, BWV Anh. 114, typeset by Allen Garvin for the
  Mutopia Project (https://www.mutopiaproject.org). Public domain.
