"""Sequence D – knowledge map, key-term registry and validator checks."""
import pytest

from conftest import load_fixture

EXPECTED_TERMS = ["speed", "speed = distance ÷ time", "m/s", "km/h", "average speed", "speedometer", "odometer"]


def test_knowledge_map_core_types(analysed):
    _, km, _, _ = analysed
    assert km.type_counts() == {"definition": 4, "quantitative": 4, "cause_effect": 1}
    assert km.primary_formula().text == "speed = distance ÷ time"


def test_registry_has_seven_entries(analysed):
    _, _, reg, _ = analysed
    assert [e.canonical for e in reg.required()] == EXPECTED_TERMS
    assert "motion" not in [e.canonical for e in reg.entries]  # state definition: knowledge map only


def test_registry_synonyms(analysed):
    _, _, reg, _ = analysed
    from level_bridge.key_term_registry import term_present
    assert term_present(reg.get("km/h"), "measured in kilometres per hour")
    assert term_present(reg.get("speed = distance ÷ time"), "divide the distance by the time")


@pytest.mark.parametrize("key,check", [
    ("missing_terms_l2", "key_term_coverage"),
    ("wrong_formula_l2", "formula_preserved"),
    ("wrong_number_l2", "numerical_consistency"),
    ("wrong_unit_l2", "unit_consistency"),
    ("reversed_relation_l2", "relationship_direction"),
    ("unsupported_l2", "unsupported_content"),
    ("malformed", "well_formed"),
    ("empty", "well_formed"),
])
def test_validator_rejects(analysed, key, check):
    _, _, _, v = analysed
    rep = v.validate(load_fixture("llm_outputs.json")[key], "l2")
    assert not rep.passed
    assert check in [c.name for c in rep.failures()]


@pytest.mark.parametrize("key,kind", [("good_summary", "summary"), ("good_l2", "l2")])
def test_validator_accepts_faithful_text(analysed, key, kind):
    _, _, _, v = analysed
    assert v.validate(load_fixture("llm_outputs.json")[key], kind).passed


def test_l3_must_be_unchanged(analysed):
    passage, _, _, v = analysed
    assert v.validate(passage.text, "l3").passed
    assert not v.validate(passage.text.replace("120", "130"), "l3").passed


def test_l1_sentence_length_rule(analysed):
    _, _, _, v = analysed
    long = ("Speed is the distance an object covers in a unit of time and it is usually measured on roads "
            "in km/h while scientists prefer m/s.")
    rep = v.validate(long, "l1")
    assert "l1_short_sentences" in [c.name for c in rep.failures()]
