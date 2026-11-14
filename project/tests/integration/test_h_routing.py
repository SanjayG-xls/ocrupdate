"""Sequences H and M – routing, repair, second chance, step-down, bridge (Meena 4 km/h)."""
from level_bridge.answer_providers import scripted_provider
from level_bridge.main import _run_session
from level_bridge.model_runtime import TemplateRuntime


def _run(cfg, artifacts, answers):
    res, tracker, ledger = _run_session(cfg, artifacts, TemplateRuntime(), scripted_provider(answers))
    return res, tracker, ledger


def _routes(res):
    return [(e["rule"], e["decision"]) for e in res.events if e["type"] == "route"]


ALL_OK = {k: {"select": "correct", "certainty": 3} for k in ("P1", "P2", "P3", "Q1", "Q3", "Q4")}


def test_priya_end_to_end(cfg, artifacts, priya_script):
    res, tracker, ledger = _run(cfg, artifacts, priya_script["answers"])
    exp = priya_script["expected"]
    s = ledger.summary()
    for k in ("assessment_credits", "assessment_max", "recovery_credits", "total_earned", "cbm_total", "cbm_max"):
        assert s[k] == exp[k], k
    assert res.placement["score"] == 1 and res.rung_path == [1, 2, 3]
    assert _routes(res) == [("R3", "climb"), ("R3", "climb"), ("R4", "bridge")]
    assert tracker.states["C3"].value == "Transferred"
    assert [h["to"] for h in tracker.history["C3"]] == ["Fragile", "Repaired", "Transferred"]
    rep = next(e for e in res.events if e["type"] == "repair")
    assert rep["error_code"] == "wrong_operation_multiply"


def test_all_correct_placement_3_starts_at_l3(cfg, artifacts):
    ans = {**ALL_OK, "T1": {"value": "4 km/h", "certainty": 3}}
    res, _, _ = _run(cfg, artifacts, ans)
    assert res.rung_path == [3] and res.bridge_reached
    bridge = next(e for e in res.events if e["type"] == "bridge")
    assert bridge["verbatim"] and bridge["extract_sids"] == ["S3", "S4"]


def test_bridge_meena_wrong_triggers_repair(cfg, artifacts):
    ans = {**ALL_OK, "T1": {"value": "60 km/h", "certainty": 2}}
    res, tracker, _ = _run(cfg, artifacts, ans)
    t1 = [e for e in res.events if e["type"] == "item" and e["item"] == "T1"][0]
    assert not t1["correct"] and tracker.states["C3"].value == "Fragile"
    assert any(e["type"] == "repair" and e["item"] == "T1" for e in res.events)


def test_repair_failure_safety_net_and_end(cfg, artifacts):
    ans = {"P1": {"select": "correct"}, "P2": {"select": "error:term_confusion"}, "P3": {"select": "error:no_change"},
           "Q1": {"select": "correct", "certainty": 2}, "Q2": {"value": "540", "certainty": 3},
           "Q2b": {"value": "48", "certainty": 3}}
    res, tracker, ledger = _run(cfg, artifacts, ans)
    assert any(e["type"] == "safety_net" for e in res.events)
    assert res.teacher_notes and "unresolved" in res.end_reason
    assert tracker.states["C3"].value == "Fragile" and not res.bridge_reached
    assert ledger.recovery_credits == 0


def test_two_unresolved_at_l2_step_down_then_end(cfg, artifacts):
    ans = {"P1": {"select": "correct"}, "P2": {"select": "correct"}, "P3": {"select": "error:reversed_relation"},
           "Q3": {"select": "error:term_confusion", "certainty": 2}, "Q3b": {"select": "error:term_confusion"},
           "Q4": {"select": "error:reversed_relation", "certainty": 3}, "Q4b": {"select": "error:reversed_relation"},
           "Q1": {"select": "correct"}, "Q2": {"value": "60 km/h"}}
    res, _, _ = _run(cfg, artifacts, ans)
    assert res.rung_path[:2] == [2, 1]
    assert ("R3", "step_down") in _routes(res)
    # L1 then resolved -> climb back to L2, whose items were already delivered -> session ends (documented)
    assert "already delivered" in res.end_reason and not res.bridge_reached


def test_two_unresolved_at_l1_ends_with_teacher_note(cfg, artifacts):
    ans = {"P1": {"select": "error:dimension_confusion"}, "P2": {"select": "error:term_confusion"},
           "P3": {"select": "error:no_change"}, "Q1": {"select": "error:term_confusion"},
           "Q1b": {"select": "error:term_confusion"}, "Q2": {"value": "540"}, "Q2b": {"value": "48"}}
    res, _, _ = _run(cfg, artifacts, ans)
    assert res.placement["score"] == 0 and res.rung_path == [1]
    assert "unresolved errors at L1" in res.end_reason and len(res.teacher_notes) == 2


def test_repair_success_l1_to_l2(cfg, artifacts, priya_script):
    res, _, _ = _run(cfg, artifacts, priya_script["answers"])
    sc = next(e for e in res.events if e["type"] == "second_chance")
    assert sc["correct"] and sc["state"] == "Repaired" and sc["recovery"] == 3


def test_low_certainty_correct_is_flagged(cfg, artifacts, priya_script):
    _, tracker, _ = _run(cfg, artifacts, priya_script["answers"])
    assert any("low certainty" in f for f in tracker.flags["C2"])
