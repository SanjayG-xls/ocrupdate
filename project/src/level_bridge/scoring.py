"""Learning credits (report p.3) and the session score ledger.

* **Assessment credits** = Bloom weight × certainty, only when correct
  (Recall 1, Understand 2, Apply 3, Transfer 4; certainty 1-3).
* **Assessment maximum** = sum over the original assessment items delivered in the
  session (assessment + transfer items) at certainty 3.
* **Recovery credits** = Bloom weight of a repaired item; reported OUTSIDE the maximum.
* **CBM** applies to every scored answer, including second chances. Placement earns nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from .cbm import CBM


@dataclass
class LedgerEntry:
    item_id: str
    kind: str                 # assessment | transfer | second_chance
    cognitive_level: str
    correct: bool
    certainty: int
    assessment_credits: int
    recovery_credits: int
    cbm: int
    max_assessment_credits: int


@dataclass
class ScoreLedger:
    bloom_weights: Dict[str, int]
    cbm: CBM
    entries: List[LedgerEntry] = field(default_factory=list)

    def weight(self, level: str) -> int:
        if level not in self.bloom_weights:
            raise ValueError(f"unknown cognitive level '{level}'")
        return int(self.bloom_weights[level])

    def record_assessment(self, item_id: str, kind: str, level: str, correct: bool, certainty: int) -> LedgerEntry:
        """Score an original assessment or transfer item."""
        w = self.weight(level)
        e = LedgerEntry(item_id, kind, level, correct, certainty, w * certainty if correct else 0, 0,
                        self.cbm.mark(correct, certainty), w * 3)
        self.entries.append(e)
        return e

    def record_second_chance(self, item_id: str, level: str, correct: bool, certainty: int) -> LedgerEntry:
        """Score a second-chance item: recovery credits (= Bloom weight) only if correct; CBM always."""
        w = self.weight(level)
        e = LedgerEntry(item_id, "second_chance", level, correct, certainty, 0, w if correct else 0,
                        self.cbm.mark(correct, certainty), 0)
        self.entries.append(e)
        return e

    # ------------------------------------------------------------------ totals
    @property
    def assessment_credits(self) -> int:
        return sum(e.assessment_credits for e in self.entries)

    @property
    def assessment_max(self) -> int:
        return sum(e.max_assessment_credits for e in self.entries)

    @property
    def recovery_credits(self) -> int:
        return sum(e.recovery_credits for e in self.entries)

    @property
    def total_earned(self) -> int:
        return self.assessment_credits + self.recovery_credits

    @property
    def cbm_total(self) -> int:
        return sum(e.cbm for e in self.entries)

    @property
    def cbm_max(self) -> int:
        return self.cbm.max_per_answer() * len(self.entries)

    def summary(self) -> Dict[str, object]:
        return {
            "assessment_credits": self.assessment_credits,
            "assessment_max": self.assessment_max,
            "recovery_credits": self.recovery_credits,
            "recovery_note": "recovery credits are outside the assessment maximum",
            "total_earned": self.total_earned,
            "cbm_total": self.cbm_total,
            "cbm_max": self.cbm_max,
            "scored_answers": len(self.entries),
            "entries": [asdict(e) for e in self.entries],
        }
