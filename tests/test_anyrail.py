"""The AnyRail importer, checked against real layouts when they're on this
machine (they're Mike's own files, so they aren't kept in the repo). Set
SIMPLE_TRACK_ANY_SAMPLES to the folder holding them, if it isn't the usual one."""
import math
import os
from collections import Counter
from pathlib import Path

import pytest

from simple_track.core.anyrail import AnyRailError, read_any
from simple_track.core.layout import connectors_join

SAMPLES = Path(os.environ.get("SIMPLE_TRACK_ANY_SAMPLES",
                              Path.home() / "Projects" / "AnyRail7_Original_Install"))


def sample(name: str) -> bytes:
    path = SAMPLES / name
    if not path.exists():
        pytest.skip(f"{name} isn't on this machine")
    return path.read_bytes()


def joined_ends(layout) -> int:
    poses = [c for p in layout.pieces for c in p.connectors()]
    return sum(1 for i, a in enumerate(poses) for b in poses[i + 1:] if connectors_join(a, b))


def test_rejects_other_files():
    with pytest.raises(AnyRailError):
        read_any(b"not a layout at all" * 10)


def test_dunnaemare():
    layout = read_any(sample("Dunnaemare.any"), "Dunnaemare")
    counts = Counter(p.code for p in layout.pieces)
    assert counts == {"SL-500": 11, "SL-E595": 4, "SL-E596": 1}
    assert all(p.source_library == "PC0100" and p.gauge_mm == 16.5 for p in layout.pieces)
    x0, y0, x1, y1 = layout.bounds()
    assert 3900 < x1 - x0 < 4100  # a 4 m shelf…
    assert 300 < y1 - y0 < 450  # …about 40 cm deep
    assert joined_ends(layout) >= 15


def test_hornby_dublo():
    layout = read_any(sample("Hornby Dublo.any"), "Hornby Dublo")
    parts = [p for p in layout.pieces if p.source_library]
    assert len(parts) == 66
    assert {p.source_library for p in parts} == {"00HDUBLO3"}
    assert [p.code for p in layout.pieces if not p.source_library] == ["Curve"]  # drawn freehand in AnyRail
    x0, y0, x1, y1 = layout.bounds()
    assert 1700 < x1 - x0 < 1850 and 950 < y1 - y0 < 1100
    assert any("background" in note for note in layout.notes)


def test_hornby_dublo_curves_dont_dangle():
    """Every end of every curve meets a connector or another line of its
    piece (on a point the curve sits between straight lead-in and tail)."""
    layout = read_any(sample("Hornby Dublo.any"))
    connectors = [(c.x, c.y) for p in layout.pieces for c in p.connectors()]
    loose = 0
    for piece in layout.pieces:
        lines = piece.polylines()
        for i, line in enumerate(lines):
            if len(line) <= 2:
                continue  # a straight
            others = [p for j, other in enumerate(lines) if j != i for p in (other[0], other[-1])]
            for end in (line[0], line[-1]):
                loose += min(math.dist(end, p) for p in connectors + others) > 1.0
    assert loose == 0
