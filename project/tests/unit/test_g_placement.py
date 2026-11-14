"""Sequence G – placement rule R1."""
import pytest

from level_bridge.placement import place, start_rung


@pytest.mark.parametrize("score,rung", [(0, 1), (1, 1), (2, 2), (3, 3)])
def test_r1(score, rung, cfg):
    rule = cfg.app["routing"]["placement_to_rung"]
    responses = [{"item_id": f"P{i+1}", "correct": i < score} for i in range(3)]
    pr = place(responses, rule)
    assert (pr.score, pr.out_of, pr.start_rung) == (score, 3, rung)
    assert "not a diagnosis" in pr.note


def test_out_of_range_score():
    with pytest.raises(ValueError):
        start_rung(4)


def test_three_probe_types(artifacts):
    assert [it.probe_type for it in artifacts.bank.of_kind("placement")] == ["literal", "word_in_context", "inference"]
