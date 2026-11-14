"""Concept Coverage, Numerical Consistency and Relationship-Direction Validation (report p.3).

What these checks DO establish:
  * every required registry term (or a permitted synonym) is present;
  * the formula is present;
  * every number / number-unit pair matches the passage (or a verified worked result);
  * no sentence states a direction that contradicts the formula
    (e.g. "more time -> faster" for speed = distance ÷ time);
  * no new numbers or units are introduced, and sentences with many words absent
    from the passage are flagged;
  * for L3, every original sentence is reproduced verbatim.

What they do NOT establish: full semantic correctness. Lexical/rule checks can miss a
wrong claim phrased with passage vocabulary. Semantic correctness is assessed by human
review (report §5.2). Nothing here claims otherwise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Tuple

from .formula_engine import FORMULAS, relation_direction
from .key_term_registry import KeyTermRegistry, term_present
from .knowledge_map import KnowledgeMap
from .passage_processor import Passage
from .quantity_parser import parse_numbers, parse_quantities

SPECIAL_TOKENS = re.compile(r"<\|[^|>]*\|>|<s>|</s>|\[INST\]|\[/INST\]")
PROMPT_ARTIFACTS = re.compile(r"^\s*(passage|rules|instructions?|explanation|summary)\s*:", re.I | re.M)
_UP = {"greater", "larger", "more", "longer", "higher", "increase", "increases", "bigger"}
_DOWN = {"smaller", "less", "shorter", "lower", "decrease", "decreases", "fewer"}
_COMPARATIVES = {"faster": ("speed", "increase"), "slower": ("speed", "decrease"),
                 "denser": ("density", "increase")}
_STOP = set("""a an the and or but if then than that this these those is are was were be been being of in on at to for
from by with as it its they them their we our you your he she his her not no do does did can could will would should
may might must also so such into over under about after before when while which who whom what where why how all any each
one two three there here very more most less least much many some other only just because same""".split())
_EXPLAIN_VOCAB = set("""means mean tells tell shows show example examples step steps first next then finally so therefore
fast faster slow slower quick quickly moves move moving travel travels travelled travelling goes go gone went takes take
took taken find found divide divided dividing whole journey number numbers called word words idea simple simply easy
remember use used using gives give get gets thing things way like say says said measure measures measured unit units
answer formula work works per every each""".split())


@dataclass
class Check:
    name: str
    passed: bool
    details: str = ""
    severity: str = "error"          # error | warning

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class ValidationReport:
    kind: str
    checks: List[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks if c.severity == "error")

    def failures(self) -> List[Check]:
        return [c for c in self.checks if not c.passed and c.severity == "error"]

    def to_dict(self) -> Dict[str, object]:
        return {"kind": self.kind, "passed": self.passed, "checks": [c.to_dict() for c in self.checks]}


def _stem(w: str) -> str:
    w = w.lower()
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _sentences(text: str) -> List[str]:
    t = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", text, flags=re.M)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", t) if s.strip()]


def _strip_list_markers(text: str) -> str:
    return re.sub(r"^\s*(?:\d+[.)]|[-*•])\s+", "", text, flags=re.M)


class ConceptValidator:
    """Validates generated text against the passage, knowledge map and registry."""

    def __init__(self, passage: Passage, km: KnowledgeMap, registry: KeyTermRegistry,
                 summary_min_coverage: float = 0.5, l1_max_words_per_sentence: int = 14) -> None:
        self.passage = passage
        self.km = km
        self.registry = registry
        self.summary_min_coverage = summary_min_coverage
        self.l1_max_words = l1_max_words_per_sentence
        self.allowed_numbers: Set[float] = set(parse_numbers(passage.text))
        self.allowed_pairs: Set[Tuple[float, str]] = {(q["value"], q["unit"]) for q in km.quantities}
        for ex in km.examples:
            st = ex.stated
            self.allowed_pairs.add((st["value"], st["unit"]))
            self.allowed_numbers.add(st["value"])
        words = re.findall(r"[a-z]+", passage.text.lower())
        self.passage_vocab = {_stem(w) for w in words}
        for e in registry.entries:
            for form in e.surface_forms():
                self.passage_vocab.update(_stem(w) for w in re.findall(r"[a-z]+", form.lower()))

    # ------------------------------------------------------------------ public
    def validate(self, text: str, kind: str, extra_numbers: Optional[Set[float]] = None,
                 extra_pairs: Optional[Set[Tuple[float, str]]] = None) -> ValidationReport:
        """Validate ``text`` of a given ``kind`` (summary | l1 | l2 | l3 | question_stem | repair)."""
        rep = ValidationReport(kind)
        rep.checks.append(self._well_formed(text))
        if not rep.checks[0].passed:
            return rep
        if kind in ("summary", "l1", "l2"):
            rep.checks.append(self._coverage(text, 1.0 if kind in ("l1", "l2") else self.summary_min_coverage))
            rep.checks.append(self._formula(text))
        if kind == "l3":
            rep.checks.append(self._original_preserved(text))
        rep.checks.append(self._numbers(text, extra_numbers or set()))
        rep.checks.append(self._units(text, extra_pairs or set()))
        rep.checks.append(self._direction(text))
        if kind in ("summary", "l1", "l2", "repair"):
            rep.checks.append(self._unsupported(text))
        if kind == "l1":
            rep.checks.append(self._l1_sentence_length(text))
        return rep

    # ------------------------------------------------------------------ checks
    def _well_formed(self, text: str) -> Check:
        if text is None or not text.strip():
            return Check("well_formed", False, "empty output")
        if SPECIAL_TOKENS.search(text):
            return Check("well_formed", False, "contains special/control tokens")
        if PROMPT_ARTIFACTS.search(text):
            return Check("well_formed", False, "echoes prompt headings (malformed output)")
        if len(re.findall(r"[A-Za-z]+", text)) < 5:
            return Check("well_formed", False, "fewer than 5 words")
        return Check("well_formed", True)

    def _coverage(self, text: str, min_ratio: float) -> Check:
        req = self.registry.required()
        missing = [e.canonical for e in req if not term_present(e, text)]
        ratio = 1.0 if not req else (len(req) - len(missing)) / len(req)
        ok = ratio >= min_ratio - 1e-9
        return Check("key_term_coverage", ok, f"{len(req) - len(missing)}/{len(req)} required terms; missing: {missing}")

    def _formula(self, text: str) -> Check:
        if not self.km.formulas:
            return Check("formula_preserved", True, "no formula in passage")
        missing = []
        for f in self.km.formulas:
            e = self.registry.get(f.text.lower())
            if not term_present(e, text):
                missing.append(f.text)
        return Check("formula_preserved", not missing, f"missing: {missing}" if missing else "present")

    def _original_preserved(self, text: str) -> Check:
        missing = [s.sid for s in self.passage.sentences if s.text not in text]
        return Check("original_text_unchanged", not missing, f"sentences not reproduced verbatim: {missing}" if missing else "all sentences verbatim")

    def _numbers(self, text: str, extra: Set[float]) -> Check:
        nums = parse_numbers(_strip_list_markers(text))
        allowed = self.allowed_numbers | extra
        bad = sorted({n for n in nums if not any(abs(n - a) < 1e-6 for a in allowed)})
        return Check("numerical_consistency", not bad, f"numbers not in passage: {bad}" if bad else "all numbers from passage")

    def _units(self, text: str, extra: Set[Tuple[float, str]]) -> Check:
        allowed = self.allowed_pairs | extra
        bad = []
        for m in parse_quantities(_strip_list_markers(text)):
            q = m.quantity
            if not any(abs(q.value - v) < 1e-6 and q.unit == u for v, u in allowed):
                bad.append(m.surface)
        return Check("unit_consistency", not bad, f"number-unit pairs not in passage: {bad}" if bad else "consistent")

    def _direction(self, text: str) -> Check:
        """Flag sentences whose stated change contradicts the formula direction."""
        problems = []
        formulas = [FORMULAS[f.key] for f in self.km.formulas]
        for sent in _sentences(text):
            low = sent.lower()
            for f in formulas:
                out_dir = self._output_direction(low, f)
                if out_dir is None:
                    continue
                for var in (f.numerator, f.denominator):
                    ch = self._variable_change(low, var)
                    if ch is None:
                        continue
                    expected = relation_direction(f, var, ch)
                    if expected != out_dir:
                        problems.append(sent)
        return Check("relationship_direction", not problems,
                     f"direction contradicts formula in: {problems}" if problems else "no contradictions found")

    @staticmethod
    def _output_direction(low: str, f) -> Optional[str]:
        for word, (out, d) in _COMPARATIVES.items():
            if out == f.output and re.search(rf"\b{word}\b", low):
                return d
        m = re.search(rf"\b(\w+) {f.output}\b", low)
        if m and m.group(1) in _UP:
            return "increase"
        if m and m.group(1) in _DOWN:
            return "decrease"
        m = re.search(rf"\b{f.output} (?:\w+ )?(increases|decreases|goes up|goes down)", low)
        if m:
            return "increase" if m.group(1) in ("increases", "goes up") else "decrease"
        return None

    @staticmethod
    def _variable_change(low: str, var: str) -> Optional[str]:
        m = re.search(rf"\b(\w+) {var}\b", low)
        if m and m.group(1) in _UP:
            return "increase"
        if m and m.group(1) in _DOWN:
            return "decrease"
        return None

    def _unsupported(self, text: str) -> Check:
        flagged = []
        for sent in _sentences(text):
            words = [w for w in re.findall(r"[a-z]+", sent.lower()) if len(w) >= 4 and w not in _STOP and w not in _EXPLAIN_VOCAB]
            novel = sorted({w for w in words if _stem(w) not in self.passage_vocab})
            if len(novel) >= 4:
                flagged.append({"sentence": sent, "novel_words": novel})
        return Check("unsupported_content", not flagged,
                     f"sentences with many words absent from the passage: {flagged}" if flagged else "none flagged")

    def _l1_sentence_length(self, text: str) -> Check:
        sents = _sentences(text)
        if not sents:
            return Check("l1_short_sentences", False, "no sentences")
        avg = sum(len(s.split()) for s in sents) / len(sents)
        return Check("l1_short_sentences", avg <= self.l1_max_words,
                     f"average {avg:.1f} words per sentence (limit {self.l1_max_words})")
