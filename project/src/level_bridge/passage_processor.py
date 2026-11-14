"""Passage ingestion: reading, normalisation, length validation and segmentation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from .sentence_segmenter import Sentence, segment


class PassageError(ValueError):
    """Raised when a passage cannot be processed (empty, far outside the length band)."""


@dataclass
class Passage:
    """A normalised passage with sentence IDs and validation notes."""

    source: str
    text: str
    word_count: int
    sentences: List[Sentence]
    warnings: List[str] = field(default_factory=list)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def sentence(self, sid: str) -> Sentence:
        for s in self.sentences:
            if s.sid == sid:
                return s
        raise KeyError(sid)

    def to_dict(self) -> Dict[str, object]:
        return {"source": self.source, "word_count": self.word_count, "sha256": self.sha256,
                "warnings": self.warnings, "sentences": [s.to_dict() for s in self.sentences]}


def normalise(text: str) -> str:
    """Normalise quotes, dashes, hyphenated line breaks and whitespace."""
    t = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("–", "-").replace("—", " - ")
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def count_words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:[/'.][A-Za-z0-9]+)*", text))


def load_passage(path: Path, limits: Dict[str, int]) -> Passage:
    """Read and validate a passage file."""
    raw = Path(path).read_text(encoding="utf-8")
    return process_text(raw, limits, source=str(path))


def process_text(raw: str, limits: Dict[str, int], source: str = "<text>") -> Passage:
    """Normalise, validate length and segment ``raw`` text."""
    text = normalise(raw)
    if not text:
        raise PassageError("Passage is empty")
    words = count_words(text)
    warnings: List[str] = []
    if words < limits["hard_min_words"] or words > limits["hard_max_words"]:
        raise PassageError(
            f"Passage has {words} words; supported range is {limits['hard_min_words']}-{limits['hard_max_words']}")
    if words < limits["target_min_words"] or words > limits["target_max_words"]:
        warnings.append(f"Passage has {words} words; PS1 target is {limits['target_min_words']}-{limits['target_max_words']}")
    sentences = segment(text)
    if len(sentences) < 2:
        raise PassageError("Passage must contain at least two sentences")
    return Passage(source=source, text=text, word_count=words, sentences=sentences, warnings=warnings)
