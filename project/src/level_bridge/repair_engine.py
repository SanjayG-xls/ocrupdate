"""Repair feedback and the Understanding Safety Net (core: word card + worked example).

Repair text is built deterministically from the error code, the passage sentence and
the Python solution. Optional LLM wording (``repair.llm_wording``) is accepted only if
it validates and still contains the correct answer; otherwise the template is used.
The Safety Net's representation switch and prerequisite check are extensions and are
reported as not implemented.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from .concept_validator import ConceptValidator
from .key_term_registry import KeyTermRegistry
from .knowledge_map import KnowledgeMap
from .misconception_detector import Evaluation
from .model_runtime import ModelRuntime
from .question_generator import Item
from .quantity_parser import fmt_number, parse_numbers, display_unit


@dataclass
class Repair:
    item_id: str
    error_code: Optional[str]
    lines: List[str]
    source: str                # template | llm
    latency_s: float = 0.0

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class SafetyNet:
    concept_id: str
    word_card: Optional[Dict[str, str]]
    worked_example: Optional[List[str]]
    extensions_not_implemented: List[str] = field(default_factory=lambda: ["representation_switch", "prerequisite_check"])

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class RepairEngine:
    def __init__(self, km: KnowledgeMap, registry: KeyTermRegistry, validator: ConceptValidator,
                 runtime: Optional[ModelRuntime] = None, llm_wording: bool = False, max_new_tokens: int = 120) -> None:
        self.km, self.registry, self.validator = km, registry, validator
        self.runtime, self.llm_wording, self.max_new_tokens = runtime, llm_wording, max_new_tokens

    def _sentence(self, sid: str) -> str:
        return next((s["text"] for s in self.km.sentences if s["sid"] == sid), "")

    def template_lines(self, item: Item, ev: Evaluation) -> List[str]:
        code = ev.error_code
        lines: List[str] = []
        if item.response_type == "numeric":
            sol = ev.details["solution"]
            me = ev.details.get("matched_error")
            fsid = item.source_sids[0]
            if me:
                lines.append(f"Your answer {fmt_number(me['value']) if me['value'] == me['value'] else me['value']} "
                             f"matches the error \"{me['code'].replace('_', ' ')}\".")
                lines.append(me["explanation"])
            elif ev.details.get("unit_issue"):
                lines.append(ev.details["unit_issue"])
            else:
                lines.append(f"Your answer {ev.response} is not correct.")
            lines.append(f"Use the rule from {fsid}: {sol['formula']}.")
            lines.extend(sol["conversions"] and [f"First convert: {c}" for c in sol["conversions"]] or [])
            lines.append(f"{sol['substitution']}  ->  {sol['answer_text']}.")
            return lines
        co = item.correct_option()
        if code == "term_confusion":
            lines.append(f"\"{ev.chosen_text}\" describes a different term.")
        elif code == "reversed_relation":
            lines.append("That reverses the relationship.")
        elif code == "no_change":
            lines.append("The quantities differ, so the result cannot be the same.")
        elif code == "missing_variable":
            lines.append("All the information needed is given in the question.")
        elif code == "dimension_confusion":
            lines.append(f"\"{ev.chosen_text}\" measures a different kind of quantity.")
        elif code == "wrong_variable":
            lines.append(f"\"{ev.chosen_text}\" is one of the inputs, not the term asked about.")
        else:
            lines.append("That is not correct.")
        lines.append(f"Correct answer: {co.text}. {item.explanation}")
        return lines

    def repair(self, item: Item, ev: Evaluation) -> Repair:
        t0 = time.perf_counter()
        lines = self.template_lines(item, ev)
        source = "template"
        if self.llm_wording and self.runtime is not None and self.runtime.is_llm:
            prompt = ("Rewrite this feedback for a Class 7 student in at most 3 short sentences. Keep every number, unit and "
                      "the formula exactly. Do not add facts.\n\n" + "\n".join(lines))
            res = self.runtime.generate(prompt, self.max_new_tokens)
            if res.ok:
                nums = set(parse_numbers(" ".join(lines)))
                rep = self.validator.validate(res.text, "repair", extra_numbers=nums,
                                              extra_pairs=self._pairs(item))
                must = ev.expected or ""
                if rep.passed and must and must.split()[0] in res.text:
                    lines, source = [res.text], "llm"
        return Repair(item.item_id, ev.error_code, lines, source, time.perf_counter() - t0)

    @staticmethod
    def _pairs(item: Item):
        pairs = set()
        if item.numeric:
            for k in ("numerator", "denominator"):
                q = item.numeric["inputs"][k]
                pairs.add((q["value"], q["unit"]))
            s = item.numeric["solution"]
            pairs.add((s["value"], s["unit"]))
        return pairs

    def safety_net(self, concept_id: str) -> SafetyNet:
        c = self.km.concept(concept_id)
        card = None
        term = c.ref.get("definition")
        if term:
            d = self.km.definition(term)
            card = {"term": d.term, "meaning": d.meaning, "source": f"{d.sid}: {self._sentence(d.sid)}"}
        elif c.ref.get("formula"):
            e = self.registry.get(c.label.lower()) if any(x.canonical == c.label.lower() for x in self.registry.entries) else None
            card = {"term": c.label, "meaning": e.meaning if e else c.label, "source": f"{c.sids[0]}: {self._sentence(c.sids[0])}"}
        worked = None
        if self.km.examples:
            ex = self.km.examples[0]
            n, d_ = ex.numerator, ex.denominator
            worked = [f"Example from {ex.sid}: {fmt_number(n['value'])} {display_unit(n['unit'])} in "
                      f"{fmt_number(d_['value'])} {display_unit(d_['unit'])}.",
                      f"step 1  {self.km.formulas[0].text}" if self.km.formulas else "step 1  read the rule",
                      f"step 2  {fmt_number(n['value'])} ÷ {fmt_number(d_['value'])} = {fmt_number(ex.stated['value'])}",
                      f"step 3  answer: {ex.computed}"]
        return SafetyNet(concept_id, card, worked)
