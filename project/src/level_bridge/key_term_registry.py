"""Key-term registry (report p.3): canonical term, source sentence, meaning,
preservation requirement and permitted synonyms.

Registry policy (documented, deterministic):

* **Included, preservation = required:** defined quantities and instruments, units
  stated in the passage, formulas, and compound quantities such as "average speed".
* **Not included:** background *state* definitions (e.g. "motion" – "an object is said
  to be in motion when…"). They remain in the knowledge map but are not checked by the
  coverage validator.

For the speed passage this yields 7 entries, matching the report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field
from typing import Dict, List

from .knowledge_map import KnowledgeMap


@dataclass
class RegistryEntry:
    canonical: str
    sid: str
    meaning: str
    preservation: str            # "required" | "optional"
    category: str                # quantity | instrument | unit | formula | compound
    synonyms: List[str] = field(default_factory=list)

    def surface_forms(self) -> List[str]:
        return [self.canonical, *self.synonyms]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class KeyTermRegistry:
    entries: List[RegistryEntry]

    def required(self) -> List[RegistryEntry]:
        return [e for e in self.entries if e.preservation == "required"]

    def get(self, canonical: str) -> RegistryEntry:
        for e in self.entries:
            if e.canonical == canonical:
                return e
        raise KeyError(canonical)

    def to_dict(self) -> Dict[str, object]:
        return {"count": len(self.entries), "required_count": len(self.required()),
                "policy": "quantities, instruments, units, formulas and compound quantities are required; "
                          "state definitions stay in the knowledge map only",
                "entries": [e.to_dict() for e in self.entries]}


def _sid_num(sid: str) -> int:
    return int(sid[1:])


def build_registry(km: KnowledgeMap, synonyms: Dict[str, List[str]]) -> KeyTermRegistry:
    """Build the registry from a knowledge map, ordered by source sentence."""
    entries: List[RegistryEntry] = []
    for d in km.definitions:
        if d.category in ("quantity", "instrument"):
            entries.append(RegistryEntry(d.term, d.sid, d.meaning, "required", d.category, synonyms.get(d.term, [])))
    for f in km.formulas:
        canon = f.text.lower()
        entries.append(RegistryEntry(canon, f.sid, "how " + canon.split(" = ")[0] + " is calculated", "required",
                                     "formula", synonyms.get(canon, [])))
    for u in km.unit_facts:
        entries.append(RegistryEntry(u.unit, u.sid, u.meaning, "required", "unit", synonyms.get(u.unit.lower(), [])))
    for c in km.compound_terms:
        entries.append(RegistryEntry(c["term"], c["sid"], c["meaning"], "required", "compound", synonyms.get(c["term"], [])))
    seen, unique = set(), []
    for e in sorted(entries, key=lambda e: (_sid_num(e.sid), e.category != "quantity")):
        if e.canonical not in seen:
            seen.add(e.canonical)
            unique.append(e)
    return KeyTermRegistry(unique)


def term_present(entry: RegistryEntry, text: str) -> bool:
    """Case-insensitive whole-phrase match of the canonical term or a permitted synonym."""
    low = text.lower()
    for form in entry.surface_forms():
        f = form.lower()
        if re.search(r"(?<![\w/])" + re.escape(f) + r"(?![\w/])", low):
            return True
    return False
