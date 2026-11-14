"""Sequence A – environment and configuration (no model, no Pi)."""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_python_version():
    assert sys.version_info >= (3, 10), "Python 3.10+ required (ExecuTorch 1.4.0 wheels: 3.10-3.13)"


def test_core_requirements_pinned():
    for f in ("requirements.txt", "requirements-pi.txt"):
        for line in (ROOT / f).read_text().splitlines():
            line = line.split("#")[0].strip()
            if line and not line.startswith("-r"):
                assert "==" in line, f"{f}: '{line}' is not pinned"


def test_executorch_pin_matches_config(cfg):
    pi = (ROOT / "requirements-pi.txt").read_text()
    m = re.search(r"executorch==([\d.]+)", pi)
    assert m and m.group(1) == cfg.model["executorch_runner"]["expected_executorch_version"]


def test_config_files_parse():
    for f in ("config.yaml", "model_config.yaml", "synonyms.yaml", "item_contexts.yaml"):
        assert yaml.safe_load((ROOT / "config" / f).read_text())


def test_default_backend_is_local_llm(cfg):
    assert cfg.model["backend"] in ("executorch_runner", "llama_main")
    assert cfg.model["generation"]["temperature"] == 0.0
