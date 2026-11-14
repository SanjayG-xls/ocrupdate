"""Summary and three-rung explanation ladder (L1 step-by-step, L2 simplified, L3 original + glosses).

For summary/L1/L2: LLM generation -> Python validation -> accept, or retry once,
then a deterministic template built from the knowledge map. L3 is never rewritten:
it is the original passage, with vocabulary glosses kept in a separate list.

Every result records its ``source`` (llm | llm_retry | template | original) and the
validation report of the text that was actually accepted. A failed generation is
never reported as validated.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from .concept_validator import ConceptValidator, ValidationReport
from .formula_engine import FORMULAS
from .key_term_registry import KeyTermRegistry
from .knowledge_map import KnowledgeMap
from .model_runtime import GenerationResult, ModelRuntime
from .passage_processor import Passage
from .quantity_parser import fmt_number, display_unit

log = logging.getLogger("level_bridge.explanations")


@dataclass
class Attempt:
    number: int
    backend: str
    generation_ok: bool
    error: Optional[str]
    validation: Optional[Dict[str, object]]
    wall_time_s: float
    ttft_ms: Optional[float] = None
    generated_tokens: Optional[int] = None
    draft: Optional[str] = None       # the model's text for this attempt (shown by `gate-report`)


@dataclass
class Explanation:
    kind: str                         # summary | l1 | l2 | l3
    text: str
    source: str                       # llm | llm_retry | template | original
    validated: bool
    validation: Dict[str, object]
    attempts: List[Attempt] = field(default_factory=list)
    glosses: List[Dict[str, str]] = field(default_factory=list)

    @property
    def fallback(self) -> bool:
        return self.source == "template"

    def to_dict(self) -> Dict[str, object]:
        d = asdict(self)
        d["fallback_generated"] = self.fallback
        return d


def _cap(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


def _article(w: str) -> str:
    return "An" if w[:1].lower() in "aeiou" else "A"


class ExplanationGenerator:
    """Builds the summary and L1-L3 explanations for one passage."""

    def __init__(self, passage: Passage, km: KnowledgeMap, registry: KeyTermRegistry, validator: ConceptValidator,
                 runtime: ModelRuntime, max_attempts: int = 2, max_new_tokens: Optional[Dict[str, int]] = None) -> None:
        self.passage, self.km, self.registry, self.validator = passage, km, registry, validator
        self.runtime = runtime
        self.max_attempts = max(1, int(max_attempts))
        self.max_new_tokens = max_new_tokens or {"summary": 160, "l1": 300, "l2": 180}
        self.generation_log: List[GenerationResult] = []

    # ------------------------------------------------------------------ prompts
    def _prompt(self, kind: str, retry_feedback: Optional[str] = None) -> str:
        terms = ", ".join(e.canonical for e in self.registry.required())
        formula = self.km.formulas[0].text if self.km.formulas else "(none)"
        ex = self._example_line()
        task = {
            "summary": "Write a short summary of the passage in 3 sentences for a Class 7 student.",
            "l1": ("Explain the passage step by step for a student who finds the text hard. "
                   "Use very short sentences (at most 12 words). One idea per sentence. "
                   "Explain each technical term in simple words. Include the worked example."),
            "l2": ("Write a simplified explanation of the passage in 4 to 6 sentences. "
                   "Keep the scientific terms, the formula and the units."),
        }[kind]
        rules = (f"Keep these exact terms: {terms}.\nKeep the formula exactly as: {formula}.\n"
                 + (f"Worked example from the passage: {ex}\n" if ex and kind != "summary" else "")
                 + "Do not add any fact, number or unit that is not in the passage. Write plain sentences only.")
        fb = f"\nYour previous answer was rejected because: {retry_feedback}. Fix this." if retry_feedback else ""
        return f"{task}\n{rules}{fb}\n\nPassage:\n{self.passage.text}"

    # ------------------------------------------------------------------ templates
    def _example_line(self) -> Optional[str]:
        if not self.km.examples:
            return None
        e = self.km.examples[0]
        num, den = e.numerator, e.denominator
        return (f"{fmt_number(num['value'])} {display_unit(num['unit'])} in {fmt_number(den['value'])} "
                f"{display_unit(den['unit'])}: {fmt_number(num['value'])} ÷ {fmt_number(den['value'])} = {e.computed}")

    def _example_actor(self) -> str:
        if not self.km.examples:
            return "an object"
        s = self.passage.sentence(self.km.examples[0].sid).text
        m = re.search(r"\b(an? \w+) that \w+", s, re.I)
        return m.group(1).lower() if m else "an object"

    _EXAMPLE_PREDICATE = {
        "speed": "covers {n} in {d}",
        "power": "does {n} of work in {d}",
        "pressure": "pushes with a force of {n} on an area of {d}",
        "resistance": "has a voltage of {n} across it and a current of {d}",
    }

    def _example_phrase(self, ex, relative: bool = False) -> str:
        """'a bus covers 120 km in 2 h'; 'a block has a mass of 120 g and a volume of 40 cm³' (generic form)."""
        f = self.km.primary_formula()
        n, d_ = ex.numerator, ex.denominator
        nq = f"{fmt_number(n['value'])} {display_unit(n['unit'])}"
        dq = f"{fmt_number(d_['value'])} {display_unit(d_['unit'])}"
        key = f.key if f else "speed"
        pred = self._EXAMPLE_PREDICATE.get(key) or (
            f"has {_article(f.numerator).lower()} {f.numerator} of {{n}} and {_article(f.denominator).lower()} {f.denominator} of {{d}}")
        return f"{self._example_actor()} {'that ' if relative else ''}{pred.format(n=nq, d=dq)}"

    def template(self, kind: str) -> str:
        km = self.km
        f = km.primary_formula()
        lines: List[str] = []
        qdefs = [d for d in km.definitions if d.category == "quantity"]
        insts = [d for d in km.definitions if d.category == "instrument"]
        states = [d for d in km.definitions if d.category == "state"]
        rel_lines = []
        for r in km.relationships:
            fixed = r.condition.replace("same ", "")
            more = "more" if r.change == "increase" else "less"
            out = "higher" if r.direction == "increase" else "lower"
            rel_lines.append(f"If the {fixed} is the same, {more} {r.changed_variable} means {out} {r.relation}.")
        ce_lines = []
        for c in km.cause_effects:
            cause = c.cause.split(";")[0].strip()
            ce_lines.append((f"{_cap(cause)}.", f"So {c.effect}."))
        ex = km.examples[0] if km.examples else None
        if kind == "l1":
            for d in states:
                lines.append(self.passage.sentence(d.sid).text)
            for d in qdefs:
                lines.append(f"{_cap(d.term)} tells us the {d.meaning}.")
            if f:
                lines.append(f"{_cap(f.text)}.")
                lines.append(f"To find {f.output}, divide the {f.numerator} by the {f.denominator}.")
            for u in km.unit_facts:
                lines.append(f"{u.unit} means {u.meaning}.")
            if ex:
                n, d_ = ex.numerator, ex.denominator
                lines.append(f"Example: {self._example_phrase(ex)}.")
                lines.append(f"{fmt_number(n['value'])} ÷ {fmt_number(d_['value'])} = {fmt_number(ex.stated['value'])}.")
                for c in km.compound_terms:
                    lines.append(f"So its {c['term']} is {ex.computed}.")
            lines.extend(rel_lines)
            for a, b in ce_lines:
                lines.extend([a, b])
            for d in insts:
                lines.append(f"{_article(d.term)} {d.term} {d.verb or 'shows'} {d.meaning}.")
            return "\n".join(lines)
        if kind == "l2":
            parts = []
            for d in qdefs:
                parts.append(f"{_cap(d.term)} is the {d.meaning}.")
            if f:
                parts.append(f"It is calculated as {f.text}" + (
                    f", and is measured in {' or '.join(u.unit for u in km.unit_facts)}." if km.unit_facts else "."))
            if ex:
                comp = km.compound_terms[0]["term"] if km.compound_terms else f.output if f else "result"
                parts.append(f"For example, {self._example_phrase(ex, relative=True)} has {_article(comp).lower()} {comp} "
                             f"of {ex.computed}.")
            parts.extend(rel_lines)
            for a, b in ce_lines:
                parts.append(f"{a[:-1]}, so {b[3:]}")
            if insts:
                parts.append("; ".join(f"{_article(d.term).lower() if i else _article(d.term)} {d.term} {d.verb or 'shows'} {d.meaning}"
                                       for i, d in enumerate(insts)) + ".")
            return " ".join(parts)
        if kind == "summary":
            parts = []
            for d in qdefs[:1]:
                parts.append(f"{_cap(d.term)} is the {d.meaning}.")
            if f:
                parts.append(f"It is calculated as {f.text}" + (
                    f" and measured in units such as {' or '.join(u.unit for u in km.unit_facts)}." if km.unit_facts else "."))
            if rel_lines:
                parts.append(rel_lines[0])
            if ex:
                parts.append(f"For example, {fmt_number(ex.numerator['value'])} {display_unit(ex.numerator['unit'])} in "
                             f"{fmt_number(ex.denominator['value'])} {display_unit(ex.denominator['unit'])} gives {ex.computed}.")
            return " ".join(parts) if parts else " ".join(s.text for s in self.passage.sentences[:3])
        raise ValueError(kind)

    # ------------------------------------------------------------------ generation
    def generate(self, kind: str) -> Explanation:
        """Generate one of summary | l1 | l2 with validation, bounded retry and template fallback."""
        attempts: List[Attempt] = []
        feedback: Optional[str] = None
        if self.runtime.is_llm:
            for n in range(1, self.max_attempts + 1):
                res = self.runtime.generate(self._prompt(kind, feedback), self.max_new_tokens.get(kind, 200))
                self.generation_log.append(res)
                rep: Optional[ValidationReport] = self.validator.validate(res.text, kind) if res.ok else None
                attempts.append(Attempt(n, res.backend, res.ok, res.error, rep.to_dict() if rep else None,
                                        res.wall_time_s, res.ttft_ms, res.generated_tokens,
                                        (res.text or "")[:3000] if res.ok else None))
                if res.ok and rep and rep.passed:
                    log.info("accepted %s from %s (attempt %d)", kind, res.backend, n)
                    return Explanation(kind, res.text, "llm" if n == 1 else "llm_retry", True, rep.to_dict(), attempts)
                feedback = (res.error or "; ".join(f"{c.name}: {c.details}" for c in rep.failures())) if (rep or res.error) else "invalid"
                log.warning("rejected %s attempt %d: %s", kind, n, feedback)
        text = self.template(kind)
        rep = self.validator.validate(text, kind)
        if not rep.passed:
            log.error("template for %s failed validation: %s", kind, [c.details for c in rep.failures()])
        return Explanation(kind, text, "template", rep.passed, rep.to_dict(), attempts)

    def l3(self) -> Explanation:
        """Original passage, unmodified, with glosses for registry terms kept separately."""
        text = self.passage.text
        rep = self.validator.validate(text, "l3")
        glosses = [{"term": e.canonical, "sid": e.sid, "gloss": e.meaning} for e in self.registry.entries]
        return Explanation("l3", text, "original", rep.passed, rep.to_dict(), [], glosses)

    def build_all(self) -> Dict[str, Explanation]:
        return {"summary": self.generate("summary"), "l1": self.generate("l1"), "l2": self.generate("l2"), "l3": self.l3()}
