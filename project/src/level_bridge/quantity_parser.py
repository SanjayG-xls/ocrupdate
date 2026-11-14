"""Quantities, units and dimensional analysis.

Every quantity carries a canonical unit and a physical dimension. Arithmetic in the
formula engine is only allowed between dimensionally compatible quantities.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

# canonical unit -> (dimension, factor to the SI base unit of that dimension)
UNITS: Dict[str, Tuple[str, float]] = {
    "km": ("length", 1000.0), "m": ("length", 1.0), "cm": ("length", 0.01),
    "h": ("time", 3600.0), "min": ("time", 60.0), "s": ("time", 1.0),
    "km/h": ("speed", 1000.0 / 3600.0), "m/s": ("speed", 1.0),
    "kg": ("mass", 1.0), "g": ("mass", 0.001),
    "cm3": ("volume", 1e-6), "m3": ("volume", 1.0),
    "g/cm3": ("density", 1000.0), "kg/m3": ("density", 1.0),
    # live-round formula library extension: pressure, resistance (Ohm's law), power
    "N": ("force", 1.0),
    "m2": ("area", 1.0), "cm2": ("area", 1e-4),
    "Pa": ("pressure", 1.0), "N/m2": ("pressure", 1.0), "N/cm2": ("pressure", 1e4),
    "V": ("voltage", 1.0), "A": ("current", 1.0), "mA": ("current", 1e-3), "ohm": ("resistance", 1.0),
    "J": ("energy", 1.0), "kJ": ("energy", 1000.0), "W": ("power", 1.0), "kW": ("power", 1000.0),
}

# surface form -> canonical unit (longest forms are matched first)
UNIT_ALIASES: Dict[str, str] = {
    "kilometres per hour": "km/h", "kilometers per hour": "km/h", "kilometre per hour": "km/h",
    "kilometer per hour": "km/h", "kmph": "km/h", "km/h": "km/h", "km/hr": "km/h",
    "metres per second": "m/s", "meters per second": "m/s", "metre per second": "m/s",
    "meter per second": "m/s", "m/s": "m/s",
    "grams per cubic centimetre": "g/cm3", "g/cm3": "g/cm3", "g/cm³": "g/cm3",
    "kilograms per cubic metre": "kg/m3", "kg/m3": "kg/m3", "kg/m³": "kg/m3",
    "kilometres": "km", "kilometers": "km", "kilometre": "km", "kilometer": "km", "km": "km",
    "centimetres": "cm", "centimeters": "cm", "cm": "cm",
    "cubic centimetres": "cm3", "cubic centimeters": "cm3", "cm3": "cm3", "cm³": "cm3",
    "cubic metres": "m3", "m3": "m3", "m³": "m3",
    "metres": "m", "meters": "m", "metre": "m", "meter": "m", "m": "m",
    "hours": "h", "hour": "h", "hrs": "h", "hr": "h", "h": "h",
    "minutes": "min", "minute": "min", "mins": "min", "min": "min",
    "seconds": "s", "second": "s", "secs": "s", "sec": "s", "s": "s",
    "kilograms": "kg", "kilogram": "kg", "kg": "kg",
    "grams": "g", "gram": "g", "g": "g",
    "newtons per square metre": "N/m2", "newtons per square meter": "N/m2", "n/m2": "N/m2", "n/m²": "N/m2",
    "newtons per square centimetre": "N/cm2", "n/cm2": "N/cm2", "n/cm²": "N/cm2",
    "newtons": "N", "newton": "N", "n": "N",
    "square metres": "m2", "square meters": "m2", "square metre": "m2", "square meter": "m2", "m2": "m2", "m²": "m2",
    "square centimetres": "cm2", "square centimeters": "cm2", "square centimetre": "cm2", "cm2": "cm2", "cm²": "cm2",
    "pascals": "Pa", "pascal": "Pa", "pa": "Pa",
    "volts": "V", "volt": "V", "v": "V",
    "milliamperes": "mA", "milliampere": "mA", "ma": "mA",
    "amperes": "A", "ampere": "A", "amps": "A", "amp": "A", "a": "A",
    "ohms": "ohm", "ohm": "ohm", "ω": "ohm",
    "kilojoules": "kJ", "kilojoule": "kJ", "kj": "kJ",
    "joules": "J", "joule": "J", "j": "J",
    "kilowatts": "kW", "kilowatt": "kW", "kw": "kW",
    "watts": "W", "watt": "W", "w": "W",
}

DISPLAY = {"cm3": "cm³", "m3": "m³", "g/cm3": "g/cm³", "kg/m3": "kg/m³", "m2": "m²", "cm2": "cm²",
           "N/m2": "N/m²", "N/cm2": "N/cm²", "ohm": "Ω"}
# single letters that are also ordinary words: only accepted as units when written in capitals
_CASE_SENSITIVE_UNITS = {"a": "A"}


class UnitError(ValueError):
    """Raised for unknown, missing or dimensionally incompatible units."""


def display_unit(unit: str) -> str:
    return DISPLAY.get(unit, unit)


@dataclass(frozen=True)
class Quantity:
    """A numeric value with a canonical unit."""

    value: float
    unit: str

    def __post_init__(self) -> None:
        if self.unit not in UNITS:
            raise UnitError(f"Unknown unit '{self.unit}'")

    @property
    def dimension(self) -> str:
        return UNITS[self.unit][0]

    def to_base(self) -> float:
        return self.value * UNITS[self.unit][1]

    def convert(self, target_unit: str) -> "Quantity":
        """Convert to another unit of the same dimension (raises :class:`UnitError` otherwise)."""
        if target_unit not in UNITS:
            raise UnitError(f"Unknown unit '{target_unit}'")
        if UNITS[target_unit][0] != self.dimension:
            raise UnitError(f"Cannot convert {self.unit} ({self.dimension}) to {target_unit} ({UNITS[target_unit][0]})")
        return Quantity(self.to_base() / UNITS[target_unit][1], target_unit)

    def text(self) -> str:
        return f"{fmt_number(self.value)} {display_unit(self.unit)}"

    def to_dict(self) -> Dict[str, object]:
        d = asdict(self)
        d["dimension"] = self.dimension
        return d


def fmt_number(x: float) -> str:
    """Format a number without spurious decimals (60.0 -> '60', 0.5 -> '0.5')."""
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.3f}".rstrip("0").rstrip(".")


def normalise_unit(token: str) -> Optional[str]:
    """Map a unit surface form to its canonical unit, or ``None`` if unknown."""
    return UNIT_ALIASES.get(token.strip().lower())


_ALIAS_PATTERN = "|".join(sorted((re.escape(a) for a in UNIT_ALIASES), key=len, reverse=True))
_QTY_RE = re.compile(rf"(?<![\w.])(\d+(?:\.\d+)?)\s*({_ALIAS_PATTERN})(?![\w/])", re.IGNORECASE)
_UNIT_MENTION_RE = re.compile(rf"\(\s*({_ALIAS_PATTERN})\s*\)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.]*\d)")


@dataclass(frozen=True)
class QuantityMention:
    """A quantity found in text."""

    sid: str
    quantity: Quantity
    surface: str

    def to_dict(self) -> Dict[str, object]:
        return {"sid": self.sid, "surface": self.surface, **self.quantity.to_dict()}


def parse_quantities(text: str, sid: str = "") -> List[QuantityMention]:
    """Find ``<number> <unit>`` pairs in ``text``."""
    out = []
    for m in _QTY_RE.finditer(text):
        unit = normalise_unit(m.group(2))
        if m.group(2).lower() in _CASE_SENSITIVE_UNITS and m.group(2) != _CASE_SENSITIVE_UNITS[m.group(2).lower()]:
            continue
        if unit:
            out.append(QuantityMention(sid, Quantity(float(m.group(1)), unit), m.group(0)))
    return out


def parse_unit_mentions(text: str) -> List[str]:
    """Find units written in brackets, e.g. ``(m/s)`` -> ``['m/s']``."""
    found = []
    for m in _UNIT_MENTION_RE.finditer(text):
        u = normalise_unit(m.group(1))
        if u and u not in found:
            found.append(u)
    return found


def parse_numbers(text: str) -> List[float]:
    """All numbers in ``text`` (used by the numerical-consistency check)."""
    return [float(n) for n in re.findall(r"(?<![\w.])\d+(?:\.\d+)?", text)]


def parse_answer(raw: str, expected_unit: Optional[str] = None) -> Tuple[Optional[float], Optional[str]]:
    """Parse a student's numeric entry such as ``'60'``, ``'60 km/h'``, ``'540 km·h'``.

    Returns ``(value, canonical_unit_or_None)``. A unit that is not a known canonical
    unit (for example ``km·h``) is returned as written so the caller can reject it.
    """
    s = raw.strip().replace(",", "")
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*(.*)$", s)
    if not m:
        return None, None
    value = float(m.group(1))
    unit_text = m.group(2).strip()
    if not unit_text:
        return value, None
    unit = normalise_unit(unit_text)
    return value, unit if unit else unit_text
