"""Entry point for the stand-alone app built by PyInstaller (see build_exe.bat)."""
import sys

from note_labeler.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
