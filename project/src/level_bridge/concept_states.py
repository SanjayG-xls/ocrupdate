"""Concept-state model (report p.3).

States: Learning, Provisional, Fragile, Repaired, Transferred, Consolidated.

Legal transitions (event -> new state):

=============  =====================  ===============================================
From           Event                  To
=============  =====================  ===============================================
Learning       correct_first          Provisional
Learning       wrong_first            Fragile
Provisional    wrong                  Fragile        (inconsistent response)
Repaired       wrong                  Fragile        (inconsistent response)
Transferred    wrong                  Fragile        (inconsistent response)
Fragile        second_chance_correct  Repaired       (NOT counted as mastery)
Fragile        second_chance_wrong    Fragile        (unresolved)
Provisional    transfer_correct       Transferred    (initial evidence only)
Repaired       transfer_correct       Transferred
Provisional    transfer_wrong         Fragile
Repaired       transfer_wrong         Fragile
Transferred    independent_correct    Consolidated   (PROPOSED – disabled by default)
=============  =====================  ===============================================

Everything else raises :class:`IllegalTransition`. In particular a single correct
answer never produces Consolidated, and Repaired never jumps to Provisional.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple


class State(str, Enum):
    LEARNING = "Learning"
    PROVISIONAL = "Provisional"
    FRAGILE = "Fragile"
    REPAIRED = "Repaired"
    TRANSFERRED = "Transferred"
    CONSOLIDATED = "Consolidated"


class IllegalTransition(ValueError):
    """Raised for a transition the state model does not allow."""


TRANSITIONS: Dict[Tuple[State, str], State] = {
    (State.LEARNING, "correct_first"): State.PROVISIONAL,
    (State.LEARNING, "wrong_first"): State.FRAGILE,
    (State.PROVISIONAL, "wrong"): State.FRAGILE,
    (State.REPAIRED, "wrong"): State.FRAGILE,
    (State.TRANSFERRED, "wrong"): State.FRAGILE,
    (State.FRAGILE, "second_chance_correct"): State.REPAIRED,
    (State.FRAGILE, "second_chance_wrong"): State.FRAGILE,
    (State.PROVISIONAL, "transfer_correct"): State.TRANSFERRED,
    (State.REPAIRED, "transfer_correct"): State.TRANSFERRED,
    (State.PROVISIONAL, "transfer_wrong"): State.FRAGILE,
    (State.REPAIRED, "transfer_wrong"): State.FRAGILE,
    (State.TRANSFERRED, "independent_correct"): State.CONSOLIDATED,
}
PROPOSED_EVENTS = {"independent_correct"}


@dataclass
class ConceptTracker:
    """Tracks the state and history of every concept in a session."""

    concept_ids: List[str]
    enable_consolidated: bool = False
    states: Dict[str, State] = field(default_factory=dict)
    history: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    flags: Dict[str, List[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for cid in self.concept_ids:
            self.states.setdefault(cid, State.LEARNING)
            self.history.setdefault(cid, [])
            self.flags.setdefault(cid, [])

    def apply(self, cid: str, event: str, item_id: str = "") -> State:
        """Apply ``event`` to concept ``cid`` and return the new state."""
        if event in PROPOSED_EVENTS and not self.enable_consolidated:
            raise IllegalTransition("Consolidated is a proposed state (needs multiple independent assessments, "
                                    "e.g. a later session); enable routing.enable_consolidated_state to use it")
        cur = self.states[cid]
        key = (cur, event)
        if key not in TRANSITIONS:
            raise IllegalTransition(f"{cid}: '{event}' is not allowed from {cur.value}")
        new = TRANSITIONS[key]
        self.states[cid] = new
        self.history[cid].append({"item": item_id, "event": event, "from": cur.value, "to": new.value})
        return new

    def flag(self, cid: str, note: str) -> None:
        if note not in self.flags[cid]:
            self.flags[cid].append(note)

    def to_dict(self) -> Dict[str, object]:
        return {cid: {"state": self.states[cid].value, "history": self.history[cid], "flags": self.flags[cid]}
                for cid in self.concept_ids}
