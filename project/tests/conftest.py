"""Shared fixtures. All tests here run WITHOUT a model and WITHOUT a Raspberry Pi,
except tests/hardware (skipped unless LB_HARDWARE=1)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from level_bridge.cbm import CBM  # noqa: E402
from level_bridge.concept_states import ConceptTracker  # noqa: E402
from level_bridge.config import load_config  # noqa: E402
from level_bridge.model_runtime import TemplateRuntime  # noqa: E402
from level_bridge.pipeline import analyse, build  # noqa: E402
from level_bridge.scoring import ScoreLedger  # noqa: E402

PASSAGE = ROOT / "data" / "passages" / "speed_passage.txt"
FIX = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def cfg():
    return load_config(ROOT)


@pytest.fixture(scope="session")
def analysed(cfg):
    return analyse(cfg, PASSAGE)          # (passage, km, registry, validator)


@pytest.fixture()
def artifacts(cfg):
    return build(cfg, PASSAGE, TemplateRuntime())


@pytest.fixture()
def ledger(cfg):
    return ScoreLedger(cfg.app["scoring"]["bloom_weights"], CBM(cfg.app["scoring"]["cbm"]))


@pytest.fixture()
def priya_script():
    return json.loads((ROOT / "data" / "test_cases" / "priya_answers.json").read_text())


def load_fixture(name: str):
    return json.loads((FIX / name).read_text())
