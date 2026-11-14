"""Sequence L – concept-state transitions."""
import pytest

from level_bridge.concept_states import ConceptTracker, IllegalTransition, State


@pytest.mark.parametrize("events,final", [
    (["correct_first"], State.PROVISIONAL),
    (["wrong_first"], State.FRAGILE),
    (["wrong_first", "second_chance_correct"], State.REPAIRED),
    (["wrong_first", "second_chance_wrong"], State.FRAGILE),
    (["correct_first", "transfer_correct"], State.TRANSFERRED),
    (["wrong_first", "second_chance_correct", "transfer_correct"], State.TRANSFERRED),
    (["correct_first", "transfer_wrong"], State.FRAGILE),
    (["correct_first", "wrong"], State.FRAGILE),
])
def test_legal(events, final):
    t = ConceptTracker(["C1"])
    for e in events:
        t.apply("C1", e)
    assert t.states["C1"] == final and len(t.history["C1"]) == len(events)


@pytest.mark.parametrize("events", [
    ["second_chance_correct"],                       # cannot repair before an error
    ["correct_first", "correct_first"],
    ["wrong_first", "second_chance_correct", "correct_first"],  # Repaired never jumps to Provisional
    ["transfer_correct"],                            # transfer requires prior evidence
])
def test_illegal(events):
    t = ConceptTracker(["C1"])
    with pytest.raises(IllegalTransition):
        for e in events:
            t.apply("C1", e)


def test_consolidated_disabled_by_default():
    t = ConceptTracker(["C1"])
    t.apply("C1", "correct_first")
    t.apply("C1", "transfer_correct")
    with pytest.raises(IllegalTransition, match="proposed"):
        t.apply("C1", "independent_correct")
    t2 = ConceptTracker(["C1"], enable_consolidated=True)
    for e in ("correct_first", "transfer_correct", "independent_correct"):
        t2.apply("C1", e)
    assert t2.states["C1"] == State.CONSOLIDATED
