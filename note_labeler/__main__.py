"""Run with no arguments for the window app, or give files for command-line use.

    python -m note_labeler                      # opens the app
    python -m note_labeler song.pdf             # -> "song (labeled).pdf"
    python -m note_labeler song.pdf --color rainbow --octaves
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import APP_NAME, __version__


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        from .gui import run_gui
        run_gui()
        return 0

    from .audiveris import AudiverisError, Cancelled
    from .pipeline import NoNotesFound, label_file
    from .render import COLORS, LabelOptions

    ap = argparse.ArgumentParser(prog="note-labeler", description=f"{APP_NAME}: write the letter "
                                 "name above every note of a piano score (PDF or image).")
    ap.add_argument("files", nargs="+", type=Path, help="PDF or image files (PNG/JPG/TIFF)")
    ap.add_argument("-o", "--out", type=Path, help="output folder (default: next to each input)")
    ap.add_argument("--color", default="black", choices=[*COLORS, "rainbow"],
                    help="label colour; 'rainbow' gives each letter its own colour")
    ap.add_argument("--size", type=float, default=1.0, help="label size, e.g. 0.8 or 1.3 (default 1.0)")
    ap.add_argument("--height", type=float, default=1.5,
                    help="gap between the staff and the labels, in staff spaces (default 1.5)")
    ap.add_argument("--octaves", action="store_true", help="add octave numbers (C4 = middle C)")
    ap.add_argument("--no-key", action="store_true", help="don't name the key-signature sharps/flats")
    ap.add_argument("--label-tied", action="store_true", help="also label the held half of tied notes")
    ap.add_argument("--musicxml", action="store_true", help="also save the recognised music as MusicXML")
    ap.add_argument("--no-cache", action="store_true", help="re-read the music even if seen before")
    ap.add_argument("--audiveris", help="path to the Audiveris program, if not found automatically")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    opts = LabelOptions(color=args.color, size=args.size, height=args.height, octave_numbers=args.octaves,
                        label_keys=not args.no_key, label_tied=args.label_tied)
    failures = 0
    for src in args.files:
        out = None
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            out = args.out / f"{src.stem} (labeled).pdf"
        last = [""]

        def progress(fraction: float, message: str) -> None:
            if message != last[0]:
                last[0] = message
                print(f"  [{fraction:4.0%}] {message}", flush=True)

        print(f"{src}:")
        try:
            result = label_file(src, out, opts, audiveris=args.audiveris, on_progress=progress,
                                use_cache=not args.no_cache, save_musicxml=args.musicxml)
        except (AudiverisError, NoNotesFound, ValueError, FileNotFoundError) as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            failures += 1
            continue
        except (Cancelled, KeyboardInterrupt):
            print("  Cancelled.", file=sys.stderr)
            return 130
        print(f"  Labelled {result.notes} notes on {result.pages} page(s) -> {result.output_pdf}")
        if result.keys:
            print(f"  Key: {', '.join(result.keys)}")
        for mxl in result.musicxml:
            print(f"  MusicXML -> {mxl}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
