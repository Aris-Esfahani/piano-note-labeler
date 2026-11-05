#!/bin/sh
# Start Piano Note Labeler. The first time, it sets itself up (needs Python 3.10+).
#   ./run_mac_linux.sh              opens the app
#   ./run_mac_linux.sh song.pdf     labels song.pdf without opening the app
cd "$(dirname "$0")" || exit 1

if [ ! -x .venv/bin/python ]; then
    echo "Setting up Piano Note Labeler for the first time (about a minute)..."
    if ! python3 -m venv .venv; then
        echo "Python 3.10 or newer is needed: https://www.python.org/downloads/"
        echo "(On Ubuntu/Debian: sudo apt install python3-venv python3-tk)"
        exit 1
    fi
    if ! .venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt; then
        echo "Could not install the PDF library. Check your internet connection and try again."
        rm -rf .venv
        exit 1
    fi
fi

exec .venv/bin/python -m note_labeler "$@"
