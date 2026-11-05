"""Tests on a real score: Bach's Menuet in G (BWV Anh. 114), public domain,
from the Mutopia Project. `minuet_in_g.omr` is what Audiveris made of
`minuet_in_g.pdf`, so these tests don't need Audiveris installed."""
import re
import tempfile
import unittest
from pathlib import Path

import pymupdf

from note_labeler.__main__ import main
from note_labeler.audiveris import find_audiveris
from note_labeler.omr import read_omr
from note_labeler.pipeline import label_file
from note_labeler.render import LabelOptions, write_labeled_pdf

FIXTURES = Path(__file__).parent / "fixtures"
PDF = FIXTURES / "minuet_in_g.pdf"
OMR = FIXTURES / "minuet_in_g.omr"
NOTE_NAME = re.compile(r"^[A-G](#|##|b|bb)?\d?$")


def labels_on(page: pymupdf.Page) -> list[tuple[str, pymupdf.Rect]]:
    """The note-name labels written on a page, one per word. Labels are the
    only Helvetica-Bold text on the test score. (Text extraction can merge
    neighbouring labels into one run, so take the words inside those runs.)"""
    runs = [pymupdf.Rect(span["bbox"]) + (-0.5, -0.5, 0.5, 0.5)
            for block in page.get_text("dict")["blocks"]
            for line in block.get("lines", [])
            for span in line["spans"] if span["font"] == "Helvetica-Bold"]
    found, seen = [], set()
    for x0, y0, x1, y1, word, *_ in page.get_text("words"):
        rect = pymupdf.Rect(x0, y0, x1, y1)
        key = (word, round(x0, 1), round(y0, 1))
        # Each label is drawn twice (white outline, then colour): count it once.
        if key in seen or not NOTE_NAME.match(word):
            continue
        center = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)
        if any(center in run for run in runs):
            seen.add(key)
            found.append((word, rect))
    return found


class ReadOmrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sheet = read_omr(OMR)[0]

    def notes(self, staff):
        return sorted((n for n in self.sheet.notes if n.staff == staff), key=lambda n: n.box.cx)

    def test_key_is_g_major(self):
        self.assertEqual(self.sheet.key_fifths[0], 1)
        self.assertTrue(self.sheet.keys)
        self.assertTrue(all(k.name() == "F#" for k in self.sheet.keys))

    def test_opening_melody(self):
        names = [n.name() for n in self.notes(1)[:13]]
        self.assertEqual(names, ["D", "G", "A", "B", "C", "D", "G", "G", "E", "C", "D", "E", "F#"])

    def test_key_signature_applies_to_every_f(self):
        fs = [n for n in self.sheet.notes if n.name().startswith("F")]
        self.assertTrue(fs)
        self.assertTrue(all(n.name() == "F#" for n in fs))

    def test_accidentals_in_middle_section(self):
        names = {n.name() for n in self.sheet.notes}
        self.assertIn("C#", names)   # bars 19-21 have C sharps
        self.assertIn("C", names)    # ...and the natural sign brings C back

    def test_grace_note_found(self):
        self.assertTrue(any(n.small for n in self.sheet.notes))

    def test_false_ottava_ignored(self):
        # Audiveris reads the "8" in "(1685-1750)" as an 8va sign; we must not.
        self.assertEqual([n.name(True) for n in self.notes(1)[16:21]], ["C5", "D5", "C5", "B4", "A4"])


def _spans(page: pymupdf.Page) -> list[dict]:
    return [span for block in page.get_text("dict")["blocks"]
            for line in block.get("lines", []) for span in line["spans"]
            if span["font"] == "Helvetica-Bold"]


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.sheet = read_omr(OMR)[0]
        out = Path(cls.tmp.name) / "labeled.pdf"
        cls.count = write_labeled_pdf(PDF, [cls.sheet], out, LabelOptions())
        cls.page = pymupdf.open(out)[0]
        cls.labels = labels_on(cls.page)
        # The same, without key-signature names: just the note labels.
        out = Path(cls.tmp.name) / "notes_only.pdf"
        write_labeled_pdf(PDF, [cls.sheet], out, LabelOptions(label_keys=False))
        cls.notes_page = pymupdf.open(out)[0]
        cls.note_labels = labels_on(cls.notes_page)
        cls.sx = cls.page.rect.width / cls.sheet.width
        cls.sy = cls.page.rect.height / cls.sheet.height
        cls.space = cls.sheet.interline * cls.sy

    @classmethod
    def tearDownClass(cls):
        cls.page.parent.close()
        cls.notes_page.parent.close()
        cls.tmp.cleanup()

    def test_every_note_and_key_labelled(self):
        self.assertEqual(self.count, len(self.sheet.notes))
        words = sum(len(text.split()) for text, _ in self.labels)
        self.assertGreaterEqual(words, len(self.sheet.notes) + len(self.sheet.keys))

    def test_labels_are_black_by_default(self):
        colours = {span["color"] for span in _spans(self.page)} - {0xFFFFFF}
        self.assertEqual(colours, {0x000000})

    def test_note_labels_never_touch_the_staff_lines(self):
        staves = [pymupdf.Rect(s.left * self.sx, s.top_at(s.left) * self.sy,
                               s.right * self.sx, s.bottom_at(s.left) * self.sy)
                  for s in self.sheet.staves.values()]
        for text, rect in self.note_labels:
            # get_text boxes include the font's full ascent/descent; shrink a hair.
            core = pymupdf.Rect(rect.x0, rect.y0 + 0.5, rect.x1, rect.y1 - 0.5)
            for staff in staves:
                self.assertFalse(core.intersects(staff), f"label {text!r} at {rect} is on a staff {staff}")

    def test_note_labels_leave_the_printing_intact(self):
        # No white outline behind note labels, so they can't clip a fingering number...
        self.assertFalse([s for s in _spans(self.notes_page) if s["color"] == 0xFFFFFF])
        # ...and they sit on blank paper (a squeezed chord may cross a stem).
        z, light = 3.0, bytes(range(150, 256))
        pix = pymupdf.open(PDF)[0].get_pixmap(matrix=pymupdf.Matrix(z, z), colorspace=pymupdf.csGRAY)
        on_ink = 0
        for span in _spans(self.notes_page):
            for x0, y0, x1, y1, word, *_ in self.notes_page.get_text("words", clip=span["bbox"]):
                base = span["origin"][1]
                r = pymupdf.Rect(x0 + 0.2, base - 0.72 * span["size"], x1 - 0.2, base)
                rows = range(int(r.y0 * z), int(r.y1 * z) + 1)
                dark = sum(len(pix.samples[y * pix.stride + int(r.x0 * z): y * pix.stride + int(r.x1 * z) + 1]
                               .translate(None, light)) for y in rows)
                on_ink += dark > 4
        self.assertLessEqual(on_ink, 2)

    def test_key_names_sit_right_on_their_sign(self):
        for key in self.sheet.keys:
            sign_top = key.box.y * self.sy
            cx = key.box.cx * self.sx
            near = [r for text, r in self.labels if text == key.name()
                    and abs((r.x0 + r.x1) / 2 - cx) <= 1.0 * self.space
                    and sign_top - 2.5 * self.space <= r.y1 <= sign_top + 0.5]
            self.assertTrue(near, f"no {key.name()} label right above the sign at {key.box}")

    def test_labels_do_not_overlap_each_other(self):
        # Text boxes are taller than the capital letters inside them (room for
        # accents and descenders), so compare the middle 60% of each box.
        def letters(r):
            return pymupdf.Rect(r.x0 + 0.3, r.y0 + 0.2 * r.height, r.x1 - 0.3, r.y1 - 0.2 * r.height)
        rects = [letters(r) for _, r in self.labels]
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                self.assertFalse(a.intersects(b), f"labels overlap at {a} / {b}")

    def test_options(self):
        out = Path(self.tmp.name) / "rainbow.pdf"
        write_labeled_pdf(PDF, [self.sheet], out, LabelOptions(color="rainbow", octave_numbers=True,
                                                               label_keys=False))
        with pymupdf.open(out) as doc:
            text = doc[0].get_text()
        self.assertIn("F#5", text)
        self.assertIn("D5", text)

    # --- Which side of each staff the labels go on -----------------------------
    def _zones(self):
        """For each piano system: the gap between the two hands, and the
        strips just above the top staff / just below the bottom staff."""
        staves = sorted(self.sheet.staves.values(), key=lambda s: s.top_at(s.left))
        zones = []
        for top, bottom in zip(staves, staves[1:]):
            if top.role == "top" and bottom.role == "bottom":
                y = lambda v: v * self.sy
                zones.append({
                    "between": (y(top.bottom_at(top.left)), y(bottom.top_at(bottom.left))),
                    "above_top": (y(top.top_at(top.left)) - 6 * self.space, y(top.top_at(top.left))),
                    "below_bottom": (y(bottom.bottom_at(bottom.left)), y(bottom.bottom_at(bottom.left)) + 6 * self.space),
                })
        return zones

    def _count(self, labels, zone_name):
        def inside(r, lo_hi):
            c = (r.y0 + r.y1) / 2
            return lo_hi[0] < c < lo_hi[1]
        return sum(1 for _, r in labels for z in self._zones() if inside(r, z[zone_name]))

    def test_staff_roles(self):
        roles = {sid: s.role for sid, s in self.sheet.staves.items()}
        self.assertEqual(roles[1], "top")
        self.assertEqual(roles[2], "bottom")
        self.assertEqual(sum(r == "bottom" for r in roles.values()), 6)   # 6 piano systems

    def test_default_top_above_bottom_below(self):
        self.assertEqual(self._count(self.note_labels, "between"), 0)   # nothing between the hands
        self.assertGreater(self._count(self.note_labels, "above_top"), 80)
        self.assertGreater(self._count(self.note_labels, "below_bottom"), 50)

    def test_swapped_sides_go_between_the_hands(self):
        out = Path(self.tmp.name) / "swapped.pdf"
        write_labeled_pdf(PDF, [self.sheet], out, LabelOptions(label_keys=False, top_staff="below",
                                                               bottom_staff="above"))
        with pymupdf.open(out) as doc:
            labels = labels_on(doc[0])
        self.assertEqual(len(labels), len(self.note_labels))
        self.assertGreater(self._count(labels, "between"), 0.9 * len(labels))


class PipelineTests(unittest.TestCase):
    def test_cli_with_omr_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main([str(OMR), "--out", tmp]), 0)
            out = Path(tmp) / "minuet_in_g (labeled).pdf"
            self.assertTrue(out.is_file())

    def test_rejects_unknown_file_type(self):
        with self.assertRaises(ValueError):
            label_file(FIXTURES / "nope.docx")

    @unittest.skipUnless(find_audiveris(), "Audiveris is not installed")
    def test_full_run_with_audiveris(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "minuet.pdf"
            src.write_bytes(PDF.read_bytes())
            result = label_file(src, use_cache=False)
            self.assertTrue(result.output_pdf.is_file())
            self.assertGreater(result.notes, 190)
            self.assertEqual(result.keys, ["G major / E minor"])


if __name__ == "__main__":
    unittest.main()
