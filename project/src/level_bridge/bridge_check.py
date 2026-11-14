"""Bridge check (report rule R4): a Transfer item shown with the unmodified textbook extract.

The extract is reproduced verbatim from the passage. Vocabulary glosses are kept in a
separate list and are not inserted into the original sentences. One correct transfer
answer is initial evidence of application in a new context – not long-term mastery.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List

from .key_term_registry import KeyTermRegistry
from .passage_processor import Passage
from .question_generator import Item


@dataclass
class BridgeCheck:
    item_id: str
    extract_sids: List[str]
    extract: str
    glosses: List[Dict[str, str]]
    verbatim: bool
    note: str = "Initial evidence of transfer only; not long-term mastery."

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def build_bridge(passage: Passage, item: Item, registry: KeyTermRegistry) -> BridgeCheck:
    """Assemble the original-text extract for the transfer item's source sentences."""
    sids = sorted(set(item.source_sids), key=lambda s: int(s[1:]))
    extract = " ".join(passage.sentence(sid).text for sid in sids)
    verbatim = all(passage.sentence(sid).text in passage.text for sid in sids)
    glosses = [{"term": e.canonical, "gloss": e.meaning} for e in registry.entries if e.sid in sids]
    return BridgeCheck(item.item_id, sids, extract, glosses, verbatim)
