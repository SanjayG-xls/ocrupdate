"""Sequence J – misconception detection and repair for the 540 case."""
from level_bridge.misconception_detector import evaluate
from level_bridge.repair_engine import RepairEngine


def test_540_is_wrong_operation(artifacts):
    ev = evaluate(artifacts.bank.by_id("Q2"), "540 km/h")
    assert not ev.correct and ev.error_code == "wrong_operation_multiply"
    assert ev.expected == "60 km/h"


def test_repair_explains_km_h_and_gives_60(artifacts):
    q2 = artifacts.bank.by_id("Q2")
    rep = RepairEngine(artifacts.km, artifacts.registry, artifacts.validator).repair(q2, evaluate(q2, "540"))
    text = " ".join(rep.lines)
    assert "540 km·h" in text and "60 km/h" in text and "S3" in text
    assert rep.source == "template"


def test_second_chance_cyclist_12(artifacts):
    sc = artifacts.bank.second_chance_for("Q2")
    assert sc.item_id == "Q2b" and "24 km" in sc.stem
    assert evaluate(sc, "12 km/h").correct and evaluate(sc, "12").correct
    assert not evaluate(sc, "48 km/h").correct


def test_other_error_models(artifacts):
    q2 = artifacts.bank.by_id("Q2")
    assert evaluate(q2, "0.0167").error_code == "inverted_formula"
    assert evaluate(q2, "180 km/h").error_code == "ignored_variable"
    assert evaluate(q2, "183").error_code == "wrong_operation_add"
    assert evaluate(q2, "77 km/h").error_code == "incorrect"


def test_mcq_error_codes(artifacts):
    q4 = artifacts.bank.by_id("Q4")
    wrong = next(o for o in q4.options if o.error_code == "reversed_relation")
    assert evaluate(q4, wrong.key).error_code == "reversed_relation"
    assert evaluate(q4, "Z").error_code == "invalid_response"
