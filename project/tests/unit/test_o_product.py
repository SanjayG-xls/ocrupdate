"""Teach · Learn · Improve (report Section 7). All tests run WITHOUT a model and WITHOUT a Raspberry Pi."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from level_bridge.answer_providers import load_script, scripted_provider
from level_bridge.cbs_portal import class_summary, load_profiles, render_portal
from level_bridge.formula_engine import FORMULAS, compute, detect_formula, error_models
from level_bridge.learner_memory import (LearnerIdError, check_learner_id, load_profile, patterns, record_session,
                                         session_record)
from level_bridge.learning_report import build_report
from level_bridge.lesson_pack import PackError, apply_review, approved, make_pack, read_pack, replay, write_pack
from level_bridge.main import _run_session, main
from level_bridge.model_runtime import TemplateRuntime
from level_bridge.pipeline import analyse, build
from level_bridge.profile_bundle import BundleError, export_bundle, import_bundles, read_bundle
from level_bridge.quantity_parser import Quantity, parse_quantities
from level_bridge.source_tags import best_source, tag_text

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "data" / "passages"
T = ROOT / "data" / "test_cases"
PASSAGES = ["speed", "density", "pressure", "ohms_law", "power"]


# ------------------------------------------------------------------ 7.4 formula library and detection
@pytest.mark.parametrize("sentence,key", [
    ("Speed is calculated by dividing the total distance covered by the total time taken.", "speed"),
    ("Density is calculated by dividing the mass of an object by its volume.", "density"),
    ("Pressure = force ÷ area.", "pressure"),
    ("Pressure is found by dividing the force acting on a surface by the area of that surface.", "pressure"),
    ("Resistance is the potential difference divided by the current.", "resistance"),
    ("Dividing the work done by the time taken gives the power.", "power"),
    ("Power is the ratio of work to time.", "power"),
])
def test_formula_phrasings_detected(sentence, key):
    f = detect_formula(sentence)
    assert f is not None and f.key == key


@pytest.mark.parametrize("sentence", [
    "Speed helps us plan journeys.", "The mass of an object is the amount of matter it contains.",
    "Speed is calculated by dividing the time by the distance.",   # reversed: not the library formula
])
def test_no_false_formula(sentence):
    assert detect_formula(sentence) is None


@pytest.mark.parametrize("key,a,b,target,value", [
    ("pressure", (50, "N"), (200, "cm2"), "Pa", 2500.0),
    ("resistance", (6, "V"), (500, "mA"), "ohm", 12.0),
    ("power", (1.2, "kJ"), (1, "min"), "W", 20.0),
    ("density", (0.06, "kg"), (100, "cm3"), "g/cm3", 0.6),
])
def test_new_formulas_compute_with_conversion(key, a, b, target, value):
    f = FORMULAS[key]
    sol = compute(f, Quantity(*a), Quantity(*b), target)
    assert abs(sol.value - value) < 1e-6
    assert sol.conversions, "transfer contexts must need a unit conversion"
    codes = {m.code for m in error_models(f, Quantity(*a), Quantity(*b), target)}
    assert {"wrong_operation_multiply", "inverted_formula", "ignored_variable", "unit_not_converted"} <= codes


def test_error_models_never_equal_correct_answer():
    f = FORMULAS["density"]
    a, b = Quantity(540, "g"), Quantity(200, "cm3")
    sol = compute(f, a, b, "g/cm3")
    for m in error_models(f, a, b, "g/cm3"):
        assert abs(m.value - sol.value) > 0.01 * max(1, sol.value)


def test_capital_a_is_ampere_but_article_a_is_not():
    units = [m.quantity.unit for m in parse_quantities("A 12 V cell drives 2 A; in 2 a day")]
    assert units == ["V", "A"]


# ------------------------------------------------------------------ robustness on unseen passages
@pytest.mark.parametrize("name", PASSAGES)
def test_practice_passages_extract_formula_example_and_relations(cfg, name):
    _, km, registry, _ = analyse(cfg, P / f"{name}_passage.txt")
    assert km.formulas, "formula not extracted"
    assert km.examples and km.examples[0].verified, "worked example not verified"
    assert len(km.relationships) == 2 and all(r.consistent_with_formula for r in km.relationships)
    assert any(e.category == "formula" for e in registry.required())


@pytest.mark.parametrize("name", PASSAGES)
def test_practice_passages_templates_pass_gate(cfg, name):
    art = build(cfg, P / f"{name}_passage.txt", TemplateRuntime())
    for k in ("summary", "l1", "l2"):
        assert art.explanations[k].validated, (name, k, art.explanations[k].validation)
    assert "an density" not in art.explanations["l2"].text and " a area" not in art.explanations["l1"].text
    kinds = {it.kind for it in art.bank.items}
    assert {"placement", "assessment", "second_chance", "transfer"} <= kinds


# ------------------------------------------------------------------ LEARN: source tags
def test_source_tags_point_to_the_right_sentence(cfg):
    art = build(cfg, P / "speed_passage.txt", TemplateRuntime())
    sents = [(s.sid, s.text) for s in art.passage.sentences]
    assert best_source("Speed = distance ÷ time.", sents, km=art.km) == "S3"
    assert best_source("If the distance is the same, less time means higher speed.", sents, km=art.km) == "S7"
    assert best_source("Example: a bus covers 120 km in 2 h.", sents, km=art.km) == "S5"
    tagged = tag_text(art.explanations["l1"].text, art.passage, art.km)
    assert re.search(r"\[S\d+\]", tagged)
    dens = build(cfg, P / "density_passage.txt", TemplateRuntime())
    ds = [(s.sid, s.text) for s in dens.passage.sentences]
    assert best_source("If the mass is the same, less volume means higher density.", ds, km=dens.km) == "S9"


def test_source_tags_do_not_change_validated_text(cfg):
    art = build(cfg, P / "speed_passage.txt", TemplateRuntime())
    before = art.explanations["l1"].text
    tag_text(before, art.passage, art.km)
    assert art.explanations["l1"].text == before


# ------------------------------------------------------------------ IMPROVE: learner memory
@pytest.mark.parametrize("bad", ["Priya", "Priya Kumar", "STU-7", "stu 7f3a", ""])
def test_learner_id_rejects_names(bad):
    with pytest.raises(LearnerIdError):
        check_learner_id(bad)


def _session(cfg, passage, script, sid):
    art = build(cfg, P / passage, TemplateRuntime())
    result, tracker, ledger = _run_session(cfg, art, TemplateRuntime(), scripted_provider(load_script(T / script)))
    report = build_report(art.km, tracker, ledger, result, {"run_id": sid})
    return session_record(sid, art, result, report)


def test_recurring_pattern_across_two_passages(cfg, tmp_path):
    record_session(tmp_path, "STU-7F3A", _session(cfg, "speed_passage.txt", "priya_answers.json", "s1"), consent=True)
    prof = record_session(tmp_path, "STU-7F3A", _session(cfg, "density_passage.txt", "priya_density_answers.json", "s2"))
    pat = patterns(prof)
    assert pat["sessions"] == 2 and pat["passages"] == ["density", "speed"]
    assert [r["family"] for r in pat["recurring"]] == ["wrong_operation"]
    assert pat["confident_errors"] == 2
    assert pat["totals"]["assessment"] == 25 + 26


def test_one_passage_is_not_a_pattern(cfg, tmp_path):
    prof = record_session(tmp_path, "STU-7F3A", _session(cfg, "speed_passage.txt", "priya_answers.json", "s1"))
    assert patterns(prof)["recurring"] == []


def test_session_record_is_idempotent(cfg, tmp_path):
    rec = _session(cfg, "speed_passage.txt", "priya_answers.json", "s1")
    record_session(tmp_path, "STU-7F3A", rec)
    prof = record_session(tmp_path, "STU-7F3A", rec)
    assert len(prof["sessions"]) == 1


def test_profile_holds_no_names_or_free_text(cfg, tmp_path):
    record_session(tmp_path, "STU-7F3A", _session(cfg, "speed_passage.txt", "priya_answers.json", "s1"))
    raw = (tmp_path / "STU-7F3A.json").read_text()
    assert "Priya" not in raw and "priya_answers" not in raw


# ------------------------------------------------------------------ IMPROVE: USB bundles
def test_export_refused_without_consent(cfg, tmp_path):
    record_session(tmp_path / "dev", "STU-7F3A", _session(cfg, "speed_passage.txt", "priya_answers.json", "s1"))
    with pytest.raises(BundleError, match="consent"):
        export_bundle(tmp_path / "dev", "STU-7F3A", tmp_path / "usb")


def test_bundle_round_trip_tamper_and_dedupe(cfg, tmp_path):
    record_session(tmp_path / "dev", "STU-7F3A", _session(cfg, "speed_passage.txt", "priya_answers.json", "s1"), consent=True)
    b = export_bundle(tmp_path / "dev", "STU-7F3A", tmp_path / "usb")
    assert read_bundle(b)["learner_id"] == "STU-7F3A"
    r1 = import_bundles([b], tmp_path / "hub")
    r2 = import_bundles([b], tmp_path / "hub")
    assert r1[0]["sessions_added"] == 1 and r2[0]["sessions_added"] == 0
    data = json.loads(b.read_text())
    data["payload"]["sessions"][0]["scores"]["assessment_credits"] = 36
    bad = tmp_path / "usb" / "tampered.lbprofile.json"
    bad.write_text(json.dumps(data))
    res = import_bundles([bad], tmp_path / "hub")
    assert not res[0]["ok"] and "checksum" in res[0]["error"]
    assert load_profile(tmp_path / "hub", "STU-7F3A")["sessions"][0]["scores"]["assessment_credits"] == 25


# ------------------------------------------------------------------ IMPROVE: CBS portal
def test_portal_numbers_and_offline_html(cfg, tmp_path):
    record_session(tmp_path, "STU-7F3A", _session(cfg, "speed_passage.txt", "priya_answers.json", "s1"), consent=True)
    record_session(tmp_path, "STU-7F3A", _session(cfg, "density_passage.txt", "priya_density_answers.json", "s2"))
    record_session(tmp_path, "STU-M4Q8", _session(cfg, "speed_passage.txt", "meena_speed_answers.json", "s3"), consent=True)
    s = class_summary(load_profiles(tmp_path))
    assert s["passage_students"] == {"density": 1, "speed": 2}
    assert s["heatmap"]["wrong_operation|speed"] == 2
    top = s["reteach"][0]
    assert (top["family"], top["passage"], top["students"], top["of"], top["sids"]) == ("wrong_operation", "speed", 2, 2, ["S3"])
    page = render_portal(s)
    assert "STU-7F3A" in page and "Priya" not in page
    assert not re.search(r"(src|href)=[\"']https?://", page), "portal must not load anything from the network"


# ------------------------------------------------------------------ TEACH: lesson packs and review
def _pack(cfg, tmp_path, name="speed"):
    art = build(cfg, P / f"{name}_passage.txt", TemplateRuntime())
    return write_pack(make_pack(art, {"backend": "template", "is_llm": False}, art), tmp_path / f"{name}.lbpack.json")


def test_pack_checksum_and_tamper(cfg, tmp_path):
    path = _pack(cfg, tmp_path)
    pack = read_pack(path)
    assert not approved(pack)
    data = json.loads(path.read_text())
    data["payload"]["explanations"]["l1"]["text"] = "Speed is distance times time."
    path.write_text(json.dumps(data))
    with pytest.raises(PackError, match="checksum"):
        read_pack(path)


def test_teacher_edit_must_pass_gate(cfg, tmp_path):
    pack = read_pack(_pack(cfg, tmp_path))
    with pytest.raises(PackError, match="validation gate"):
        apply_review(cfg, pack, "l1", "edit", "Speed is how fast something goes.")
    assert pack["payload"]["review"]["l1"]["status"] == "pending"
    good = pack["payload"]["explanations"]["l1"]["text"].replace("Speed tells us", "Speed means")
    apply_review(cfg, pack, "l1", "edit", good)
    assert pack["payload"]["explanations"]["l1"]["source"] == "teacher_edited"
    for k in ("summary", "l2"):
        apply_review(cfg, pack, k, "approve")
    assert approved(pack)
    write_pack(pack, tmp_path / "speed.lbpack.json")
    assert read_pack(tmp_path / "speed.lbpack.json")["payload"]["review"]["l1"]["status"] == "edited"


def test_pack_replay_is_model_free_and_reproduces_priya(cfg, tmp_path):
    pack = read_pack(_pack(cfg, tmp_path))
    art = replay(cfg, pack)
    assert [it.item_id for it in art.bank.items] == pack["payload"]["item_ids"]
    result, tracker, ledger = _run_session(cfg, art, TemplateRuntime(), scripted_provider(load_script(T / "priya_answers.json")))
    s = ledger.summary()
    assert (s["assessment_credits"], s["assessment_max"], s["recovery_credits"], s["cbm_total"]) == (25, 36, 3, 6)


def test_cli_end_to_end_teach_learn_improve(cfg, tmp_path):
    pk = tmp_path / "speed.lbpack.json"
    assert main(["pack-build", "--backend", "template", "--out", str(pk)]) == 0
    assert main(["pack-review", "--pack", str(pk), "--approve-all"]) == 0
    prod = cfg.app["product"]
    old = dict(prod)
    prod.update(learners_dir=str(tmp_path / "dev"), hub_dir=str(tmp_path / "hub"))
    try:
        assert main(["session", "--pack", str(pk), "--answers", "data/test_cases/priya_answers.json",
                     "--learner", "STU-7F3A", "--consent", "--run-id", "pytest_pack"]) == 0
        assert main(["session", "--pack", str(pk), "--answers", "data/test_cases/priya_answers.json",
                     "--learner", "Priya", "--run-id", "pytest_name"]) == 2
        assert main(["profile-export", "--learner", "STU-7F3A", "--out", str(tmp_path / "usb")]) == 0
        assert main(["hub-import", "--dir", str(tmp_path / "usb")]) == 0
        assert main(["portal", "--out", str(tmp_path / "portal.html")]) == 0
    finally:
        prod.clear()
        prod.update(old)
    assert "STU-7F3A" in (tmp_path / "portal.html").read_text()


# ------------------------------------------------------------------ report 5.3: question-rewording check
@pytest.mark.parametrize("bad", [
    "The basic unit of speed is the meter.",                     # P1 on the Pi 500: statement
    "Asha and Ravi both travel 10 km. Asha takes 30 min and Ravi takes 40 min. Therefore, Asha is faster.",  # P3
    "In 1 h, bus X covers 50 km and bus Y covers 65 km. Bus X has a higher average speed.",  # Q4
])
def test_bad_rewordings_from_device_log_are_rejected(cfg, bad):
    from level_bridge.question_generator import _valid_stem
    art = build(cfg, P / "speed_passage.txt", TemplateRuntime())
    for it in art.bank.items:
        ok, _ = _valid_stem(it, bad)
        assert not ok


def test_good_rewording_still_accepted(cfg):
    from level_bridge.question_generator import _valid_stem
    art = build(cfg, P / "speed_passage.txt", TemplateRuntime())
    q2 = art.bank.by_id("Q2")
    new = q2.template_stem.replace("What is the average speed", "Find the average speed").replace("? (type", "? (type")
    assert _valid_stem(q2, new)[0]


# ------------------------------------------------------------------ live-round demo: gate-report and compare
def test_extract_answer_from_free_text():
    from level_bridge.trust_demo import extract_answer
    assert extract_answer("speed = 180 ÷ 3 = 60 km/h.") == "60 km/h"
    assert extract_answer("The answer is 540 km/h") == "540 km/h"
    assert extract_answer("about 0.6 g/cm3") == "0.6 g/cm3"
    assert extract_answer("no idea") is None


def test_compare_marks_ai_errors_with_python_diagnosis(cfg):
    from level_bridge.model_runtime import ScriptedRuntime
    from level_bridge.trust_demo import ai_alone, render_compare

    def fake(prompt):
        if "Summarise" in prompt:
            return "Speed is how fast a car goes. A bus goes 150 km in 2 hours."   # drops terms, invents 150
        if "letter" in prompt:
            return "A"
        return "540 km/h" if "180 km" in prompt else "12 km/h"

    art = build(cfg, P / "speed_passage.txt", TemplateRuntime())
    r = ai_alone(art, ScriptedRuntime(fn=fake))
    q2 = next(i for i in r["items"] if i["item"] == "Q2")
    assert q2["ai_answer"] == "540 km/h" and not q2["ai_correct"] and q2["ai_error"] == "wrong_operation_multiply"
    assert q2["level_bridge"] == "60 km/h"
    assert r["summary"]["passed_gate"] is False and r["summary"]["checks"]
    text = "\n".join(render_compare(r, "scripted"))
    assert "AI alone" in text and "Level Bridge" in text


def test_gate_report_shows_rejected_draft_and_reasons(cfg):
    from level_bridge.explanation_generator import ExplanationGenerator
    from level_bridge.model_runtime import ScriptedRuntime
    from level_bridge.trust_demo import gate_report
    passage, km, registry, validator = analyse(cfg, P / "speed_passage.txt")
    ex = cfg.app["explanations"]
    rt = ScriptedRuntime(fn=lambda p: "Speed is how fast something moves. A bus goes 150 km in 2 hours.")
    gen = ExplanationGenerator(passage, km, registry, validator, rt, ex["max_attempts"], ex["max_new_tokens"])
    exps = {k: v.to_dict() for k, v in gen.build_all().items()}
    assert exps["l1"]["attempts"][0]["draft"].startswith("Speed is how fast")
    lines = "\n".join(gate_report(exps, "scripted"))
    assert "REJECTED" in lines and "model draft" in lines and "validated template" in lines


def test_compare_refuses_without_model():
    assert main(["compare", "--backend", "template"]) == 2
