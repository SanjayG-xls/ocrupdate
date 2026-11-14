"""Deterministic formula engine with dimensional analysis and coded error models.

The engine – never the LLM – computes every numerical answer. Each formula in the
library has the form ``output = numerator ÷ denominator`` (the Class 6–10 relations
used in the PoC). Extending the library means adding an entry to ``FORMULAS``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from .quantity_parser import Quantity, UnitError, UNITS, display_unit, fmt_number


class InvalidInput(ValueError):
    """Raised when inputs violate the engine's input contract (missing/incompatible units, zero denominator)."""


@dataclass(frozen=True)
class Formula:
    """``output = numerator ÷ denominator`` with dimensions and preferred output units."""

    key: str
    output: str
    numerator: str
    denominator: str
    output_dim: str
    numerator_dim: str
    denominator_dim: str
    # (numerator unit, denominator unit) -> natural output unit
    unit_map: Dict[tuple, str]
    default_output_unit: str

    @property
    def text(self) -> str:
        return f"{self.output} = {self.numerator} ÷ {self.denominator}"

    def to_dict(self) -> Dict[str, object]:
        return {"key": self.key, "text": self.text, "output": self.output, "numerator": self.numerator,
                "denominator": self.denominator, "output_dimension": self.output_dim}


FORMULAS: Dict[str, Formula] = {
    "speed": Formula("speed", "speed", "distance", "time", "speed", "length", "time",
                     {("km", "h"): "km/h", ("m", "s"): "m/s"}, "km/h"),
    "density": Formula("density", "density", "mass", "volume", "density", "mass", "volume",
                       {("g", "cm3"): "g/cm3", ("kg", "m3"): "kg/m3"}, "g/cm3"),
    # live-round extension: common Class 6-10 ratio formulas
    "pressure": Formula("pressure", "pressure", "force", "area", "pressure", "force", "area",
                        {("N", "m2"): "Pa", ("N", "cm2"): "N/cm2"}, "Pa"),
    "resistance": Formula("resistance", "resistance", "voltage", "current", "resistance", "voltage", "current",
                          {("V", "A"): "ohm"}, "ohm"),
    "power": Formula("power", "power", "work", "time", "power", "energy", "time",
                     {("J", "s"): "W", ("kJ", "s"): "kW"}, "W"),
}

# multi-word or alternative names used in textbooks -> library quantity name
QUANTITY_ALIASES = {
    "potential difference": "voltage", "electric current": "current", "electrical resistance": "resistance",
    "work done": "work", "energy used": "work", "energy": "work", "thrust": "force",
}

# preferred unit for each input dimension when converting towards an output unit
_TARGET_INPUT_UNITS = {
    "km/h": ("km", "h"), "m/s": ("m", "s"), "g/cm3": ("g", "cm3"), "kg/m3": ("kg", "m3"),
    "Pa": ("N", "m2"), "N/m2": ("N", "m2"), "N/cm2": ("N", "cm2"), "ohm": ("V", "A"), "W": ("J", "s"), "kW": ("kJ", "s"),
}


@dataclass
class Solution:
    """A worked solution: formula, conversions, substitution, calculation, answer."""

    formula: str
    conversions: List[str]
    substitution: str
    calculation: str
    value: float
    unit: str
    answer_text: str

    def steps(self) -> List[str]:
        out = [f"Formula: {self.formula}"]
        out += [f"Convert: {c}" for c in self.conversions]
        out += [f"Substitute: {self.substitution}", f"Calculate: {self.calculation}", f"Answer: {self.answer_text}"]
        return out

    def to_dict(self) -> Dict[str, object]:
        d = asdict(self)
        d["steps"] = self.steps()
        return d


@dataclass(frozen=True)
class ErrorModel:
    """A coded misconception: the value a student gets by making a specific error."""

    code: str
    value: float
    unit_label: str          # the (often invalid) unit that error actually produces
    explanation: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def make_quantity(value: Optional[float], unit: Optional[str]) -> Quantity:
    """Input contract: a quantity needs a number AND a known unit. Raises :class:`InvalidInput`."""
    if value is None:
        raise InvalidInput("Missing value")
    if not unit:
        raise InvalidInput(f"Missing unit for value {fmt_number(value)}: units are required")
    try:
        return Quantity(float(value), unit)
    except UnitError as exc:
        raise InvalidInput(str(exc)) from exc


def compute(formula: Formula, numerator: Optional[Quantity], denominator: Optional[Quantity],
            target_unit: Optional[str] = None) -> Solution:
    """Compute ``formula`` with full dimensional checking.

    Raises :class:`InvalidInput` for missing quantities/units, dimension mismatches and
    a zero (or negative) denominator. Converts inputs explicitly when needed.
    """
    if numerator is None or denominator is None:
        raise InvalidInput("Missing quantity: both inputs with units are required")
    if numerator.dimension != formula.numerator_dim:
        raise InvalidInput(f"{formula.numerator} must be a {formula.numerator_dim}, got {numerator.unit}")
    if denominator.dimension != formula.denominator_dim:
        raise InvalidInput(f"{formula.denominator} must be a {formula.denominator_dim}, got {denominator.unit}")
    if denominator.value <= 0:
        raise InvalidInput(f"{formula.denominator} must be greater than zero (got {fmt_number(denominator.value)})")
    if target_unit is None:
        target_unit = formula.unit_map.get((numerator.unit, denominator.unit), formula.default_output_unit)
    if target_unit not in UNITS or UNITS[target_unit][0] != formula.output_dim:
        raise InvalidInput(f"'{target_unit}' is not a unit of {formula.output}")
    want_num, want_den = _TARGET_INPUT_UNITS[target_unit]
    conversions: List[str] = []
    num, den = numerator, denominator
    if num.unit != want_num:
        num = num.convert(want_num)
        conversions.append(f"{numerator.text()} = {num.text()}")
    if den.unit != want_den:
        den = den.convert(want_den)
        conversions.append(f"{denominator.text()} = {den.text()}")
    value = num.value / den.value
    unit = target_unit
    return Solution(
        formula=formula.text,
        conversions=conversions,
        substitution=f"{formula.output} = {num.text()} ÷ {den.text()}",
        calculation=f"{fmt_number(num.value)} ÷ {fmt_number(den.value)} = {fmt_number(value)}",
        value=round(value, 6),
        unit=unit,
        answer_text=f"{fmt_number(value)} {display_unit(unit)}",
    )


def error_models(formula: Formula, numerator: Quantity, denominator: Quantity,
                 target_unit: Optional[str] = None) -> List[ErrorModel]:
    """Values produced by coded misconceptions for this item (never shown as valid options).

    The unit label records what the wrong operation *actually* produces, e.g.
    ``180 km × 3 h = 540 km·h`` – which is not a unit of speed.
    """
    nu, du = display_unit(numerator.unit), display_unit(denominator.unit)
    a, b = numerator.value, denominator.value
    models = [
        ErrorModel("wrong_operation_multiply", a * b, f"{nu}·{du}",
                   f"{numerator.text()} × {denominator.text()} = {fmt_number(a * b)} {nu}·{du}, which is not a unit of {formula.output}."),
        ErrorModel("wrong_operation_add", a + b, "invalid",
                   f"{numerator.text()} + {denominator.text()} cannot be added: they measure different things."),
        ErrorModel("inverted_formula", b / a if a else float("nan"), f"{du}/{nu}",
                   f"{denominator.text()} ÷ {numerator.text()} gives {du}/{nu}; {formula.output} is {formula.numerator} ÷ {formula.denominator}."),
        ErrorModel("ignored_variable", a, nu,
                   f"{numerator.text()} is the {formula.numerator}, not the {formula.output}; the {formula.denominator} must be used."),
    ]
    sol = compute(formula, numerator, denominator, target_unit)
    if sol.conversions:  # inputs needed conversion -> "unit not converted" is a meaningful error
        models.append(ErrorModel("unit_not_converted", a / b, f"{nu}/{du}",
                                 f"{fmt_number(a)} ÷ {fmt_number(b)} = {fmt_number(a / b)} is in {nu}/{du}; convert first ({'; '.join(sol.conversions)})."))
    # never keep an error model that coincides with the correct value
    return [m for m in models if not _close(m.value, sol.value)]


def _close(x: float, y: float, rel: float = 0.01) -> bool:
    if x != x or y != y:  # NaN
        return False
    return abs(x - y) <= rel * max(1.0, abs(y))


@dataclass
class NumericEvaluation:
    """Result of comparing a student's numeric entry with the solution and error models."""

    correct: bool
    entered_value: Optional[float]
    entered_unit: Optional[str]
    matched_error: Optional[ErrorModel]
    message: str
    unit_issue: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        d = asdict(self)
        d["matched_error"] = self.matched_error.to_dict() if self.matched_error else None
        return d


def evaluate_numeric(entered_value: Optional[float], entered_unit: Optional[str], solution: Solution,
                     models: List[ErrorModel], tolerance: float = 0.02) -> NumericEvaluation:
    """Evaluate a numeric answer. The expected unit is implied by the question when omitted.

    A correct number with a wrong unit is marked incorrect with ``unit_issue`` set.
    """
    if entered_value is None:
        return NumericEvaluation(False, None, entered_unit, None, "No number was entered.")
    if entered_unit not in (None, solution.unit):
        if entered_unit in UNITS and UNITS[entered_unit][0] == UNITS[solution.unit][0]:
            converted = Quantity(entered_value, entered_unit).convert(solution.unit).value
            if _close(converted, solution.value, tolerance):
                return NumericEvaluation(True, entered_value, entered_unit, None,
                                         f"Correct ({fmt_number(entered_value)} {display_unit(entered_unit)} = {solution.answer_text}).")
        issue = f"'{entered_unit}' is not the unit asked for ({display_unit(solution.unit)})."
        return NumericEvaluation(False, entered_value, entered_unit, None, issue, unit_issue=issue)
    if _close(entered_value, solution.value, tolerance):
        return NumericEvaluation(True, entered_value, entered_unit, None, f"Correct: {solution.answer_text}.")
    # several error models can be numerically close (e.g. 180 vs 183): take the nearest match
    near = [m for m in models if _close(entered_value, m.value, tolerance)]
    if near:
        m = min(near, key=lambda x: abs(entered_value - x.value) / max(1.0, abs(x.value)))
        return NumericEvaluation(False, entered_value, entered_unit, m, m.explanation)
    return NumericEvaluation(False, entered_value, entered_unit, None,
                             f"Not correct. Expected {solution.answer_text}.")


# ----------------------------------------------------------------------------- detection in text
_Q = r"(?:the |its |their |a |an )?(?:total )?(\w+)"
# (pattern, order of groups as (output, numerator, denominator))
_FORMULA_PATTERNS = [
    (re.compile(r"\b(\w+) is (?:calculated|found|obtained|given|worked out|measured) by dividing " + _Q + r"\b.*?\bby " + _Q, re.I), (0, 1, 2)),
    (re.compile(r"\b(\w+)\s*(?:=|equals|is equal to)\s*" + _Q + r"\s*(?:÷|/|divided by)\s*" + _Q, re.I), (0, 1, 2)),
    (re.compile(r"\b(\w+) is " + _Q + r" divided by " + _Q, re.I), (0, 1, 2)),
    (re.compile(r"\bdividing " + _Q + r"\b.*?\bby " + _Q + r"\b.*?\b(?:gives|gives us|equals) " + _Q, re.I), (2, 0, 1)),
    (re.compile(r"\b(\w+) is the ratio of " + _Q + r" to " + _Q, re.I), (0, 1, 2)),
]
# kept for backward compatibility with older imports
_DIVIDE_RE = _FORMULA_PATTERNS[0][0]
_EQUALS_RE = _FORMULA_PATTERNS[1][0]


def normalise_quantity_names(text: str) -> str:
    """Rewrite textbook synonyms (e.g. 'potential difference') to library names before matching."""
    out = text
    for alias in sorted(QUANTITY_ALIASES, key=len, reverse=True):
        out = re.sub(rf"\b{re.escape(alias)}\b", QUANTITY_ALIASES[alias], out, flags=re.I)
    return out


def detect_formula(sentence: str) -> Optional[Formula]:
    """Return a library formula stated in ``sentence``.

    Recognised forms include 'X is calculated by dividing A … by B', 'X = A ÷ B', 'X is A divided by B',
    'dividing A by B gives X' and 'X is the ratio of A to B'. Quantity synonyms are normalised first.
    """
    text = normalise_quantity_names(sentence)
    for rx, order in _FORMULA_PATTERNS:
        for m in rx.finditer(text):
            g = [x.lower() for x in m.groups()]
            out, num, den = g[order[0]], g[order[1]], g[order[2]]
            for f in FORMULAS.values():
                if f.output == out and f.numerator == num and f.denominator == den:
                    return f
    return None


def formula_by_output(name: str) -> Optional[Formula]:
    return FORMULAS.get(name.lower())


def relation_direction(formula: Formula, changed_variable: str, change: str) -> str:
    """Direction of the output when one input changes and the other is fixed.

    ``change`` is 'increase' or 'decrease'. Returns 'increase'/'decrease'. For
    ``out = num ÷ den`` the output follows the numerator and opposes the denominator.
    """
    if changed_variable == formula.numerator:
        return change
    if changed_variable == formula.denominator:
        return "decrease" if change == "increase" else "increase"
    raise InvalidInput(f"{changed_variable} is not an input of {formula.text}")
