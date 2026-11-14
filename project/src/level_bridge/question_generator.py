"""Deterministic item bank: placement probes, assessment items, second-chance items, transfer.

* Correct answers are always computed by Python (definition lookup, formula engine,
  direction rules) – the LLM may only reword a stem, and a reworded stem is kept
  only if it passes validation (same numbers and units, key term kept, no answer leak).
* Explanation support (rung L1-L3) and cognitive level (recall/understand/apply/transfer)
  are independent fields; the scheduler assigns both.
* Quantitative items use numeric entry, so no option with an invalid unit is shown.
"""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

from .formula_engine import FORMULAS, Formula, compute, error_models, make_quantity
from .knowledge_map import Definition, KnowledgeMap
from .model_runtime import ModelRuntime
from .quantity_parser import Quantity, display_unit, fmt_number, parse_numbers, parse_quantities

log = logging.getLogger("level_bridge.questions")

COGNITIVE_LEVELS = ("recall", "understand", "apply", "transfer")
_PHRASING = {
    "speed": {"verb": "covers", "join": "in", "higher": "higher average speed", "who": "Who is faster?"},
    "density": {"verb": "has a mass of", "join": "and a volume of", "higher": "higher density", "who": "Which is denser?",
                "ask": "density", "same_a": "both have a mass of {a}. Their volumes are {b1} and {b2}"},
    "pressure": {"verb": "pushes with a force of", "join": "on an area of", "higher": "higher pressure",
                 "who": "Which produces the higher pressure?", "ask": "pressure",
                 "same_a": "both push with a force of {a}, on areas of {b1} and {b2}",
                 "same_b": "both press on an area of {b}, with forces of {a1} and {a2}"},
    "resistance": {"verb": "has a voltage of", "join": "across it and a current of", "higher": "higher resistance",
                   "who": "Which has the higher resistance?", "ask": "resistance",
                   "same_a": "both have a voltage of {a} across them. Their currents are {b1} and {b2}",
                   "same_b": "both carry a current of {b}. The voltages across them are {a1} and {a2}"},
    "power": {"verb": "does", "join": "of work in", "higher": "higher power", "who": "Which has the higher power?",
              "ask": "power", "same_a": "both do {a} of work, taking {b1} and {b2}",
              "same_b": "both work for {b}, doing {a1} and {a2} of work"},
}


@dataclass
class Option:
    key: str
    text: str
    correct: bool
    error_code: Optional[str] = None


@dataclass
class Item:
    item_id: str
    kind: str                       # placement | assessment | second_chance | transfer
    concept_id: str
    knowledge_type: str
    cognitive_level: Optional[str]  # recall | understand | apply | transfer (None for placement)
    rung: Optional[int]             # explanation-support rung the item is scheduled at
    response_type: str              # mcq | numeric
    stem: str
    source_sids: List[str]
    explanation: str
    options: List[Option] = field(default_factory=list)
    answer_key: Optional[str] = None
    numeric: Optional[Dict[str, object]] = None   # solution + error models for numeric items
    probe_type: Optional[str] = None              # literal | word_in_context | inference (placement)
    parent_item: Optional[str] = None             # for second-chance items
    stem_source: str = "template"                 # template | llm
    template_stem: str = ""

    def correct_option(self) -> Optional[Option]:
        return next((o for o in self.options if o.correct), None)

    def to_dict(self) -> Dict[str, object]:
        d = asdict(self)
        return d


@dataclass
class ItemBank:
    items: List[Item]

    def by_id(self, item_id: str) -> Item:
        for it in self.items:
            if it.item_id == item_id:
                return it
        raise KeyError(item_id)

    def of_kind(self, kind: str) -> List[Item]:
        return [i for i in self.items if i.kind == kind]

    def for_rung(self, rung: int) -> List[Item]:
        return [i for i in self.items if i.kind == "assessment" and i.rung == rung]

    def second_chance_for(self, item_id: str) -> Optional[Item]:
        return next((i for i in self.items if i.kind == "second_chance" and i.parent_item == item_id), None)

    def composition(self) -> Dict[str, int]:
        comp = {k: len(self.of_kind(k)) for k in ("placement", "assessment", "second_chance", "transfer")}
        comp["total"] = len(self.items)
        return comp

    def to_dict(self) -> Dict[str, object]:
        return {"composition": self.composition(), "items": [i.to_dict() for i in self.items]}


def _cap(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


class QuestionGenerator:
    """Builds the item bank from the knowledge map and the context library."""

    def __init__(self, km: KnowledgeMap, contexts: Dict[str, object], seed: int = 7) -> None:
        self.km = km
        self.contexts = contexts
        self.seed = seed
        self.f: Optional[Formula] = km.primary_formula()

    # ------------------------------------------------------------------ helpers
    def _rng(self, item_id: str) -> random.Random:
        return random.Random(f"{self.seed}-{item_id}")

    def _shuffle(self, item_id: str, opts: List[Tuple[str, bool, Optional[str]]]) -> List[Option]:
        order = list(opts)
        self._rng(item_id).shuffle(order)
        return [Option("ABCD"[i], t, c, e) for i, (t, c, e) in enumerate(order)]

    def _ctx(self, key: str, idx: int = 0) -> Dict[str, object]:
        lib = self.contexts.get(self.f.key, {}) if self.f else {}
        lst = lib.get(key) or []
        if not lst:
            raise ValueError(f"No '{key}' context for formula '{self.f.key if self.f else None}' in item_contexts.yaml")
        return lst[idx % len(lst)]

    @staticmethod
    def _q(pair) -> Quantity:
        return make_quantity(pair[0], pair[1])

    def _concept_for(self, ref_key: str, ref_val: str) -> str:
        for c in self.km.concepts:
            if c.ref.get(ref_key) == ref_val:
                return c.cid
        raise KeyError(ref_val)

    # ------------------------------------------------------------------ item builders
    def _definition_options(self, d: Definition) -> List[Tuple[str, bool, Optional[str]]]:
        pool: List[Tuple[str, Optional[str]]] = []
        defs = self.km.definitions
        if d.pair_term:
            pair = next(x for x in defs if x.term == d.pair_term)
            pool.append((pair.short_meaning, "term_confusion"))
        for x in [x for x in defs if x.category == "state"] + [x for x in defs if x.category != "state"]:
            if x.term != d.term and x.term != d.pair_term:
                pool.append((x.short_meaning, "term_confusion"))
        for c in self.km.compound_terms:
            pool.append((_cap(c["term"]), "term_confusion"))
        if self.f:
            pool.append((f"{_cap(self.f.denominator)} taken", "wrong_variable"))
        seen, distractors = {d.short_meaning.lower()}, []
        for text, code in pool:
            if text.lower() not in seen:
                seen.add(text.lower())
                distractors.append((text, False, code))
        return [(d.short_meaning, True, None)] + distractors[:3]

    def definition_item(self, item_id: str, d: Definition, kind: str, level: str, rung: Optional[int],
                        probe: Optional[str] = None, parent: Optional[str] = None, reverse: bool = False) -> Item:
        cid = self._concept_for("definition", d.term)
        if reverse:  # term-from-meaning variant (used for second chances)
            others = [x.term for x in self.km.definitions if x.term not in (d.term, d.pair_term)]
            terms = [d.term] + ([d.pair_term] if d.pair_term else []) + others + [c["term"] for c in self.km.compound_terms]
            terms = list(dict.fromkeys(terms))[:4]
            opts = [(t, t == d.term, None if t == d.term else "term_confusion") for t in terms]
            stem = f"Which term means \"{d.short_meaning.lower()}\"?"
        else:
            opts = self._definition_options(d)
            stem = (f"In sentence {d.sid}, what does \"{d.term}\" mean?" if probe == "word_in_context"
                    else f"What is {d.term}?" if d.category == "quantity" else f"What does {'an' if d.term[0] in 'aeiou' else 'a'} {d.term} measure?"
                    if d.verb == "measures" else f"What does {'an' if d.term[0] in 'aeiou' else 'a'} {d.term} show?")
        options = self._shuffle(item_id, opts)
        key = next(o.key for o in options if o.correct)
        expl = f"{_cap(d.term)}: {d.meaning} ({d.sid})."
        return Item(item_id, kind, cid, "definition", level, rung, "mcq", stem, [d.sid], expl, options, key,
                    probe_type=probe, parent_item=parent, template_stem=stem)

    def numeric_item(self, item_id: str, ctx_key: str, kind: str, level: str, rung: Optional[int],
                     parent: Optional[str] = None) -> Item:
        f = self.f
        c = self._ctx(ctx_key)
        a, b = self._q(c["a"]), self._q(c["b"])
        target = f.default_output_unit
        sol = compute(f, a, b, target)
        models = error_models(f, a, b, target)
        ph = _PHRASING.get(f.key, {"verb": "has", "join": "and"})
        setting = f" {c['setting']}" if c.get("setting") else ""
        stem = (f"{c['actor']} {c.get('verb', ph['verb'])} {a.text()}{setting} {ph['join']} {b.text()}. "
                f"What is the {ph.get('ask', 'average ' + f.output)} in {display_unit(target)}? (type a number)")
        fid = self._concept_for("formula", f.key)
        fsid = next(x.sid for x in self.km.formulas if x.key == f.key)
        return Item(item_id, kind, fid, "quantitative", level, rung, "numeric", stem, [fsid],
                    " ".join(sol.steps()), numeric={"inputs": {"numerator": a.to_dict(), "denominator": b.to_dict()},
                                                     "solution": sol.to_dict(), "error_models": [m.to_dict() for m in models]},
                    parent_item=parent, template_stem=stem)

    def relation_item(self, item_id: str, ctx_key: str, kind: str, level: Optional[str], rung: Optional[int],
                      probe: Optional[str] = None, parent: Optional[str] = None) -> Item:
        f = self.f
        c = self._ctx(ctx_key)
        ph = _PHRASING.get(f.key, {"verb": "has", "join": "and", "higher": f"higher {f.output}", "who": f"Which has the higher {f.output}?"})
        x, y = c["actors"]
        if ctx_key.startswith("relation_same_b"):
            b = self._q(c["b"])
            a1, a2 = self._q(c["a"][0]), self._q(c["a"][1])
            s1, s2 = compute(f, a1, b), compute(f, a2, b)
            if ph.get("same_b"):
                stem = (f"{_cap(x)} and {y} " + ph["same_b"].format(b=b.text(), a1=a1.text(), a2=a2.text())
                        + f". Which has the {ph['higher']}?")
            else:
                stem = (f"In {b.text()}, {x} {ph['verb']} {a1.text()} and {y} {ph['verb']} {a2.text()}. "
                        f"Which has the {ph['higher']}?")
            rel = next(r for r in self.km.relationships if r.condition == f"same {f.denominator}") \
                if any(r.condition == f"same {f.denominator}" for r in self.km.relationships) else None
        else:
            a = self._q(c["a"])
            b1, b2 = self._q(c["b"][0]), self._q(c["b"][1])
            s1, s2 = compute(f, a, b1), compute(f, a, b2)
            same_a = ph.get("same_a", "both have {a}. Their " + f.denominator + "s are {b1} and {b2}")
            stem = (f"{_cap(x)} and {y} both travel {a.text()}. {_cap(x)} takes {b1.text()} and {y} takes {b2.text()}. "
                    f"{ph['who']}") if f.key == "speed" else (
                    f"{_cap(x)} and {y} " + same_a.format(a=a.text(), b1=b1.text(), b2=b2.text()) + f". {ph['who']}")
            rel = next((r for r in self.km.relationships if r.condition == f"same {f.numerator}"), None)
        winner = x if s1.value > s2.value else y
        loser = y if winner == x else x
        opts = [(_cap(winner), True, None), (_cap(loser), False, "reversed_relation"),
                (f"Both have the same {f.output}", False, "no_change"),
                ("It cannot be found from this information", False, "missing_variable")]
        options = self._shuffle(item_id, opts)
        key = next(o.key for o in options if o.correct)
        sid = rel.sid if rel else next(x_.sid for x_ in self.km.formulas)
        cid = self._concept_for("relationship", rel.sid) if rel else self._concept_for("formula", f.key)
        expl = (f"{_cap(x)}: {s1.answer_text}; {y}: {s2.answer_text}. {self._sentence_hint(sid)}")
        return Item(item_id, kind, cid, "quantitative", level, rung, "mcq", stem, [sid], expl, options, key,
                    probe_type=probe, parent_item=parent, template_stem=stem)

    def _sentence_hint(self, sid: str) -> str:
        s = next((x["text"] for x in self.km.sentences if x["sid"] == sid), "")
        return f"({sid}: \"{s}\")" if s else ""

    def unit_probe(self, item_id: str) -> Optional[Item]:
        basic = next((u for u in self.km.unit_facts if "basic unit" in u.meaning), None)
        if not basic or not self.f:
            return None
        others = []
        for q in self.km.quantities:
            if q["dimension"] != self.f.output_dim and q["unit"] not in [o for o, _ in others]:
                others.append((q["unit"], q["dimension"]))
        names = {"km": "kilometre", "h": "hour", "m": "metre", "s": "second", "min": "minute", "g": "gram", "kg": "kilogram",
                 "cm3": "cubic centimetre", "N": "newton", "m2": "square metre", "cm2": "square centimetre", "V": "volt",
                 "A": "ampere", "mA": "milliampere", "J": "joule", "kJ": "kilojoule", "W": "watt"}
        for extra in ("s", "m", "min"):
            if len(others) >= 3:
                break
            if extra not in [o for o, _ in others]:
                others.append((extra, ""))
        opts = [(f"{basic.unit} ({basic.meaning.split(',')[0]})", True, None)] + \
               [(f"{display_unit(u)} ({names.get(u, u)})", False, "dimension_confusion") for u, _ in others[:3]]
        options = self._shuffle(item_id, opts)
        key = next(o.key for o in options if o.correct)
        cid = self._concept_for("definition", self.f.output) if self.km.definition(self.f.output) else self.km.concepts[0].cid
        stem = f"What is the basic unit of {self.f.output}?"
        return Item(item_id, "placement", cid, "definition", None, None, "mcq", stem, [basic.sid],
                    f"{basic.meaning} ({basic.sid}).", options, key, probe_type="literal", template_stem=stem)

    # ------------------------------------------------------------------ bank
    def build(self) -> ItemBank:
        """Schedule: L1 = [definition recall, quantitative apply]; L2 = [definition recall,
        relationship apply]; bridge = quantitative transfer. One second chance per assessment item."""
        km = self.km
        defs_by_concept = [km.definition(c.ref["definition"]) for c in km.concepts if c.knowledge_type == "definition"]
        items: List[Item] = []
        # placement probes
        p1 = self.unit_probe("P1") or (self.definition_item("P1", defs_by_concept[0], "placement", None, None, probe="literal")
                                       if defs_by_concept else None)
        if p1:
            items.append(p1)
        if len(defs_by_concept) >= 2:
            items.append(self.definition_item("P2", defs_by_concept[1], "placement", None, None, probe="word_in_context"))
        if self.f and km.relationships:
            ctx = "relation_same_a" if any(r.condition == f"same {self.f.numerator}" for r in km.relationships) else "relation_same_b"
            items.append(self.relation_item("P3", ctx, "placement", None, None, probe="inference"))
        # assessment schedule
        plan: List[Item] = []
        if defs_by_concept:
            plan.append(self.definition_item("Q1", defs_by_concept[0], "assessment", "recall", 1))
        if self.f:
            plan.append(self.numeric_item("Q2", "assessment", "assessment", "apply", 1))
        if len(defs_by_concept) >= 2:
            plan.append(self.definition_item("Q3", defs_by_concept[1], "assessment", "recall", 2))
        if self.f and km.relationships:
            plan.append(self.relation_item("Q4", "relation_same_b", "assessment", "apply", 2))
        # renumber consecutively in case some were skipped
        for n, it in enumerate(plan, start=1):
            it.item_id = f"Q{n}"
        items.extend(plan)
        for it in plan:
            sc_id = f"{it.item_id}b"
            if it.response_type == "numeric":
                sc = self.numeric_item(sc_id, "second_chance", "second_chance", it.cognitive_level, it.rung, parent=it.item_id)
            elif it.knowledge_type == "definition":
                sc = self.definition_item(sc_id, km.definition(km.concept(it.concept_id).ref["definition"]), "second_chance",
                                          it.cognitive_level, it.rung, parent=it.item_id, reverse=True)
            else:
                sc = self.relation_item(sc_id, "relation_same_b_second", "second_chance", it.cognitive_level, it.rung, parent=it.item_id)
            items.append(sc)
        if self.f:
            t = self.numeric_item("T1", "transfer", "transfer", "transfer", 3)
            t.source_sids = sorted({*t.source_sids, *[u.sid for u in km.unit_facts]}, key=lambda s: int(s[1:]))
            items.append(t)
        return ItemBank(items)


# ---------------------------------------------------------------------- LLM stem rewording
def reword_stems(bank: ItemBank, runtime: ModelRuntime, max_new_tokens: int = 220) -> Dict[str, object]:
    """Ask the LLM to reword all stems in one call; keep a reworded stem only if it validates.

    Validation: identical numbers and number-unit pairs, key term kept (definition items),
    the correct option text not leaked, at most 35 words, no special tokens.
    """
    summary = {"attempted": False, "accepted": 0, "rejected": 0, "reasons": {}, "backend": runtime.name}
    if not runtime.is_llm:
        return summary
    summary["attempted"] = True
    listing = "\n".join(f"{n}. {it.stem}" for n, it in enumerate(bank.items, start=1))
    prompt = ("Reword each numbered question so a Class 7 student understands it easily. Keep every number, unit and "
              "technical term exactly. Do not answer the questions. Reply with the same numbering, one question per line.\n\n"
              + listing)
    res = runtime.generate(prompt, max_new_tokens)
    summary["generation"] = {"ok": res.ok, "error": res.error, "wall_time_s": res.wall_time_s,
                             "ttft_ms": res.ttft_ms, "generated_tokens": res.generated_tokens}
    if not res.ok:
        summary["reasons"]["generation_failed"] = res.error
        return summary
    lines = {int(m.group(1)): m.group(2).strip() for m in re.finditer(r"^\s*(\d+)[.)]\s*(.+)$", res.text, re.M)}
    for n, it in enumerate(bank.items, start=1):
        new = lines.get(n)
        ok, why = _valid_stem(it, new)
        if ok:
            it.stem, it.stem_source = new, "llm"
            summary["accepted"] += 1
        else:
            summary["rejected"] += 1
            summary["reasons"][it.item_id] = why
    return summary


def _valid_stem(it: Item, new: Optional[str]) -> Tuple[bool, str]:
    if not new:
        return False, "missing"
    if re.search(r"<\|", new):
        return False, "special tokens"
    if len(new.split()) > 35:
        return False, "too long"
    if sorted(parse_numbers(new)) != sorted(parse_numbers(it.template_stem)):
        return False, "numbers changed"
    old_pairs = sorted((m.quantity.value, m.quantity.unit) for m in parse_quantities(it.template_stem))
    new_pairs = sorted((m.quantity.value, m.quantity.unit) for m in parse_quantities(new))
    if old_pairs != new_pairs:
        return False, "units changed"
    m = re.search(r"\"([^\"]+)\"", it.template_stem)
    if m and m.group(1).lower() not in new.lower():
        return False, "key term dropped"
    # report Section 5.3: some on-device rewordings turned questions into statements or answered them
    if "?" in it.template_stem and "?" not in new:
        return False, "question became a statement"
    if re.search(r"\b(?:therefore|the answer is|so the answer|correct answer)\b", new, re.I):
        return False, "answer leaked"
    for o in it.options:
        t = o.text.lower()
        if len(t) > 3 and t in new.lower() and t not in it.template_stem.lower():
            return False, "option text added"
    co = it.correct_option()
    if co and len(co.text) > 6 and co.text.lower() in new.lower():
        return False, "answer leaked"
    return True, "ok"
