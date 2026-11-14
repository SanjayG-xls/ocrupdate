"""Sentence segmentation with stable sentence IDs (S1, S2, ...)."""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Dict, List

_ABBREVIATIONS = ["e.g.", "i.e.", "etc.", "Mr.", "Mrs.", "Dr.", "vs.", "approx.", "Fig.", "No."]
_PLACEHOLDER = "⁣"  # invisible separator used to protect abbreviation dots


@dataclass(frozen=True)
class Sentence:
    """A passage sentence with a stable identifier."""

    sid: str
    index: int
    text: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def segment(text: str) -> List[Sentence]:
    """Split normalised passage text into sentences.

    Splits after ``.``, ``!`` or ``?`` followed by whitespace and an upper-case letter,
    a digit or an opening quote. Decimal numbers (``2.5``) and common abbreviations
    are protected. Semicolons do not split sentences.
    """
    protected = text
    for abbr in _ABBREVIATIONS:
        protected = protected.replace(abbr, abbr.replace(".", _PLACEHOLDER))
    protected = re.sub(r"(\d)\.(\d)", lambda m: f"{m.group(1)}{_PLACEHOLDER}{m.group(2)}", protected)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(“])", protected.strip())
    sentences: List[Sentence] = []
    for part in parts:
        restored = part.replace(_PLACEHOLDER, ".").strip()
        if restored:
            idx = len(sentences) + 1
            sentences.append(Sentence(sid=f"S{idx}", index=idx, text=restored))
    return sentences
