"""Regression: deterministic stages must match data/expected_outputs exactly."""
import json

import pytest

from level_bridge.main import main


@pytest.mark.parametrize("stage", ["stage1_passage", "stage2_knowledge_map", "stage3_key_term_registry"])
def test_deterministic_stage_matches(cfg, stage):
    assert main(["process"]) == 0
    got = json.loads((cfg.outputs_dir / f"{stage}.json").read_text())
    exp = json.loads((cfg.root / "data" / "expected_outputs" / f"{stage}.json").read_text())
    assert got == exp


def test_template_item_bank_matches(cfg):
    assert main(["build", "--backend", "template"]) == 0
    got = json.loads((cfg.outputs_dir / "stage5_item_bank.json").read_text())
    exp = json.loads((cfg.root / "data" / "expected_outputs" / "stage5_item_bank_TEMPLATE.json").read_text())
    assert got == exp


def test_priya_report_matches_except_timings(cfg):
    assert main(["demo", "--backend", "template", "--answers", "data/test_cases/priya_answers.json",
                 "--run-id", "pytest_regress"]) == 0
    got = json.loads((cfg.outputs_dir / "learning_report_pytest_regress.json").read_text())
    exp = json.loads((cfg.root / "data" / "expected_outputs" / "priya_learning_report_TEMPLATE.json").read_text())
    for k in ("placement", "rung_path", "end_reason", "concepts", "scores", "teacher_notes"):
        assert got[k] == exp[k], k
