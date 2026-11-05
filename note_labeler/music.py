"""Music theory helpers: clefs, key signatures and note spelling.

Audiveris gives every note a *staff position* ("pitch"): 0 is the middle
staff line, and the number goes UP as you move DOWN the staff (-4 is the top
line, +4 the bottom line). Everything here turns that position into a note
name such as "F#" or "Bb".

We count notes as "diatonic numbers": octave * 7 + step, where step 0..6 is
C D E F G A B. Middle C (C4) is therefore 4 * 7 + 0 = 28.
"""
from __future__ import annotations

STEPS = "CDEFGAB"
SHARP_ORDER = "FCGDAEB"  # order sharps appear in a key signature
FLAT_ORDER = "BEADGCF"   # order flats appear in a key signature

# Note each clef shape "points at", as a diatonic number.
_CLEF_REFERENCE = {
    "G": 4 * 7 + 4,  # G clef curls around G4
    "F": 3 * 7 + 3,  # F clef dots surround F3
    "C": 4 * 7 + 0,  # C clef centre marks middle C
}

# Accidental shapes Audiveris uses -> semitone change.
ALTER_SHAPES = {
    "SHARP": 1,
    "FLAT": -1,
    "NATURAL": 0,
    "DOUBLE_SHARP": 2,
    "DOUBLE_FLAT": -2,
}

# Major / minor key names for each number of sharps (+) or flats (-).
_KEY_NAMES = {
    -7: ("Cb major", "Ab minor"), -6: ("Gb major", "Eb minor"),
    -5: ("Db major", "Bb minor"), -4: ("Ab major", "F minor"),
    -3: ("Eb major", "C minor"), -2: ("Bb major", "G minor"),
    -1: ("F major", "D minor"), 0: ("C major", "A minor"),
    1: ("G major", "E minor"), 2: ("D major", "B minor"),
    3: ("A major", "F# minor"), 4: ("E major", "C# minor"),
    5: ("B major", "G# minor"), 6: ("F# major", "D# minor"),
    7: ("C# major", "A# minor"),
}


class Clef:
    """A clef sitting on a given staff position."""

    def __init__(self, shape: str, line: int):
        self.shape = shape
        self.line = line  # staff position the clef marks (G clef is usually 2)
        self.percussion = shape.startswith("PERCUSSION")
        family = shape[0] if shape[:1] in _CLEF_REFERENCE else "G"
        ref = _CLEF_REFERENCE[family]
        if "8VA" in shape:
            ref += 7
        elif "8VB" in shape:
            ref -= 7
        self.reference = ref

    def diatonic(self, staff_position: int) -> int:
        """Diatonic number of a note at this staff position."""
        return self.reference - (staff_position - self.line)

    def __repr__(self) -> str:
        return f"Clef({self.shape}, line={self.line})"


TREBLE = Clef("G_CLEF", 2)
BASS = Clef("F_CLEF", -2)


def key_alters(fifths: int) -> dict[int, int]:
    """Which steps a key signature raises or lowers: {step index: +1/-1}."""
    fifths = max(-7, min(7, fifths))
    if fifths >= 0:
        return {STEPS.index(s): 1 for s in SHARP_ORDER[:fifths]}
    return {STEPS.index(s): -1 for s in FLAT_ORDER[:-fifths]}


def key_name(fifths: int) -> str:
    major, minor = _KEY_NAMES[max(-7, min(7, fifths))]
    return f"{major} / {minor}"


def accidental_text(alter: int) -> str:
    return {2: "##", 1: "#", 0: "", -1: "b", -2: "bb"}.get(alter, "")


def spell(diatonic: int, alter: int, with_octave: bool = False) -> str:
    """Note name, e.g. spell(28, 1) -> 'C#' (or 'C#4' with octave)."""
    octave, step = divmod(diatonic, 7)
    name = STEPS[step] + accidental_text(alter)
    return f"{name}{octave}" if with_octave else name


def step_of(diatonic: int) -> int:
    return diatonic % 7
