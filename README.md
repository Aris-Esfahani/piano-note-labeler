# Piano Note Labeler

Writes the letter name (C, D, F#, Bb…) above every note of your piano sheet music,
so beginners can read any piece. It also names the sharps and flats of the key
signature (for example **F#** in G major).

Give it a PDF or a scan of the music and you get back **the same page**, with the
letters added in a neat row above each staff. Note labels never sit on the staff lines
and never touch fingering numbers or other printing. Each key-signature name sits
right on top of its own sharp or flat.

![Bach's Menuet in G with the note names written above each staff](docs/example.png)

- Works on printed sheet music: digital PDFs, and scans or photos (PNG, JPG, TIFF).
- Gets sharps and flats right: key signature, accidentals that last to the end of
  the bar, naturals, and notes tied over a barline.
- Chords are labelled as a stack, top note on top.
- Runs on your own computer. Nothing is uploaded.

## Install (Windows)

1. **Install Audiveris** (free). It's the program that reads the notes off the page.
   Download the `.msi` file for Windows from the
   [Audiveris releases page](https://github.com/Audiveris/audiveris/releases) and run it.
2. **Download `PianoNoteLabeler-Windows.exe`** from this project's
   [Releases](../../releases) page and double-click it. No other setup is needed.

The app finds Audiveris by itself. If it doesn't, click **Locate Audiveris…** and pick
`C:\Program Files\Audiveris\Audiveris.exe`.

**Keeping Audiveris inside this folder instead:** copy the whole Audiveris program
folder (`Audiveris.exe` together with its `app` and `runtime` folders) into a folder
named `Audiveris` here, next to `run_windows.bat` (or next to the downloaded `.exe`).
The app uses that copy first. Moving `Audiveris.exe` on its own doesn't work: it needs
the `app` and `runtime` folders beside it.

## Install (macOS / Linux), or run from the source code

1. Install Audiveris from its [releases page](https://github.com/Audiveris/audiveris/releases)
   (macOS `.dmg`, Ubuntu `.deb`).
2. Install [Python 3.10 or newer](https://www.python.org/downloads/).
   On Ubuntu/Debian also run `sudo apt install python3-venv python3-tk`.
3. Download this project (green **Code** button → **Download ZIP**) and unzip it.
4. Start it:
   - **Windows:** double-click `run_windows.bat`
   - **macOS / Linux:** run `./run_mac_linux.sh` in a terminal

   The first start takes about a minute while it installs its one library (PyMuPDF).

## How to use it

1. Click **Choose sheet music…** and pick a PDF or an image. You can pick several files.
2. Click **Label the notes**. Reading the music takes about 15–25 seconds per page.
3. Click **Open labeled PDF**. The result is saved next to your file as
   `<name> (labeled).pdf`. Your original file is never changed.

Options:

| Option | What it does |
| --- | --- |
| Label colour | Black (the default), blue, red, green, or **Rainbow**: each letter gets its own colour (C red, D orange, E yellow, F green, G blue, A indigo, B violet). |
| Size | How big the letters are. |
| Distance above the staff | How far above the staff the row of letters sits. |
| Name the key signature | Writes F#, Bb… right on top of each sharp or flat of the key signature. |
| Show octave numbers | `C4` instead of `C` (C4 is middle C). |
| Also label held notes | Labels the second note of a tie too. Off by default, because you don't play it again. |
| Also save a MusicXML file | Saves the recognised music, which you can open and fix in MuseScore. |

Changing options and labelling the same file again is instant: the app remembers
what it read.

### Getting good results

- **Digital PDFs work best**: ones made by notation software (MuseScore, Sibelius,
  LilyPond), like most of IMSLP's typeset scores and the Mutopia Project.
- **Scans:** 300 DPI, black and white, page straight. Phone photos work if they're
  sharp, flat and evenly lit.
- **Handwritten music doesn't work.**
- Note reading is good but not perfect. A smudge or an unusual symbol can give a
  wrong or missing letter. If a letter looks wrong, trust the printed note.

## Command line

```bash
python -m note_labeler song.pdf
```

```bash
python -m note_labeler song.pdf other.pdf --color rainbow --octaves --out labeled/
```

Run `python -m note_labeler --help` for every option. With no file names it opens the app.

## How it works

1. **Audiveris** reads the page image (optical music recognition) and saves a project
   file (`.omr`) listing every staff, clef, key signature, note head, accidental and
   tie, with its position on the page.
2. **`note_labeler/omr.py`** works out each note's name: its line or space on the staff
   and the clef give the letter. The key signature, any accidental earlier in the bar,
   or a tie from the previous bar decide the sharp or flat.
3. **`note_labeler/render.py`** writes the letters onto the original PDF with PyMuPDF.
   It looks at the printed page and puts each label on blank paper above its staff,
   clear of the staff lines, stems, beams, slurs, fingering numbers and text. Labels in a
   bar line up. Key-signature names go right on top of their own sharp or flat.

| File | Purpose |
| --- | --- |
| `note_labeler/gui.py` | The window app (Tkinter, built into Python) |
| `note_labeler/__main__.py` | Command line |
| `note_labeler/pipeline.py` | File in → labelled PDF out, with caching |
| `note_labeler/audiveris.py` | Finds and runs Audiveris |
| `note_labeler/omr.py` | Reads Audiveris's `.omr` file and names the notes |
| `note_labeler/music.py` | Clefs, key signatures, note spelling |
| `note_labeler/render.py` | Places and draws the labels |

## Development

```bash
python -m unittest discover -s tests -v
```

The tests use a public-domain score (Bach, Menuet in G, from the
[Mutopia Project](https://www.mutopiaproject.org)) and the `.omr` file Audiveris made
from it, so they run without Audiveris. One extra test runs Audiveris itself if it's
installed.

To build the stand-alone Windows app yourself, run `build_exe.bat` (it creates
`dist\PianoNoteLabeler.exe`). On GitHub, pushing a version tag such as `v1.0.0` builds
the Windows and macOS apps and attaches them to a Release (see
`.github/workflows/build.yml`).

## Credits

- [Audiveris](https://github.com/Audiveris/audiveris): optical music recognition (AGPL-3.0)
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF): reading and writing PDFs (AGPL-3.0)
- Sample score: J. S. Bach, Menuet in G, BWV Anh. 114, typeset by Allen Garvin for the
  Mutopia Project, public domain.
