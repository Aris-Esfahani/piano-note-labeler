# Piano Note Labeler - writes the letter name above every note of sheet music.
# Copyright (C) 2026 Aris Esfahani
# Free software under the GNU Affero General Public License v3.0 or later;
# see the LICENSE file. Uses Audiveris (https://github.com/Audiveris/audiveris).
"""Entry point for the stand-alone app built by PyInstaller (see build_exe.bat)."""
import sys

from note_labeler.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
