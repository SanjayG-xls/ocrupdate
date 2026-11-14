"""Sequence K – credits and CBM. Totals are computed by the engine, not hard-coded."""
import pytest

from level_bridge.cbm import CBM


@pytest.mark.parametrize("correct,certainty,mark", [
    (True, 1, 1), (True, 2, 2), (True, 3, 3), (False, 1, 0), (False, 2, -2), (False, 3, -6)])
def test_all_six_cbm_combinations(cfg, correct, certainty, mark):
    assert CBM(cfg.app["scoring"]["cbm"]).mark(correct, certainty) == mark


def test_invalid_certainty(cfg):
    with pytest.raises(ValueError):
        CBM(cfg.app["scoring"]["cbm"]).mark(True, 4)


def test_credit_weights(ledger):
    e = ledger.record_assessment("x", "assessment", "apply", True, 2)
    assert e.assessment_credits == 6 and e.max_assessment_credits == 9
    w = ledger.record_assessment("y", "assessment", "transfer", False, 3)
    assert w.assessment_credits == 0 and w.cbm == -6


def test_recovery_outside_maximum(ledger):
    ledger.record_assessment("Q2", "assessment", "apply", False, 3)
    ledger.record_second_chance("Q2b", "apply", True, 2)
    assert ledger.assessment_max == 9 and ledger.recovery_credits == 3
    assert ledger.total_earned == 3 and ledger.cbm_total == -4 and ledger.cbm_max == 6


def test_priya_ledger(ledger):
    for item, lvl, ok, c in [("Q1", "recall", True, 3), ("Q2", "apply", False, 3)]:
        ledger.record_assessment(item, "assessment", lvl, ok, c)
    ledger.record_second_chance("Q2b", "apply", True, 2)
    for item, lvl, ok, c in [("Q3", "recall", True, 1), ("Q4", "apply", True, 3)]:
        ledger.record_assessment(item, "assessment", lvl, ok, c)
    ledger.record_assessment("T1", "transfer", "transfer", True, 3)
    s = ledger.summary()
    assert (s["assessment_credits"], s["assessment_max"]) == (25, 36)
    assert (s["recovery_credits"], s["total_earned"]) == (3, 28)
    assert (s["cbm_total"], s["cbm_max"]) == (6, 18)
