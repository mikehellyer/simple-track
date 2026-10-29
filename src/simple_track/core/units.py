"""Lengths in the units modellers think in. Everything is stored in mm."""
from __future__ import annotations

# unit name -> (millimetres per unit, decimals worth showing)
UNITS: dict[str, tuple[float, int]] = {
    "mm": (1.0, 0),
    "cm": (10.0, 1),
    "m": (1000.0, 3),
    "in": (25.4, 2),
    "ft": (304.8, 3),
}

# Common baseboard sizes: label -> (width mm, depth mm)
BASEBOARD_PRESETS: dict[str, tuple[float, float]] = {
    "4 × 2 ft": (4 * 304.8, 2 * 304.8),
    "6 × 4 ft": (6 * 304.8, 4 * 304.8),
    "8 × 4 ft": (8 * 304.8, 4 * 304.8),
    "1200 × 600 mm": (1200.0, 600.0),
    "1800 × 1200 mm": (1800.0, 1200.0),
    "Shelf, 3000 × 400 mm": (3000.0, 400.0),
}


def to_mm(value: float, unit: str) -> float:
    return value * UNITS[unit][0]


def from_mm(mm: float, unit: str) -> float:
    return mm / UNITS[unit][0]


def describe(mm: float, unit: str) -> str:
    """'2440 mm', '1.22 m', and feet as feet and inches: '8 ft', '4 ft 6 in'."""
    if unit == "ft":
        inches = round(mm / 25.4, 1)
        feet = int(inches // 12)
        rest = round(inches - feet * 12, 1)
        return f"{feet} ft" if rest == 0 else f"{feet} ft {rest:g} in"
    value = round(from_mm(mm, unit), UNITS[unit][1])
    text = f"{value:.{UNITS[unit][1]}f}".rstrip("0").rstrip(".") if UNITS[unit][1] else f"{value:.0f}"
    return f"{text} {unit}"
