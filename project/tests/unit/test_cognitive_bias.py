"""Explanation support (rung) and cognitive level are independent (report p.3)."""
from level_bridge.question_generator import QuestionGenerator


def test_recall_item_can_be_scheduled_at_l3(artifacts, cfg):
    qg = QuestionGenerator(artifacts.km, cfg.item_contexts)
    it = qg.definition_item("X1", artifacts.km.definition("speedometer"), "assessment", "recall", 3)
    assert (it.rung, it.cognitive_level) == (3, "recall")


def test_apply_item_can_be_scheduled_at_l1(artifacts, cfg):
    qg = QuestionGenerator(artifacts.km, cfg.item_contexts)
    it = qg.numeric_item("X2", "assessment", "assessment", "apply", 1)
    assert (it.rung, it.cognitive_level) == (1, "apply")
    assert it.numeric["solution"]["value"] == 60


def test_credits_depend_on_level_not_rung(ledger):
    a = ledger.record_assessment("a", "assessment", "apply", True, 3)    # at L1
    b = ledger.record_assessment("b", "assessment", "recall", True, 3)   # at L3
    assert a.assessment_credits > b.assessment_credits
