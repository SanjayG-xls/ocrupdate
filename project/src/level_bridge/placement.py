"""Placement (report rule R1): three probes on the original text -> starting rung.

Placement is a passage-specific starting point for support. It is NOT a diagnosis
of general reading proficiency, and it earns no credits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

DEFAULT_RULE = {0: 1, 1: 1, 2: 2, 3: 3}


@dataclass
class PlacementResult:
    score: int
    out_of: int
    start_rung: int
    responses: List[Dict[str, object]]
    note: str = "Passage-specific starting point for support; not a diagnosis of reading proficiency."

    def to_dict(self) -> Dict[str, object]:
        return {"score": self.score, "out_of": self.out_of, "start_rung": self.start_rung,
                "rule": "R1: 0-1 -> L1, 2 -> L2, 3 -> L3", "responses": self.responses, "note": self.note}


def start_rung(score: int, rule: Dict[int, int] = DEFAULT_RULE) -> int:
    """Apply R1. ``rule`` maps the number of correct probes to the starting rung."""
    rule = {int(k): int(v) for k, v in rule.items()}
    if score not in rule:
        raise ValueError(f"placement score {score} outside {sorted(rule)}")
    return rule[score]


def place(responses: List[Dict[str, object]], rule: Dict[int, int] = DEFAULT_RULE) -> PlacementResult:
    """``responses`` are dicts with at least ``item_id`` and ``correct``."""
    score = sum(1 for r in responses if r.get("correct"))
    return PlacementResult(score, len(responses), start_rung(score, rule), responses)
