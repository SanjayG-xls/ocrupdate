"""Sequence E – L1/L2/L3 generation: validation, one retry, template fallback."""
from conftest import load_fixture

from level_bridge.explanation_generator import ExplanationGenerator
from level_bridge.model_runtime import ScriptedRuntime, TemplateRuntime

FX = load_fixture("llm_outputs.json")


def _gen(analysed, runtime):
    passage, km, reg, v = analysed
    return ExplanationGenerator(passage, km, reg, v, runtime, max_attempts=2)


def test_first_attempt_accepted(analysed):
    e = _gen(analysed, ScriptedRuntime([FX["good_l2"]])).generate("l2")
    assert e.source == "llm" and e.validated and len(e.attempts) == 1


def test_retry_after_invalid_output(analysed):
    rt = ScriptedRuntime([FX["wrong_formula_l2"], FX["good_l2"]])
    e = _gen(analysed, rt).generate("l2")
    assert e.source == "llm_retry" and e.validated and len(e.attempts) == 2
    assert "rejected because" in rt.prompts[1]           # retry carries the validator feedback


def test_two_failures_fall_back_to_template(analysed):
    e = _gen(analysed, ScriptedRuntime([FX["wrong_number_l2"], FX["reversed_relation_l2"]])).generate("l2")
    assert e.source == "template" and e.fallback
    assert len(e.attempts) == 2 and not any(a.validation and a.validation["passed"] for a in e.attempts)


def test_failed_generation_never_reported_as_validated_llm(analysed):
    e = _gen(analysed, ScriptedRuntime([RuntimeError("boom"), ""])).generate("summary")
    assert e.source == "template"
    assert all(not a.generation_ok for a in e.attempts)


def test_template_backend_makes_no_llm_claim(analysed):
    out = _gen(analysed, TemplateRuntime()).build_all()
    assert {k: v.source for k, v in out.items()} == {"summary": "template", "l1": "template", "l2": "template", "l3": "original"}
    assert all(v.validated for v in out.values())         # templates themselves pass validation
    assert all(not v.attempts for v in out.values())


def test_l3_is_original_with_separate_glosses(analysed):
    passage = analysed[0]
    e = _gen(analysed, TemplateRuntime()).l3()
    assert e.text == passage.text and e.glosses
