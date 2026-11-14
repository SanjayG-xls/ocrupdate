"""Sequence F – item bank: keys, explanations, source refs, labels; level independent of rung."""


def test_bank_composition(artifacts):
    comp = artifacts.bank.composition()
    assert comp == {"placement": 3, "assessment": 4, "second_chance": 4, "transfer": 1, "total": 12}


def test_every_item_is_complete_and_grounded(artifacts):
    sids = {s.sid for s in artifacts.passage.sentences}
    cids = {c.cid for c in artifacts.km.concepts}
    for it in artifacts.bank.items:
        assert it.stem and it.explanation and it.concept_id in cids
        assert it.source_sids and set(it.source_sids) <= sids
        assert it.knowledge_type in ("definition", "quantitative", "cause_effect")
        if it.kind != "placement":
            assert it.cognitive_level in ("recall", "understand", "apply", "transfer")
        if it.response_type == "mcq":
            assert sum(o.correct for o in it.options) == 1 and it.answer_key == it.correct_option().key
        else:
            assert it.numeric["solution"]["answer_text"]


def test_l1_can_ask_apply_and_l3_can_recall(artifacts):
    levels = {(it.rung, it.cognitive_level) for it in artifacts.bank.items if it.kind == "assessment"}
    assert (1, "apply") in levels                     # low support, high cognitive level
    assert (2, "recall") in levels


def test_transfer_uses_simple_wording(artifacts):
    t = artifacts.bank.of_kind("transfer")[0]
    assert t.cognitive_level == "transfer" and len(t.stem.split()) <= 25


def test_numeric_answers_come_from_python(artifacts):
    q2 = artifacts.bank.by_id("Q2")
    assert q2.numeric["solution"]["value"] == 60
    assert q2.numeric["solution"]["unit"] == "km/h"
    assert 540 not in [o.text for o in q2.options]        # numeric entry, no invalid distractors


def test_llm_stem_rewording_validated(artifacts):
    from level_bridge.model_runtime import ScriptedRuntime
    from level_bridge.question_generator import reword_stems
    bank = artifacts.bank
    lines = []
    for n, it in enumerate(bank.items, start=1):
        lines.append(f"{n}. {it.stem.replace('180 km', '200 km') if it.item_id == 'Q2' else 'Please answer: ' + it.stem}")
    rep = reword_stems(bank, ScriptedRuntime(["\n".join(lines)]))
    assert rep["reasons"]["Q2"] == "numbers changed"
    assert bank.by_id("Q2").stem_source == "template"
