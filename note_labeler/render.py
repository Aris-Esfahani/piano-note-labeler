# Piano Note Labeler - writes the letter name above every note of sheet music.
# Copyright (C) 2026 Aris Esfahani
# Free software under the GNU Affero General Public License v3.0 or later;
# see the LICENSE file. Uses Audiveris (https://github.com/Audiveris/audiveris).
"""Write the note names onto the original PDF pages (PyMuPDF).

Every note label goes ABOVE its staff, on blank paper: the page is rendered
once as a small picture, and each label is moved until nothing printed (staff
lines, stems, beams, slurs, fingering numbers, text...) is under or next to it.
Key-signature names sit right on top of their own sharp or flat.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pymupdf

from .omr import NoteMark, SheetMarks

# One colour per letter, darkened so every colour reads well on white paper.
RAINBOW = {
    "C": (0.85, 0.10, 0.10),  # red
    "D": (0.90, 0.42, 0.00),  # orange
    "E": (0.70, 0.55, 0.00),  # dark yellow
    "F": (0.10, 0.55, 0.15),  # green
    "G": (0.05, 0.35, 0.85),  # blue
    "A": (0.35, 0.15, 0.70),  # indigo
    "B": (0.75, 0.10, 0.60),  # violet
}
COLORS = {
    "blue": (0.05, 0.30, 0.80),
    "red": (0.80, 0.05, 0.05),
    "black": (0.0, 0.0, 0.0),
    "green": (0.0, 0.50, 0.15),
}
WHITE = (1, 1, 1)
FONT = "hebo"  # Helvetica Bold, built into every PDF reader


@dataclass
class LabelOptions:
    color: str = "black"          # black / blue / red / green / rainbow
    size: float = 1.0             # 1.0 = a bit taller than one staff space
    octave_numbers: bool = False  # "C4" instead of "C"
    label_keys: bool = True       # name the sharps/flats of the key signature
    label_tied: bool = False      # also label the held half of a tie
    height: float = 1.5           # gap between staff and labels, in staff spaces


def _color(name: str, scheme: str) -> tuple[float, float, float]:
    if scheme == "rainbow":
        return RAINBOW.get(name[:1], COLORS["black"])
    return COLORS.get(scheme, COLORS["black"])


class _InkMap:
    """Which parts of the page already have printing on them. The page is
    rendered once (before any labels are added) as a small grey image."""

    ZOOM = 2.0                                  # 144 dpi is plenty
    _LIGHT = bytes(range(150, 256))             # paper-coloured pixel values

    def __init__(self, page: pymupdf.Page):
        pix = page.get_pixmap(matrix=pymupdf.Matrix(self.ZOOM, self.ZOOM),
                              colorspace=pymupdf.csGRAY, alpha=False)
        self.width, self.height, self.stride = pix.width, pix.height, pix.stride
        self.samples = pix.samples

    def ink(self, rect: pymupdf.Rect, skip_lines: tuple[float, ...] = (), line_half: float = 0.0) -> int:
        """Number of dark pixels inside rect (given in page points), not
        counting pixel rows within `line_half` of the heights in `skip_lines`
        (used to look past staff lines)."""
        z = self.ZOOM
        x0, x1 = max(0, int(rect.x0 * z)), min(self.width, int(rect.x1 * z) + 1)
        y0, y1 = max(0, int(rect.y0 * z)), min(self.height, int(rect.y1 * z) + 1)
        dark = 0
        for y in range(y0, y1):
            if skip_lines and any(abs((y + 0.5) / z - line) <= line_half for line in skip_lines):
                continue
            row = self.samples[y * self.stride + x0: y * self.stride + x1]
            dark += len(row.translate(None, self._LIGHT))
        return dark


@dataclass
class _Block:
    """One label, or a stack of labels for a chord (lowest note first)."""
    lines: list[tuple[str, float]]   # (text, font size)
    x: float                         # horizontal centre, in points
    spacing: float = 0.95            # line height, relative to font size

    @property
    def width(self) -> float:
        return max(pymupdf.get_text_length(t, fontname=FONT, fontsize=s) for t, s in self.lines)

    def rect(self, baseline: float) -> pymupdf.Rect:
        """Area covered when the bottom line of text sits on `baseline`."""
        bottom, top = self.lines[0][1], self.lines[-1][1]
        rise = sum(self.spacing * s for _, s in self.lines[1:])
        pad = 0.12 * bottom
        half = self.width / 2 + pad
        return pymupdf.Rect(self.x - half, baseline - rise - 0.74 * top - pad,
                            self.x + half, baseline + 0.05 * bottom + pad)

    def variants(self) -> list["_Block"]:
        """Ways to fit a chord where space is tight: as is, squeezed, one line."""
        if len(self.lines) == 1:
            return [self]
        squeezed = _Block([(t, 0.85 * s) for t, s in self.lines], self.x, spacing=0.85)
        one_line = _Block([(" ".join(t for t, _ in self.lines), 0.9 * self.lines[0][1])], self.x)
        return [self, squeezed, one_line]

    def shifted(self, dx: float) -> "_Block":
        return replace(self, x=self.x + dx) if dx else self


# A spot is (baseline, block). Candidates are tried cheapest first: moving a
# label up costs 1 per staff space, sliding it sideways costs 2 per space, so
# a label slides a little past its own stem before it climbs far.
_LIFT_STEPS = 30          # up to 6 staff spaces higher, in 0.2-space steps
_NEAR_LIFT = 10           # "close to its note": within 2 staff spaces
_SHIFT_STEPS = 4          # up to 0.8 staff space sideways (1.6 when squeezed)


def _candidates(shift_steps: int) -> list[tuple[int, int, int]]:
    return sorted(((lift + 2 * abs(shift), lift, shift)
                   for lift in range(_LIFT_STEPS + 1)
                   for shift in range(-shift_steps, shift_steps + 1)),
                  key=lambda c: (c[0], c[1], abs(c[2]), c[2] > 0))


_CANDIDATES = {False: _candidates(_SHIFT_STEPS), True: _candidates(2 * _SHIFT_STEPS)}


class _Placer:
    """Finds blank paper for every label, then draws it."""

    INK_TOLERANCE = 1  # one stray pixel (a scanner speck) is fine

    def __init__(self, page: pymupdf.Page, space: float):
        self.page = page
        self.ink = _InkMap(page)
        self.space = space
        self.step = 0.2 * space
        # Blank border kept between a label and anything printed, so labels
        # don't crowd fingering numbers and the like. In a tight spot (say,
        # between a fingering and a slur) a label may do without it, but it
        # still never touches anything printed.
        self.margin = 0.12 * space
        self.taken: list[pymupdf.Rect] = []

    def overlaps_label(self, rect: pymupdf.Rect) -> bool:
        return any(rect.intersects(t) for t in self.taken)

    def free(self, rect: pymupdf.Rect, check_labels: bool = True,
             skip_lines: tuple[float, ...] = (), tight: bool = False) -> bool:
        if rect.y0 < 0:
            return False
        if check_labels and self.overlaps_label(rect):
            return False
        m = 0.0 if tight else self.margin
        return self.ink.ink(rect + (-m, -m, m, m), skip_lines, 0.12 * self.space) <= self.INK_TOLERANCE

    def _spots(self, block: _Block, start: float, roof: float, max_lift: int = _LIFT_STEPS,
               wide: bool = False):
        for _, lift, shift in _CANDIDATES[wide]:
            if lift > max_lift:
                continue
            baseline = start - lift * self.step
            moved = block.shifted(shift * self.step)
            rect = moved.rect(baseline)
            if rect.y0 >= roof:
                yield baseline, moved, rect

    def search(self, block: _Block, start: float, roof: float, check_labels: bool = True,
               max_lift: int = _LIFT_STEPS, wide: bool = False,
               skip_lines: tuple[float, ...] = (), tight: bool = False) -> tuple[float, _Block] | None:
        """Nearest spot at or above `start` on blank paper, the top of the label
        staying below `roof`. `wide` lets it slide further sideways; `tight`
        drops the blank border."""
        for baseline, moved, rect in self._spots(block, start, roof, max_lift, wide):
            if self.free(rect, check_labels, skip_lines, tight):
                return baseline, moved
        return None

    def nearest(self, block: _Block, start: float, roof: float, check_labels: bool = True,
                max_lift: int = _LIFT_STEPS, wide: bool = False) -> tuple[float, _Block] | None:
        """Comfortable spot close by, else a tight one close by, else whatever
        is free further up. Keeps labels near their notes."""
        near = min(_NEAR_LIFT, max_lift)
        return (self.search(block, start, roof, check_labels, near, wide)
                or self.search(block, start, roof, check_labels, near, wide, tight=True)
                or self.search(block, start, roof, check_labels, max_lift, wide)
                or self.search(block, start, roof, check_labels, max_lift, wide, tight=True))

    def least_ink(self, block: _Block, start: float, roof: float) -> tuple[int, float, _Block]:
        """No blank paper anywhere nearby: the spot covering the least printing
        (never another label)."""
        best = None
        for baseline, moved, rect in self._spots(block, start, roof, wide=True):
            if rect.y0 < 0 or self.overlaps_label(rect):
                continue
            ink = self.ink.ink(rect)
            if best is None or ink < best[0]:
                best = (ink, baseline, moved)
                if ink <= self.INK_TOLERANCE:
                    break
        return best if best is not None else (10 ** 9, start, block)

    def draw(self, block: _Block, baseline: float, scheme: str, outline: bool = False) -> None:
        self.taken.append(block.rect(baseline))
        for text, size in block.lines:
            width = pymupdf.get_text_length(text, fontname=FONT, fontsize=size)
            point = (block.x - width / 2, baseline)
            if outline:
                # Thin white edge so letters stay readable where they cross a
                # staff line (only key-signature names sit on the staff).
                self.page.insert_text(point, text, fontsize=size, fontname=FONT,
                                      color=WHITE, render_mode=1, border_width=0.3)
            self.page.insert_text(point, text, fontsize=size, fontname=FONT,
                                  color=_color(text, scheme))
            baseline -= block.spacing * size


class _Geometry:
    """Converts Audiveris pixel positions to PDF points, staff by staff."""

    def __init__(self, page: pymupdf.Page, sheet: SheetMarks):
        self.sheet = sheet
        self.sx = page.rect.width / sheet.width
        self.sy = page.rect.height / sheet.height
        self.space = sheet.interline * self.sy            # one staff space, in points

    def staff_top(self, staff_id: int, x_px: float, fallback_px: float) -> float:
        staff = self.sheet.staves.get(staff_id)
        return (staff.top_at(x_px) if staff else fallback_px) * self.sy

    def roof(self, staff_id: int, x_px: float) -> float:
        """Labels must stay below this line: never on (or touching) the staff above."""
        staff = self.sheet.staves.get(staff_id)
        if staff is None:
            return 0.0
        top = staff.top_at(x_px)
        above = [s.bottom_at(x_px) for s in self.sheet.staves.values()
                 if s.id != staff_id and s.left - 50 <= x_px <= s.right + 50
                 and s.bottom_at(x_px) < top]
        return max(above) * self.sy + 0.5 * self.space if above else 0.0


def _group_columns(notes: list[NoteMark]) -> list[list[NoteMark]]:
    """Group note heads that sit on top of each other (chords, two voices)."""
    groups: list[list[NoteMark]] = []
    for note in sorted(notes, key=lambda n: (n.staff, n.box.cx)):
        last = groups[-1] if groups else None
        if last and last[0].staff == note.staff:
            left = min(n.box.x for n in last)
            right = max(n.box.right for n in last)
            overlap = min(right, note.box.right) - max(left, note.box.x)
            same_chord = note.chord is not None and any(n.chord == note.chord for n in last)
            if same_chord or overlap > 0.3 * note.box.w:
                last.append(note)
                continue
        groups.append([note])
    return groups


def _find_spot(placer: _Placer, plain: _Block, start: float, floor: float,
               roof: float) -> tuple[_Block, float]:
    """Pick the label's shape (stack, squeezed stack, one line) and height."""
    variants = plain.variants()
    # 1. Close to the note (at most 2 spaces above the normal height): blank
    #    paper with a comfortable border first, then a tight fit.
    for tight in (False, True):
        for block in variants:
            found = placer.search(block, start, roof, check_labels=False,
                                  max_lift=_NEAR_LIFT, tight=tight)
            if found is not None:
                return block, found[0]
    # 2. Tight spot (e.g. right under the staff above): come a bit closer.
    baseline = start + placer.step
    while baseline <= floor:
        for block in variants:
            if placer.search(block, baseline, roof, check_labels=False, max_lift=0, tight=True):
                return block, baseline
        baseline += placer.step
    # 3. Slide further sideways (e.g. past a rest sitting right above the note).
    for block in variants:
        found = placer.search(block, start, roof, check_labels=False, wide=True, tight=True)
        if found is not None:
            return block, found[0]
    # 4. Further up.
    for tight in (False, True):
        for block in variants:
            found = placer.search(block, start, roof, check_labels=False, tight=tight)
            if found is not None:
                return block, found[0]
    # 5. No blank paper at all: cover as little printing as possible.
    fits = [(placer.least_ink(v, floor, roof), v) for v in variants]
    (_, baseline, _), block = min(fits, key=lambda f: f[0][0])
    return block, baseline


def label_page(page: pymupdf.Page, sheet: SheetMarks, opts: LabelOptions) -> int:
    """Draw the labels for one page. Returns the number of notes labelled."""
    if page.rotation:
        page.remove_rotation()
    geo = _Geometry(page, sheet)
    space = geo.space
    base_size = max(5.0, 1.3 * space * opts.size)
    clearance = max(0.3, opts.height) * space     # blank gap under the labels
    placer = _Placer(page, space)

    if opts.label_keys:
        _label_key_signatures(placer, geo, opts, base_size * 0.75)

    notes = [n for n in sheet.notes if opts.label_tied or not n.tied]
    plans = []
    for column in _group_columns(notes):
        column.sort(key=lambda n: n.box.y)                      # top note first
        lines = [(n.name(opts.octave_numbers), base_size * (0.8 if n.small else 1.0))
                 for n in reversed(column)]                     # lowest note first
        x_px = sum(n.box.cx for n in column) / len(column)
        staff = column[0].staff
        staff_top = geo.staff_top(staff, x_px, column[0].box.y)
        head_top = column[0].box.y * geo.sy
        row = staff_top - clearance
        start = min(row, head_top - 0.6 * space)        # clear of notes above the staff too
        floor = min(staff_top, head_top) - 0.35 * space  # closest a label may come
        roof = geo.roof(staff, x_px)
        block, need = _find_spot(placer, _Block(lines, x_px * geo.sx), start, floor, roof)
        plans.append((column, block, row, start, roof, need))

    # Labels in the same bar line up, so they read like a line of text: each
    # label rises to the highest neighbour in its bar, but by no more than
    # 1.5 staff spaces (one tall ornament shouldn't lift the whole bar).
    by_bar: dict[tuple[int, str], list[float]] = {}
    for column, block, row, start, roof, need in plans:
        by_bar.setdefault((column[0].staff, column[0].measure), []).append(need)

    for column, block, row, start, roof, need in plans:
        bar = by_bar[(column[0].staff, column[0].measure)]
        target = min(n for n in bar if n >= need - 1.5 * space)
        spot = (placer.search(block, target, roof, max_lift=0)                # lined up
                or placer.search(block, target, roof, max_lift=0, tight=True)
                or placer.nearest(block, need, roof)                          # its own height
                or placer.search(block, need, roof, wide=True, tight=True)
                or placer.least_ink(block, need, roof)[1:])
        baseline, block = spot
        placer.draw(block, baseline, opts.color)
    return len(notes)


def _label_key_signatures(placer: _Placer, geo: _Geometry, opts: LabelOptions,
                          size: float) -> None:
    """Name each key-signature sharp/flat right on top of the sign itself.

    The signs are staggered up and down the staff, so the names follow them.
    A name may cross a staff line here (it gets a thin white edge), but it
    never touches the sign next to it or another name."""
    sheet = geo.sheet
    for key in sorted(sheet.keys, key=lambda k: (k.staff, k.box.x)):
        staff = sheet.staves.get(key.staff)
        lines = tuple(y * geo.sy for y in staff.lines_at(key.box.cx)) if staff else ()
        block = _Block([(key.name(), size)], key.box.cx * geo.sx)
        sign_top = key.box.y * geo.sy
        # Baseline that leaves the label (plus its blank border) just clear of the sign.
        start = sign_top - block.rect(0).y1 - placer.margin - 0.3
        roof = geo.roof(key.staff, key.box.cx)
        found = (placer.search(block, start, roof, max_lift=_NEAR_LIFT, skip_lines=lines)
                 or placer.search(block, start, roof, max_lift=_NEAR_LIFT, skip_lines=lines, tight=True))
        baseline, block = found if found is not None else (start, block)
        placer.draw(block, baseline, opts.color, outline=True)


def image_to_pdf(image: Path, pdf_out: Path) -> None:
    """Wrap a scanned image (PNG/JPG/TIFF) in a PDF."""
    img = pymupdf.open(image)
    converted = pymupdf.open("pdf", img.convert_to_pdf())
    out = pymupdf.open()
    for i, page in enumerate(converted):
        w, h = page.rect.width, page.rect.height
        # Images without a usable DPI come out huge (72 dpi). Treat them as a
        # full sheet of paper: scale to 8.5 inches wide.
        scale = 8.5 * 72 / w if w > 13 * 72 else 1.0
        new = out.new_page(width=w * scale, height=h * scale)
        new.show_pdf_page(new.rect, converted, i)
    out.save(pdf_out, garbage=3, deflate=True)


def write_labeled_pdf(source_pdf: Path, sheets: list[SheetMarks], out_pdf: Path,
                      opts: LabelOptions) -> int:
    """Copy source_pdf to out_pdf with labels on every recognised page."""
    doc = pymupdf.open(source_pdf)
    total = 0
    for sheet in sheets:
        if 0 <= sheet.page_index < doc.page_count:
            total += label_page(doc[sheet.page_index], sheet, opts)
    doc.save(out_pdf, garbage=3, deflate=True)
    doc.close()
    return total
