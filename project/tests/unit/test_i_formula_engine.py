"""Sequence I – deterministic numeric engine."""
import pytest

from level_bridge.formula_engine import FORMULAS, InvalidInput, compute, error_models, evaluate_numeric, make_quantity
from level_bridge.quantity_parser import Quantity, parse_answer

S = FORMULAS["speed"]


@pytest.mark.parametrize("d,t,value", [
    ((180, "km"), (3, "h"), 60),
    ((24, "km"), (2, "h"), 12),
    ((2, "km"), (30, "min"), 4),
    ((120, "km"), (2, "h"), 60),
])
def test_speed_cases(d, t, value):
    sol = compute(S, Quantity(*d), Quantity(*t), "km/h")
    assert sol.value == pytest.approx(value) and sol.unit == "km/h"
    steps = sol.steps()
    assert steps[0] == "Formula: speed = distance ÷ time"
    assert any(s.startswith("Substitute:") for s in steps)
    assert any(s.startswith("Calculate:") for s in steps)
    assert steps[-1] == f"Answer: {value} km/h"


def test_unit_conversion_is_shown():
    sol = compute(S, Quantity(2, "km"), Quantity(30, "min"), "km/h")
    assert "Convert: 30 min = 0.5 h" in sol.steps()


def test_zero_time_invalid():
    with pytest.raises(InvalidInput, match="greater than zero"):
        compute(S, Quantity(180, "km"), Quantity(0, "h"), "km/h")


def test_missing_unit_invalid():
    with pytest.raises(InvalidInput, match="Missing unit"):
        make_quantity(180, None)


def test_incompatible_units_invalid():
    with pytest.raises(InvalidInput):
        compute(S, Quantity(180, "kg"), Quantity(3, "h"), "km/h")


def test_never_540_km_per_h():
    sol = compute(S, Quantity(180, "km"), Quantity(3, "h"), "km/h")
    assert sol.value != 540
    mult = next(m for m in error_models(S, Quantity(180, "km"), Quantity(3, "h"), "km/h") if m.code == "wrong_operation_multiply")
    assert mult.value == 540 and mult.unit_label == "km·h"      # the error model labels it km·h, never km/h


def test_correct_value_wrong_unit_is_unit_issue():
    sol = compute(S, Quantity(180, "km"), Quantity(3, "h"), "km/h")
    v, u = parse_answer("60 m/s", "km/h")
    ev = evaluate_numeric(v, u, sol, error_models(S, Quantity(180, "km"), Quantity(3, "h"), "km/h"))
    assert not ev.correct and ev.unit_issue
