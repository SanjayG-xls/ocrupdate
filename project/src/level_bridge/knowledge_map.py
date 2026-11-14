"""Rule-based STEM knowledge map.

Core PoC knowledge types (report p.3): **definition**, **cause_effect**, **quantitative**.
Extension types (process/sequence, classification/comparison, experiment/variables)
are NOT extracted; sentences that match none of the supported patterns are listed as
``unsupported`` so that downstream components can fall back safely.

The extraction is pattern-based (no LLM), so it is reproducible and testable, but it
only recognises the sentence forms implemented below. That limit is reported, not hidden.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from .formula_engine import Formula, FORMULAS, compute, detect_formula, relation_direction, InvalidInput, normalise_quantity_names
from .passage_processor import Passage
from .quantity_parser import Quantity, QuantityMention, parse_quantities, parse_unit_mentions, UNITS, UNIT_ALIASES

CORE_TYPES = ("definition", "cause_effect", "quantitative")
EXTENSION_TYPES = ("process_sequence", "classification_comparison", "experiment_variables")


@dataclass
class Definition:
    term: str
    meaning: str            # meaning as phrased from the passage
    short_meaning: str      # compact form used for options, e.g. "total distance travelled"
    sid: str
    category: str           # quantity | instrument | state
    pair_term: Optional[str] = None   # confusable partner defined in the same sentence
    verb: Optional[str] = None        # for instruments: shows / measures / records


@dataclass
class FormulaFact:
    sid: str
    key: str
    text: str


@dataclass
class WorkedExample:
    sid: str
    formula_key: str
    numerator: Dict[str, object]
    denominator: Dict[str, object]
    stated: Dict[str, object]
    computed: str
    verified: bool


@dataclass
class Relationship:
    """(subject, relation, direction, condition, result) tuple extracted from the passage."""

    sid: str
    formula_key: str
    subject: str
    relation: str          # the output quantity, e.g. speed
    direction: str         # increase | decrease (of the relation)
    condition: str         # fixed variable, e.g. "same time"
    changed_variable: str  # e.g. distance
    change: str            # increase | decrease (of the changed variable)
    result: str            # human-readable result phrase
    consistent_with_formula: bool


@dataclass
class CauseEffect:
    cause_sid: str
    effect_sid: str
    cause: str
    effect: str


@dataclass
class UnitFact:
    sid: str
    unit: str
    meaning: str


@dataclass
class Concept:
    cid: str
    label: str
    knowledge_type: str
    sids: List[str]
    ref: Dict[str, object]


@dataclass
class KnowledgeMap:
    passage_sha256: str
    sentences: List[Dict[str, object]]
    definitions: List[Definition] = field(default_factory=list)
    formulas: List[FormulaFact] = field(default_factory=list)
    examples: List[WorkedExample] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    cause_effects: List[CauseEffect] = field(default_factory=list)
    unit_facts: List[UnitFact] = field(default_factory=list)
    quantities: List[Dict[str, object]] = field(default_factory=list)
    compound_terms: List[Dict[str, str]] = field(default_factory=list)
    unsupported: List[Dict[str, str]] = field(default_factory=list)
    concepts: List[Concept] = field(default_factory=list)
    sentence_types: Dict[str, List[str]] = field(default_factory=dict)

    # ------------------------------------------------------------------ helpers
    def type_counts(self) -> Dict[str, int]:
        return {
            "definition": len(self.definitions),
            "quantitative": len(self.formulas) + len(self.examples) + len(self.relationships),
            "cause_effect": len(self.cause_effects),
        }

    def concept(self, cid: str) -> Concept:
        for c in self.concepts:
            if c.cid == cid:
                return c
        raise KeyError(cid)

    def primary_formula(self) -> Optional[Formula]:
        return FORMULAS[self.formulas[0].key] if self.formulas else None

    def definition(self, term: str) -> Optional[Definition]:
        for d in self.definitions:
            if d.term == term:
                return d
        return None

    def to_dict(self) -> Dict[str, object]:
        return {
            "passage_sha256": self.passage_sha256,
            "supported_knowledge_types": list(CORE_TYPES),
            "extension_types_not_extracted": list(EXTENSION_TYPES),
            "type_counts": self.type_counts(),
            "sentences": self.sentences,
            "sentence_types": self.sentence_types,
            "definitions": [asdict(d) for d in self.definitions],
            "formulas": [asdict(f) for f in self.formulas],
            "worked_examples": [asdict(e) for e in self.examples],
            "relationships": [asdict(r) for r in self.relationships],
            "cause_effects": [asdict(c) for c in self.cause_effects],
            "unit_facts": [asdict(u) for u in self.unit_facts],
            "quantities": self.quantities,
            "compound_terms": self.compound_terms,
            "unsupported": self.unsupported,
            "concepts": [asdict(c) for c in self.concepts],
        }


# ---------------------------------------------------------------------- patterns
_DEF_CALLED = re.compile(r"^(?:the |a |an )?(?P<meaning>.+?) is called (?:its |the |a |an )?(?P<term>[a-z]+(?: [a-z]+)?)\.?$", re.I)
_DEF_THIS_CALLED = re.compile(
    r"^(?P<pre>.+?),? and this (?P<noun>\w+) is called (?:its |the |a |an )?(?P<term>[a-z]+(?: [a-z]+)?)\.?$", re.I)
_DEF_STATE = re.compile(r"^(?P<art>an?|the) (?P<subject>\w+) is said to be in (?P<term>\w+) when (?P<meaning>.+?)\.?$", re.I)
_DEF_MEANS = re.compile(r"^(?:the |a |an )?(?P<term>[a-z]+(?: [a-z]+)?) (?:is defined as|means|is known as) (?P<meaning>.+?)\.?$", re.I)
_DEF_INSTRUMENT = re.compile(
    r"^(?:a |an |the )?(?P<term>\w+(?:meter|scope|graph))(?: in (?:an?|the) (?P<ctx>\w+))? (?P<verb>shows|measures|records|indicates) (?P<meaning>.+?)\.?$",
    re.I)
# general instruments ('A balance in the laboratory measures ...', 'a measuring cylinder measures ...')
_DEF_INSTRUMENT_GENERAL = re.compile(
    r"^(?:a |an |the )(?P<term>(?:measuring |spring |electric |digital )?\w+)(?: in (?:an?|the) (?P<ctx>\w+))? (?P<verb>measures|records|indicates) (?P<meaning>.+?)\.?$",
    re.I)
_REL_SAME_DEN = re.compile(
    r"if (?:the )?(?P<fixed>\w+)(?: \w+)? (?:stays|remains|is|are|is kept|stay) (?:the )?(?:same|constant|fixed),? (?:a|an|the) (?P<subject>\w+) (?:that \w+|with|having) (?:a |the )?"
    r"(?P<chg>greater|larger|more|longer|smaller|less|shorter) (?P<var>\w+) (?:must have|has|will have) (?:a )?"
    r"(?P<dir>higher|greater|larger|more|lower|smaller|less) (?P<out>\w+)", re.I)
_REL_SAME_NUM = re.compile(
    r"if two (?P<subject>\w+) (?:cover|travel|have|carry|use|do|push with|press with) the same (?P<fixed>\w+),? the one (?:that (?:takes|has|needs|uses)|with) "
    r"(?:the |a )?(?P<chg>less|more|shorter|longer|smaller|larger|greater|lower|higher) (?P<var>\w+) (?:is|has|produces|gives|exerts) (?:a |the )?"
    r"(?P<dir>faster|slower|denser|less dense|higher|greater|larger|lower|smaller|less|more)(?: (?P<out>\w+))?", re.I)
_CAUSE_LEAD = re.compile(r"^(?:that is why|this is why|therefore,?|as a result,?) (?P<effect>.+?)\.?$", re.I)
_BECAUSE = re.compile(r"^(?P<effect>.+?),? because (?P<cause>.+?)\.?$", re.I)

_UP = {"greater", "larger", "more", "longer", "higher", "faster"}
_DOWN = {"smaller", "less", "shorter", "lower", "slower"}
_COMPARATIVE_OUTPUT = {"faster": ("speed", "increase"), "slower": ("speed", "decrease"),
                       "denser": ("density", "increase"), "less dense": ("density", "decrease")}
_INSTRUMENT_SUFFIX = ("meter", "scope", "graph")


def _dirn(word: str) -> str:
    w = word.lower()
    if w in _UP:
        return "increase"
    if w in _DOWN:
        return "decrease"
    raise ValueError(word)


def _shorten(meaning: str) -> str:
    """Compact option text: 'the total distance it has travelled' -> 'total distance travelled'."""
    m = meaning.strip().rstrip(".")
    m = re.sub(r"^(?:its|the|a|an)\s+(?!\w+'s\b)", "", m, flags=re.I)
    m = re.sub(r"\s+(?:it|they|the \w+) (?:has|have|had|is|are)\s+", " ", m, flags=re.I)
    m = re.sub(r"\b(\w+) an? \w+ covers\b", r"\1 covered", m, flags=re.I)
    return m[0].upper() + m[1:] if m else m


def _definitions(sid: str, text: str) -> List[Definition]:
    out: List[Definition] = []
    m = _DEF_STATE.match(text)
    if m:
        art, subj = m.group("art").lower(), m.group("subject").lower()
        meaning = re.sub(r"\bits\b", f"{art} {subj}'s", m.group("meaning"))
        out.append(Definition(m.group("term").lower(), meaning, _shorten(meaning), sid, "state"))
        return out
    clauses = re.split(r",\s*while\s+", text.rstrip("."), flags=re.I)
    instruments: List[Definition] = []
    ctx = None
    for cl in clauses:
        mi = _DEF_INSTRUMENT.match(cl.strip())
        if mi:
            ctx = mi.group("ctx") or ctx
            meaning = mi.group("meaning")
            if ctx:
                meaning = re.sub(r"\bits\b", f"the {ctx}'s", meaning)
                meaning = re.sub(r"\bit\b", f"the {ctx}", meaning)
            instruments.append(Definition(mi.group("term").lower(), meaning, _shorten(mi.group("meaning")), sid,
                                          "instrument", verb=mi.group("verb").lower()))
    if not instruments:
        for cl in clauses:
            mg = _DEF_INSTRUMENT_GENERAL.match(cl.strip())
            if mg and mg.group("term").lower() not in ("object", "vehicle", "student", "body"):
                instruments.append(Definition(mg.group("term").lower(), mg.group("meaning"), _shorten(mg.group("meaning")), sid,
                                              "instrument", verb=mg.group("verb").lower()))
    if instruments:
        if len(instruments) == 2:
            instruments[0].pair_term, instruments[1].pair_term = instruments[1].term, instruments[0].term
        return instruments
    mt = _DEF_THIS_CALLED.match(text)
    if mt:   # 'Every conductor opposes the flow of current, and this opposition is called its resistance.'
        pre = mt.group("pre").strip().rstrip(",")
        meaning = f"{mt.group('noun').lower()}: {pre[0].lower() + pre[1:]}"
        out.append(Definition(mt.group("term").lower(), meaning, _shorten(meaning), sid, "quantity"))
        return out
    for rx in (_DEF_CALLED, _DEF_MEANS):
        m = rx.match(text)
        if m:
            term = m.group("term").lower()
            cat = "instrument" if term.endswith(_INSTRUMENT_SUFFIX) else "quantity"
            out.append(Definition(term, m.group("meaning"), _shorten(m.group("meaning")), sid, cat))
            return out
    return out


def _relationship(sid: str, text: str) -> Optional[Relationship]:
    text = normalise_quantity_names(text)
    m = _REL_SAME_DEN.search(text)
    if m:
        out = m.group("out").lower()
        f = FORMULAS.get(out)
        var, fixed = m.group("var").lower(), m.group("fixed").lower()
        change, direction = _dirn(m.group("chg")), _dirn(m.group("dir"))
        result = f"{m.group('chg').lower()} {var} -> {m.group('dir').lower()} {out}"
    else:
        m = _REL_SAME_NUM.search(text)
        if not m:
            return None
        d = m.group("dir").lower()
        if d in _COMPARATIVE_OUTPUT:
            out, direction = _COMPARATIVE_OUTPUT[d]
        elif m.group("out"):
            out, direction = m.group("out").lower(), _dirn(d)
        else:
            return None
        f = FORMULAS.get(out)
        var, fixed = m.group("var").lower(), m.group("fixed").lower()
        change = _dirn(m.group("chg"))
        result = f"{m.group('chg').lower()} {var} -> {m.group('dir').lower()}" + (
            f" {m.group('out').lower()}" if m.group("out") else "")
    if f is None:
        return None
    try:
        consistent = relation_direction(f, var, change) == direction
    except InvalidInput:
        consistent = False
    subject = m.group("subject").lower()
    subject = subject[:-1] if subject.endswith("s") else subject
    return Relationship(sid, f.key, subject, f.output, direction, f"same {fixed}", var, change, result, consistent)


def _worked_example(sid: str, mentions: List[QuantityMention], f: Formula) -> Optional[WorkedExample]:
    num = next((q.quantity for q in mentions if q.quantity.dimension == f.numerator_dim), None)
    den = next((q.quantity for q in mentions if q.quantity.dimension == f.denominator_dim), None)
    stated = next((q.quantity for q in mentions if q.quantity.dimension == f.output_dim), None)
    if not (num and den and stated):
        return None
    sol = compute(f, num, den, stated.unit)
    verified = abs(sol.value - stated.value) <= 0.01 * max(1.0, abs(stated.value))
    return WorkedExample(sid, f.key, num.to_dict(), den.to_dict(), stated.to_dict(), sol.answer_text, verified)


_LONG_NAMES = {"km/h": "kilometres per hour", "m/s": "metre per second", "km": "kilometre", "m": "metre",
               "h": "hour", "min": "minute", "s": "second", "g/cm3": "grams per cubic centimetre",
               "kg/m3": "kilograms per cubic metre", "kg": "kilogram", "g": "gram", "cm3": "cubic centimetre",
               "N": "newton", "m2": "square metre", "cm2": "square centimetre", "Pa": "pascal",
               "N/m2": "newton per square metre", "N/cm2": "newton per square centimetre", "V": "volt",
               "A": "ampere", "mA": "milliampere", "ohm": "ohm (Ω)", "J": "joule", "kJ": "kilojoule", "W": "watt",
               "kW": "kilowatt"}


def _unit_meaning(clause: str, unit: str) -> str:
    long_name = _LONG_NAMES.get(unit, unit)
    dim = UNITS[unit][0]
    if re.search(r"basic unit", clause, re.I) and re.search(rf"basic unit of {re.escape(dim)}\b", clause, re.I) is not None or \
            (re.search(r"basic unit", clause, re.I) and not re.search(r"basic unit of \w+", clause, re.I)):
        return f"{long_name}, the basic unit of {dim}"
    if re.search(r"roads", clause, re.I):
        return f"{long_name}, a unit of {dim} used on roads"
    m = re.search(r"\b(?:used |given |usually given |measured )?in (?:the )?(laboratory|daily life|homes|schools|science)\b", clause, re.I)
    if m:
        return f"{long_name}, a unit of {dim} used in the {m.group(1).lower()}" if m.group(1).lower() == "laboratory" else f"{long_name}, a unit of {dim}"
    return f"{long_name}, a unit of {dim}"


def build_knowledge_map(passage: Passage) -> KnowledgeMap:
    """Extract the core-type knowledge map from a processed passage."""
    km = KnowledgeMap(passage_sha256=passage.sha256, sentences=[s.to_dict() for s in passage.sentences])
    sentence_types: Dict[str, List[str]] = {s.sid: [] for s in passage.sentences}
    formula_for_examples: Optional[Formula] = None
    # pass 1: formulas first, so worked examples can be verified against them
    for s in passage.sentences:
        f = detect_formula(s.text)
        if f:
            km.formulas.append(FormulaFact(s.sid, f.key, f.text))
            sentence_types[s.sid].append("quantitative:formula")
            formula_for_examples = formula_for_examples or f
    prev = None
    for s in passage.sentences:
        mentions = parse_quantities(s.text, s.sid)
        km.quantities.extend(m.to_dict() for m in mentions)
        for d in _definitions(s.sid, s.text):
            km.definitions.append(d)
            sentence_types[s.sid].append("definition")
        units = parse_unit_mentions(s.text)
        if units:
            parts = re.split(r",\s*but\s+|,\s*while\s+|;\s*", s.text)
            for u in units:
                forms = [u] + [a for a, c in UNIT_ALIASES.items() if c == u and len(a) > 1]
                clause = next((p for p in parts if any(re.search(r"(?<![\w/])" + re.escape(f) + r"(?![\w/])", p, re.I)
                                                       for f in forms)), s.text)
                km.unit_facts.append(UnitFact(s.sid, u, _unit_meaning(clause, u)))
            sentence_types[s.sid].append("unit_fact")
        if formula_for_examples and len(mentions) >= 3:
            ex = _worked_example(s.sid, mentions, formula_for_examples)
            if ex:
                km.examples.append(ex)
                sentence_types[s.sid].append("quantitative:worked_example")
        rel = _relationship(s.sid, s.text)
        if rel:
            km.relationships.append(rel)
            sentence_types[s.sid].append("quantitative:relationship")
        mc = _CAUSE_LEAD.match(s.text)
        if mc and prev is not None:
            km.cause_effects.append(CauseEffect(prev.sid, s.sid, prev.text.rstrip("."), mc.group("effect")))
            sentence_types[s.sid].append("cause_effect:effect")
            sentence_types[prev.sid].append("cause_effect:cause")
        else:
            mb = _BECAUSE.match(s.text)
            if mb:
                km.cause_effects.append(CauseEffect(s.sid, s.sid, mb.group("cause"), mb.group("effect")))
                sentence_types[s.sid].append("cause_effect")
        prev = s
    # compound quantity terms, e.g. "average speed", tied to a formula stated with "total ... total"
    for f in km.formulas:
        out = FORMULAS[f.key].output
        hits = [s.sid for s in passage.sentences if re.search(rf"\baverage {out}\b", s.text, re.I)]
        if hits:
            fs = passage.sentence(f.sid).text
            meaning = (f"total {FORMULAS[f.key].numerator} ÷ total {FORMULAS[f.key].denominator}"
                       if re.search(r"\btotal\b", fs, re.I) else f"{FORMULAS[f.key].numerator} ÷ {FORMULAS[f.key].denominator}")
            km.compound_terms.append({"term": f"average {out}", "sid": hits[0], "meaning": meaning, "all_sids": hits})
    for sid, types in sentence_types.items():
        if not types:
            km.unsupported.append({"sid": sid, "text": passage.sentence(sid).text,
                                   "reason": "no supported definition / cause-effect / quantitative pattern"})
    km.sentence_types = sentence_types
    km.concepts = _assign_concepts(km)
    return km


def _assign_concepts(km: KnowledgeMap) -> List[Concept]:
    """Deterministic concept IDs.

    Order: quantity definitions; the second term of each confusable instrument pair
    (its partner serves as the 'term confusion' distractor); formulas; relationships;
    remaining instrument definitions; state definitions; cause-effect links.
    """
    ordered: List[tuple] = []
    quantities = [d for d in km.definitions if d.category == "quantity"]
    instruments = [d for d in km.definitions if d.category == "instrument"]
    paired_second = [d for d in instruments if d.pair_term and instruments.index(d) % 2 == 1]
    others = [d for d in instruments if d not in paired_second]
    states = [d for d in km.definitions if d.category == "state"]
    for d in quantities + paired_second:
        ordered.append((d.term, "definition", [d.sid], {"definition": d.term}))
    for f in km.formulas:
        ordered.append((f.text, "quantitative", [f.sid], {"formula": f.key}))
    for r in km.relationships:
        label = f"{r.condition}, {r.result}"
        ordered.append((label, "quantitative", [r.sid], {"relationship": r.sid}))
    for d in others + states:
        ordered.append((d.term, "definition", [d.sid], {"definition": d.term}))
    for c in km.cause_effects:
        ordered.append((f"{c.effect} (because: {c.cause})", "cause_effect", [c.cause_sid, c.effect_sid], {"cause_effect": c.effect_sid}))
    return [Concept(f"C{i}", label, kt, sids, ref) for i, (label, kt, sids, ref) in enumerate(ordered, start=1)]
