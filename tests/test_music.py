import unittest

from note_labeler import music


class ClefTests(unittest.TestCase):
    def test_treble_lines(self):
        # Staff positions: -4 is the top line, +4 the bottom line.
        names = [music.spell(music.TREBLE.diatonic(p), 0, True) for p in (-4, -2, 0, 2, 4)]
        self.assertEqual(names, ["F5", "D5", "B4", "G4", "E4"])

    def test_bass_lines(self):
        names = [music.spell(music.BASS.diatonic(p), 0, True) for p in (-4, -2, 0, 2, 4)]
        self.assertEqual(names, ["A3", "F3", "D3", "B2", "G2"])

    def test_middle_c_on_ledger_lines(self):
        self.assertEqual(music.spell(music.TREBLE.diatonic(6), 0, True), "C4")
        self.assertEqual(music.spell(music.BASS.diatonic(-6), 0, True), "C4")

    def test_octave_clefs_and_c_clef(self):
        self.assertEqual(music.spell(music.Clef("G_CLEF_8VB", 2).diatonic(2), 0, True), "G3")
        self.assertEqual(music.spell(music.Clef("C_CLEF", 0).diatonic(0), 0, True), "C4")


class KeyTests(unittest.TestCase):
    def test_sharps(self):
        self.assertEqual(music.key_alters(1), {music.STEPS.index("F"): 1})
        self.assertEqual(set(music.key_alters(3)), {music.STEPS.index(s) for s in "FCG"})

    def test_flats(self):
        self.assertEqual(music.key_alters(-2), {music.STEPS.index("B"): -1, music.STEPS.index("E"): -1})

    def test_names(self):
        self.assertEqual(music.key_name(0), "C major / A minor")
        self.assertEqual(music.key_name(1), "G major / E minor")
        self.assertEqual(music.key_name(-3), "Eb major / C minor")

    def test_spelling(self):
        self.assertEqual(music.spell(28, 1), "C#")
        self.assertEqual(music.spell(34, -1), "Bb")
        self.assertEqual(music.spell(31, 2, True), "F##4")
        self.assertEqual(music.spell(30, 0), "E")


if __name__ == "__main__":
    unittest.main()
