"""Build-phase orchestration shared by the CLI, the benchmark and the tests.

T_build = T_preprocessing + T_model_generation + T_validation (report §5.2). Model
loading is NOT inside T_build; it is measured separately (cold start / model load).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .concept_validator import ConceptValidator
from .config import AppConfig
from .explanation_generator import Explanation, ExplanationGenerator
from .key_term_registry import KeyTermRegistry, build_registry
from .knowledge_map import KnowledgeMap, build_knowledge_map
from .model_runtime import ModelRuntime
from .passage_processor import Passage, load_passage
from .question_generator import ItemBank, QuestionGenerator, reword_stems

log = logging.getLogger("level_bridge.pipeline")


@dataclass
class BuildArtifacts:
    passage: Passage
    km: KnowledgeMap
    registry: KeyTermRegistry
    validator: ConceptValidator
    explanations: Dict[str, Explanation]
    bank: ItemBank
    stem_rewording: Dict[str, object]
    timings: Dict[str, float] = field(default_factory=dict)
    generation_calls: list = field(default_factory=list)

    @property
    def llm_outputs_accepted(self) -> int:
        n = sum(1 for k in ("summary", "l1", "l2") if self.explanations[k].source in ("llm", "llm_retry"))
        return n + int(self.stem_rewording.get("accepted", 0))


def resolve_input(cfg: AppConfig, p) -> Path:
    """A relative input path is taken from the working directory if it exists there, else from the project root."""
    p = Path(p)
    if p.is_absolute() or p.exists():
        return p
    return cfg.root / p


def analyse(cfg: AppConfig, passage_path: Path) -> tuple:
    """Preprocessing: passage -> sentences -> knowledge map -> registry -> validator."""
    passage_path = resolve_input(cfg, passage_path)
    passage = load_passage(passage_path, cfg.app["passage"])
    try:  # record a project-relative source so outputs do not depend on the working directory
        passage.source = Path(passage_path).resolve().relative_to(cfg.root).as_posix()
    except ValueError:
        passage.source = str(passage_path)
    km = build_knowledge_map(passage)
    registry = build_registry(km, cfg.synonyms)
    ex = cfg.app["explanations"]
    validator = ConceptValidator(passage, km, registry, ex["summary_min_term_coverage"], ex["l1_max_words_per_sentence"])
    return passage, km, registry, validator


def build(cfg: AppConfig, passage_path: Path, runtime: ModelRuntime) -> BuildArtifacts:
    """Run the complete build phase with timing breakdown."""
    t0 = time.perf_counter()
    passage, km, registry, validator = analyse(cfg, passage_path)
    t_pre = time.perf_counter() - t0
    ex_cfg = cfg.app["explanations"]
    gen = ExplanationGenerator(passage, km, registry, validator, runtime, ex_cfg["max_attempts"], ex_cfg["max_new_tokens"])
    t1 = time.perf_counter()
    explanations = gen.build_all()
    bank = QuestionGenerator(km, cfg.item_contexts).build()
    rew = {"attempted": False}
    if cfg.app["questions"].get("llm_stem_rewording", True):
        rew = reword_stems(bank, runtime, ex_cfg["max_new_tokens"].get("question_stems", 220))
    t_gen_total = time.perf_counter() - t1
    calls = [r.to_dict() for r in gen.generation_log]
    if rew.get("generation"):
        calls.append({"kind": "question_stems", **rew["generation"]})
    t_model = sum(float(c.get("wall_time_s") or 0.0) for c in calls)
    timings = {
        "t_preprocessing_s": round(t_pre, 4),
        "t_model_generation_s": round(t_model, 4),
        "t_validation_and_templates_s": round(max(0.0, t_gen_total - t_model), 4),
        "t_build_s": round(time.perf_counter() - t0, 4),
    }
    return BuildArtifacts(passage, km, registry, validator, explanations, bank, rew, timings, calls)
