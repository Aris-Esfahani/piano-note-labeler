# Piano Note Labeler - writes the letter name above every note of sheet music.
# Copyright (C) 2026 Aris Esfahani
# Free software under the GNU Affero General Public License v3.0 or later;
# see the LICENSE file. Uses Audiveris (https://github.com/Audiveris/audiveris).
"""Read an Audiveris project file (.omr) and work out every note's name.

An .omr file is a zip. Inside, ``book.xml`` lists the sheets (one per PDF
page) and ``sheet#N/sheet#N.xml`` holds everything Audiveris recognised on
that page: staves, clefs, key signatures, note heads, accidentals, ties...
each with its pixel position on the page image.

The result is a list of ``SheetMarks``: for each page, where each note head
and key-signature accidental is, and what it is called.
"""
from __future__ import annotations

import bisect
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import music
from .music import Clef


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


@dataclass
class NoteMark:
    """One recognised note head."""
    staff: int
    box: Box
    diatonic: int          # see music.py; already includes 8va/8vb lines
    alter: int             # -2..+2 semitones
    tied: bool = False     # held over from a tie (not played again)
    small: bool = False    # grace / cue note
    chord: str | None = None
    measure: str = ""      # which bar it is in (labels in a bar line up)

    def name(self, with_octave: bool = False) -> str:
        return music.spell(self.diatonic, self.alter, with_octave)


@dataclass
class KeyMark:
    """One sharp or flat of a key signature."""
    staff: int
    box: Box
    diatonic: int
    alter: int

    def name(self) -> str:
        return music.spell(self.diatonic, self.alter)


@dataclass
class Staff:
    id: int
    left: float
    right: float
    top_line: list[tuple[float, float]]     # (x, y) points of the top line
    bottom_line: list[tuple[float, float]]  # (x, y) points of the bottom line
    role: str = "top"                       # "top" or "bottom" staff of its part (piano: RH / LH)

    def top_at(self, x: float) -> float:
        return _interpolate(self.top_line, x)

    def bottom_at(self, x: float) -> float:
        return _interpolate(self.bottom_line, x)

    def lines_at(self, x: float) -> list[float]:
        """Heights of the five staff lines at x (they're evenly spaced)."""
        top, bottom = self.top_at(x), self.bottom_at(x)
        return [top + i * (bottom - top) / 4 for i in range(5)]


@dataclass
class SheetMarks:
    sheet_number: int        # Audiveris sheet number (1-based)
    page_index: int          # 0-based page in the input file
    width: int               # page image size in pixels
    height: int
    interline: float         # distance between staff lines, in pixels
    notes: list[NoteMark] = field(default_factory=list)
    keys: list[KeyMark] = field(default_factory=list)
    staves: dict[int, Staff] = field(default_factory=dict)
    key_fifths: list[int] = field(default_factory=list)  # keys found, in reading order


def _interpolate(points: list[tuple[float, float]], x: float) -> float:
    if not points:
        return 0.0
    if x <= points[0][0]:
        return points[0][1]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if x <= x2:
            t = 0 if x2 == x1 else (x - x1) / (x2 - x1)
            return y1 + t * (y2 - y1)
    return points[-1][1]


def _box(el: ET.Element) -> Box | None:
    b = el.find("bounds")
    if b is None:
        return None
    return Box(float(b.get("x")), float(b.get("y")), float(b.get("w")), float(b.get("h")))


def _ids(el: ET.Element | None) -> list[str]:
    return el.text.split() if el is not None and el.text else []


def _pos(el: ET.Element) -> int:
    return round(float(el.get("pitch", "0")))


# Note head shapes that have no pitch (drum/ghost notes) - not labelled.
_UNPITCHED = ("CROSS", "CIRCLE_X")
_OCTAVE_SIZES = {"OTTAVA": 1, "QUINDICESIMA": 2, "VENTIDUESIMA": 3}
# Audiveris often mistakes a stray "8" (e.g. in "1685") for an 8va sign.
# Those guesses come with a low confidence grade, so only trust sure ones.
# (8va only changes octave numbers, never the letter.)
_MIN_OCTAVE_GRADE = 0.8


class _SystemReader:
    """Works through one system (one line of music across all its staves)."""

    def __init__(self, system: ET.Element, carry_clefs: dict[int, Clef], name: str = ""):
        self.system = system
        self.name = name  # unique within the sheet, e.g. "1.3" = page 1, system 3
        self.carry_clefs = carry_clefs  # staff order -> clef at end of previous system
        self.inters: dict[str, ET.Element] = {}
        self.relations: list[tuple[str, str, ET.Element]] = []
        for sig in system.findall("sig"):
            for inters in sig.findall("inters"):
                for el in inters:
                    if el.get("id"):
                        self.inters[el.get("id")] = el
            for rels in sig.findall("relations"):
                for rel in rels:
                    if len(rel):
                        self.relations.append((rel.get("source"), rel.get("target"), rel[0]))

    def of_tag(self, tag: str) -> list[ET.Element]:
        return [el for el in self.inters.values() if el.tag == tag]

    def read(self, sheet: SheetMarks) -> None:
        # --- Staves, in top-to-bottom order, grouped by part ------------------
        staff_order: dict[int, int] = {}
        staff_part: dict[int, int] = {}
        five_line: set[int] = set()
        for p_idx, part in enumerate(self.system.findall("part")):
            part_staves = part.findall("staff")
            for s_idx, st in enumerate(part_staves):
                # In a piano part the last staff is the bottom (left-hand) one.
                role = "bottom" if len(part_staves) > 1 and s_idx == len(part_staves) - 1 else "top"
                sid = int(st.get("id"))
                staff_order[sid] = len(staff_order)
                staff_part[sid] = p_idx
                lines = st.find("lines")
                line_els = lines.findall("line") if lines is not None else []
                if len(line_els) == 5:
                    five_line.add(sid)
                pts = [[(float(p.get("x")), float(p.get("y"))) for p in ln.findall("point")]
                       for ln in line_els]
                if pts:
                    sheet.staves[sid] = Staff(sid, float(st.get("left", 0)), float(st.get("right", 0)),
                                              pts[0], pts[-1], role)

        # --- Clefs per staff (sorted by x) ---------------------------------
        clefs: dict[int, list[tuple[float, Clef]]] = {}
        for el in self.of_tag("clef"):
            box = _box(el)
            if box is None or el.get("staff") is None:
                continue
            clef = Clef(el.get("shape", "G_CLEF"), _pos(el))
            clefs.setdefault(int(el.get("staff")), []).append((box.x, clef))
        for lst in clefs.values():
            lst.sort(key=lambda t: t[0])

        def clef_at(staff: int, x: float) -> Clef:
            lst = clefs.get(staff, [])
            chosen = None
            for cx, clef in lst:
                if cx <= x:
                    chosen = clef
            if chosen is None and lst:
                chosen = lst[0][1]
            if chosen is None:
                chosen = self.carry_clefs.get(staff_order.get(staff, -1))
            if chosen is None:  # nothing recognised at all: guess piano layout
                chosen = music.BASS if staff_order.get(staff, 0) % 2 else music.TREBLE
            return chosen

        # --- Key signatures per staff ------------------------------------
        keys: dict[int, list[tuple[float, int]]] = {}
        for el in self.of_tag("key"):
            box = _box(el)
            if box is None or el.get("staff") is None:
                continue
            keys.setdefault(int(el.get("staff")), []).append((box.x, int(el.get("fifths", "0"))))
        for lst in keys.values():
            lst.sort(key=lambda t: t[0])
        # Piano staves share one key: if a staff's key went unrecognised,
        # borrow the key from another staff of the same part.
        for sid in staff_order:
            if sid not in keys:
                for other, lst in keys.items():
                    if staff_part.get(other) == staff_part[sid] and lst:
                        keys[sid] = [(-1.0, lst[0][1])]
                        break
        for sid in sorted(staff_order, key=staff_order.get):
            if keys.get(sid):
                sheet.key_fifths.append(keys[sid][0][1])
                break

        def fifths_at(staff: int, x: float) -> int:
            fifths = 0
            for kx, f in keys.get(staff, []):
                if kx <= x:
                    fifths = f
            return fifths

        # --- Measures: which measure each chord is in ----------------------
        chord_measure: dict[str, str] = {}
        for part in self.system.findall("part"):
            for m in part.findall("measure"):
                for cid in _ids(m.find("head-chords")):
                    chord_measure[cid] = m.get("id")
        stacks = sorted((float(s.get("left", 0)), s.get("id")) for s in self.system.findall("stack"))
        stack_lefts = [s[0] for s in stacks]

        def measure_by_x(x: float) -> str:
            i = bisect.bisect_right(stack_lefts, x) - 1
            return stacks[max(i, 0)][1] if stacks else "0"

        # --- Relations: chords, accidentals, ties --------------------------
        head_chord: dict[str, str] = {}
        head_alter: dict[str, int] = {}
        tie_from: dict[str, str] = {}   # right head -> left head
        ties: dict[str, dict[str, str]] = {}
        for src, dst, kind in self.relations:
            s_el, d_el = self.inters.get(src), self.inters.get(dst)
            if s_el is None or d_el is None:
                continue
            if kind.tag == "containment" and s_el.tag == "head-chord" and d_el.tag == "head":
                head_chord[dst] = src
            elif kind.tag == "alter-head" and d_el.tag == "head":
                alter = music.ALTER_SHAPES.get(s_el.get("shape", ""))
                if alter is not None:
                    head_alter[dst] = alter
            elif kind.tag == "slur-head" and s_el.get("tie") == "true":
                ties.setdefault(src, {})[kind.get("side", "")] = dst
        for ends in ties.values():
            if "RIGHT" in ends:
                tie_from[ends["RIGHT"]] = ends.get("LEFT", "")

        # --- 8va / 8vb lines -----------------------------------------------
        shifts: dict[int, list[tuple[float, float, int]]] = {}
        for el in self.of_tag("octave-shift"):
            if el.get("staff") is None or float(el.get("ctx-grade", el.get("grade", "0"))) < _MIN_OCTAVE_GRADE:
                continue
            size = _OCTAVE_SIZES.get(el.get("shape", ""), 1)
            sign = -1 if el.get("kind") == "BASSA" else 1
            xs = [float(p.get("x")) for p in el.iter() if p.tag in ("p1", "p2", "hook")]
            box = _box(el)
            if box is not None:
                xs += [box.x, box.right]
            if xs:
                shifts.setdefault(int(el.get("staff")), []).append((min(xs), max(xs), sign * size))

        def octave_shift(staff: int, x: float) -> int:
            return sum(s for x1, x2, s in shifts.get(staff, []) if x1 - 5 <= x <= x2 + 5)

        # --- Note heads, left to right on each staff -------------------------
        heads = []
        for el in self.of_tag("head"):
            hid, mirror = el.get("id"), el.get("mirror")
            if mirror and mirror in self.inters and int(mirror) < int(hid):
                continue  # same head drawn for two voices - keep one copy
            shape = el.get("shape", "")
            box = _box(el)
            if box is None or el.get("staff") is None or any(u in shape for u in _UNPITCHED):
                continue
            staff = int(el.get("staff"))
            if staff not in five_line:
                continue
            heads.append((staff, box.cx, hid, el, box))
        heads.sort(key=lambda h: (h[0], h[1]))

        measure_accidentals: dict[tuple[str, int, int], int] = {}
        resolved: dict[str, tuple[int, int]] = {}  # head id -> (diatonic, alter), without 8va
        for staff, x, hid, el, box in heads:
            clef = clef_at(staff, x)
            if clef.percussion:
                continue
            diatonic = clef.diatonic(_pos(el))
            chord = head_chord.get(hid)
            measure = chord_measure.get(chord) if chord else None
            if measure is None:
                measure = measure_by_x(x)
            state_key = (measure, staff, diatonic)
            tied = hid in tie_from
            left = resolved.get(tie_from.get(hid, ""))
            if hid in head_alter:
                alter = head_alter[hid]
                measure_accidentals[state_key] = alter
            elif tied and left and left[0] == diatonic:
                alter = left[1]  # a tie carries its accidental across the barline
            elif state_key in measure_accidentals:
                alter = measure_accidentals[state_key]
            else:
                alter = music.key_alters(fifths_at(staff, x)).get(music.step_of(diatonic), 0)
            resolved[hid] = (diatonic, alter)
            sheet.notes.append(NoteMark(
                staff=staff,
                box=box,
                diatonic=diatonic + 7 * octave_shift(staff, x),
                alter=alter,
                tied=tied,
                small=el.get("shape", "").endswith("_SMALL"),
                chord=chord,
                measure=f"{self.name}:{measure}",
            ))

        # --- Key-signature accidentals --------------------------------------
        for el in self.of_tag("key-alter"):
            alter = music.ALTER_SHAPES.get(el.get("shape", ""))
            box = _box(el)
            if not alter or box is None or el.get("staff") is None:
                continue  # skip naturals (key cancellations)
            staff = int(el.get("staff"))
            clef = clef_at(staff, box.cx)
            if clef.percussion:
                continue
            sheet.keys.append(KeyMark(staff, box, clef.diatonic(_pos(el)), alter))

        # Remember the last clef on each staff for the next system.
        for sid, order in staff_order.items():
            self.carry_clefs[order] = clef_at(sid, float("inf"))


def read_omr(omr_path: Path) -> list[SheetMarks]:
    """Parse an Audiveris .omr file into per-page note marks."""
    results: list[SheetMarks] = []
    with zipfile.ZipFile(omr_path) as zf:
        book = ET.fromstring(zf.read("book.xml"))
        names = set(zf.namelist())
        carry_clefs: dict[int, Clef] = {}
        for sheet_el in book.findall("sheet"):
            number = int(sheet_el.get("number"))
            if sheet_el.get("invalid") == "true":
                continue  # Audiveris found no music on this page
            inp = sheet_el.find("input/number")
            page_index = (int(inp.text) if inp is not None and inp.text else number) - 1
            entry = f"sheet#{number}/sheet#{number}.xml"
            if entry not in names:
                continue
            root = ET.fromstring(zf.read(entry))
            pic = root.find("picture")
            inter = root.find("scale/interline")
            sheet = SheetMarks(
                sheet_number=number,
                page_index=page_index,
                width=int(pic.get("width")),
                height=int(pic.get("height")),
                interline=float(inter.get("main")) if inter is not None else 20.0,
            )
            for page in root.findall("page"):
                for system in page.findall("system"):
                    name = f"{page.get('id', '')}.{system.get('id', '')}"
                    _SystemReader(system, carry_clefs, name).read(sheet)
            results.append(sheet)
    return results
