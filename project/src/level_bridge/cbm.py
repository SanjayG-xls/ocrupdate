"""Certainty-based marking (Gardner-Medwin), exactly as stated in the report (p.3).

| Response | Certainty 1 | Certainty 2 | Certainty 3 |
|----------|-------------|-------------|-------------|
| Correct  | +1          | +2          | +3          |
| Wrong    | 0           | -2          | -6          |
"""

from __future__ import annotations

from typing import Dict, Optional

DEFAULT_TABLE = {"correct": {1: 1, 2: 2, 3: 3}, "wrong": {1: 0, 2: -2, 3: -6}}


class CBM:
    """Certainty-based marking with a configurable table (defaults to the report's)."""

    def __init__(self, table: Optional[Dict[str, Dict[int, int]]] = None) -> None:
        t = table or DEFAULT_TABLE
        self.table = {k: {int(c): int(v) for c, v in t[k].items()} for k in ("correct", "wrong")}

    def mark(self, correct: bool, certainty: int) -> int:
        if certainty not in (1, 2, 3):
            raise ValueError(f"certainty must be 1, 2 or 3 (got {certainty})")
        return self.table["correct" if correct else "wrong"][certainty]

    def max_per_answer(self) -> int:
        return max(self.table["correct"].values())
