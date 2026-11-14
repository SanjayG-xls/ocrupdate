"""LEARN: source tags. Each explanation sentence is shown with the passage sentence it comes from, e.g. ``[S3]``.

Tagging is applied when the text is *displayed*; the validated explanation text is not
changed, so validation results and the stored report stay exactly as before.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional

_STOP = set("""a an the of in on at to by for and or but is are was were be been it its this that these those
with as from has have had than then so such which who what when where why how one two per unit also""".split())


def _words(text: str) -> set:
    out = set()
    for w in re.findall(r"[a-z]+", text.lower()):
        if len(w) > 2 and w not in _STOP:
            out.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return out


def _numbers(text: str) -> set:
    return set(re.findall(r"(?<![\w.])\d+(?:\.\d+)?", text))


def _idf(passage_sentences: List[tuple]) -> Dict[str, float]:
    df: Dict[str, int] = {}
    for _, text in passage_sentences:
        for w in _words(text):
            df[w] = df.get(w, 0) + 1
    n = max(1, len(passage_sentences))
    return {w: math.log((n + 1) / c) for w, c in df.items()}


def best_source(sentence: str, passage_sentences: List[tuple], min_overlap: float = 1.2, km=None) -> Optional[str]:
    """Sid of the passage sentence this explanation sentence comes from.

    Order: (1) shared numbers (worked example); (2) the formula sentence when the line states the rule;
    (3) the relationship whose fixed quantity the line names ('if the distance is the same');
    (4) content-word overlap weighted by rarity in the passage (common words such as 'speed' count little).
    """
    low = sentence.lower()
    ns = _numbers(sentence)
    if ns:
        hits = [(len(ns & _numbers(t)), sid) for sid, t in passage_sentences if ns & _numbers(t)]
        if hits:
            return max(hits)[1]
    if km is not None:
        if km.formulas and re.search(r"÷|\bdivid|\bdivided by\b", low):
            return km.formulas[0].sid
        m = re.search(r"\b(?:the )?(\w+) (?:is|stays|remains) the same\b|\bsame (\w+)\b", low)
        if m:
            fixed = m.group(1) or m.group(2) or ""
            if fixed.endswith("s") and not fixed.endswith("ss"):
                fixed = fixed[:-1]
            rel = next((r for r in km.relationships if r.condition == f"same {fixed}"), None)
            if rel:
                return rel.sid
    idf = _idf(passage_sentences)
    ws = _words(sentence)
    best, best_score = None, 0.0
    for sid, text in passage_sentences:
        score = sum(idf.get(w, 0.0) for w in ws & _words(text))
        if score > best_score:
            best, best_score = sid, score
    return best if best_score >= min_overlap else None


def _split(text: str) -> List[str]:
    parts: List[str] = []
    for line in text.splitlines():
        if not line.strip():
            parts.append(line)
            continue
        parts.extend(s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", line.strip()) if s)
    return parts


def tag_text(text: str, passage, km=None) -> str:
    """One sentence per line, each followed by its source tag when one is found."""
    sents = [(s.sid, s.text) for s in passage.sentences]
    out = []
    for s in _split(text):
        if not s.strip():
            continue
        sid = best_source(s, sents, km=km)
        out.append(f"{s} [{sid}]" if sid else s)
    return "\n".join(out)


def coverage(text: str, passage, km=None) -> float:
    """Share of explanation sentences that received a tag (reported, not used for routing)."""
    sents = [(s.sid, s.text) for s in passage.sentences]
    parts = [s for s in _split(text) if s.strip()]
    if not parts:
        return 0.0
    return sum(1 for s in parts if best_source(s, sents, km=km)) / len(parts)
