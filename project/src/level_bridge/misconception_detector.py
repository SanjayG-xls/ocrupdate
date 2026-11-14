"""Evaluate responses and identify coded misconceptions.

MCQ: the chosen option carries its error code. Numeric: Python recomputes the solution
from the item's inputs and compares the entry with the correct value and with each
coded error model (wrong operation, inverted formula, unit not converted, ...).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Optional

from .formula_engine import FORMULAS, compute, error_models, evaluate_numeric
from .question_generator import Item
from .quantity_parser import Quantity, parse_answer


@dataclass
class Evaluation:
    item_id: str
    correct: bool
    response: str
    error_code: Optional[str]
    message: str
    chosen_text: Optional[str] = None
    expected: Optional[str] = None
    details: Optional[Dict[str, object]] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _formula_for(item: Item):
    # numeric items always come from the primary formula of the knowledge map
    for f in FORMULAS.values():
        sol = item.numeric["solution"]
        if sol["formula"] == f.text:
            return f
    raise KeyError(item.numeric["solution"]["formula"])


def evaluate(item: Item, response: str) -> Evaluation:
    """Evaluate ``response`` (option letter for MCQ, number with optional unit for numeric)."""
    response = (response or "").strip()
    if item.response_type == "mcq":
        key = response[:1].upper()
        opt = next((o for o in item.options if o.key == key), None)
        co = item.correct_option()
        if opt is None:
            return Evaluation(item.item_id, False, response, "invalid_response",
                              f"'{response}' is not one of {[o.key for o in item.options]}", expected=co.text if co else None)
        return Evaluation(item.item_id, opt.correct, response, None if opt.correct else (opt.error_code or "incorrect"),
                          "Correct." if opt.correct else f"Not correct: \"{opt.text}\".", opt.text, co.text if co else None)
    # numeric
    f = _formula_for(item)
    inp = item.numeric["inputs"]
    a = Quantity(inp["numerator"]["value"], inp["numerator"]["unit"])
    b = Quantity(inp["denominator"]["value"], inp["denominator"]["unit"])
    target = item.numeric["solution"]["unit"]
    sol = compute(f, a, b, target)            # recomputed, not read back from storage
    models = error_models(f, a, b, target)
    value, unit = parse_answer(response, target)
    ev = evaluate_numeric(value, unit, sol, models)
    code = None if ev.correct else (ev.matched_error.code if ev.matched_error else ("unit_error" if ev.unit_issue else "incorrect"))
    return Evaluation(item.item_id, ev.correct, response, code, ev.message, expected=sol.answer_text,
                      details={"solution": sol.to_dict(), "matched_error": ev.matched_error.to_dict() if ev.matched_error else None,
                               "unit_issue": ev.unit_issue})
