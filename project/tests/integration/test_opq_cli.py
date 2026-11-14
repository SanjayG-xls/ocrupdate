"""Sequences O, P, Q – offline check, benchmark harness, end-to-end CLI (template backend, no model)."""
import json

from level_bridge.main import main
from level_bridge.offline_checker import check_offline


def test_offline_report_structure():
    rep = check_offline("executorch_runner", probe_network=False)
    assert rep["backend_is_local"] and rep["cloud_inference_possible_in_app"] is False
    assert not check_offline("cloud", probe_network=False)["backend_is_local"]


def test_end_to_end_template(cfg, tmp_path):
    code = main(["demo", "--backend", "template", "--answers", "data/test_cases/priya_answers.json",
                 "--run-id", "pytest_e2e"])
    assert code == 0
    rep = json.loads((cfg.outputs_dir / "learning_report_pytest_e2e.json").read_text())
    assert rep["run"]["is_llm_inference"] is False
    assert rep["run"]["llm_outputs_accepted"] == 0
    s = rep["scores"]
    assert (s["assessment_credits"], s["assessment_max"], s["recovery_credits"], s["total_earned"],
            s["cbm_total"], s["cbm_max"]) == (25, 36, 3, 28, 6, 18)
    assert (cfg.outputs_dir / "knowledge_map_pytest_e2e.json").exists()


def test_missing_model_fails_loudly(tmp_path):
    cfgfile = tmp_path / "m.yaml"
    cfgfile.write_text("backend: executorch_runner\nexecutorch_runner:\n  pte_path: /nonexistent.pte\n"
                       "  tokenizer_path: /nonexistent.json\ngeneration: {temperature: 0.0}\n")
    assert main(["--model-config", str(cfgfile), "build"]) == 3
    assert main(["--model-config", str(cfgfile), "build", "--allow-template-fallback"]) == 0


def test_benchmark_template_labelled_non_llm(cfg):
    assert main(["benchmark", "--backend", "template", "--warmup", "1", "--runs", "2", "--run-id", "pytest_bench"]) == 0
    b = json.loads((cfg.outputs_dir / "benchmark_pytest_bench.json").read_text())
    assert b["is_llm_inference"] is False and "NON-LLM" in b["label"]
    assert b["median"]["generated_tokens"] is None and b["median"]["ttft_ms_first_call"] is None
    assert len([r for r in b["runs"] if r["phase"] == "measured"]) == 2
    assert (cfg.outputs_dir / "benchmark_pytest_bench.csv").exists()


def test_process_command(cfg):
    assert main(["process"]) == 0
    km = json.loads((cfg.outputs_dir / "stage2_knowledge_map.json").read_text())
    assert km


def test_unsupported_passage_exit_code(tmp_path):
    p = tmp_path / "bad.txt"
    p.write_text("Too short.")
    assert main(["process", "--passage", str(p)]) == 2


def test_cpu_meter_measures_busy_interval():
    import time
    from level_bridge.benchmark import CpuMeter
    with CpuMeter() as c:
        t = time.perf_counter()
        while time.perf_counter() - t < 0.6:
            pass
    assert c.process_pct is not None and c.process_pct > 50
    with CpuMeter() as short:
        pass
    assert short.system_pct is None and short.process_pct is None   # too short to measure honestly


def test_capture_for_report_template_run(cfg, tmp_path):
    import shutil
    import subprocess
    import sys
    run = tmp_path / "e2e_test"
    run.mkdir()
    assert main(["demo", "--backend", "template", "--answers", "data/test_cases/priya_answers.json",
                 "--run-id", "cap_test"]) == 0
    assert main(["benchmark", "--backend", "template", "--warmup", "0", "--runs", "1", "--run-id", "cap_test"]) == 0
    for f in cfg.outputs_dir.glob("*cap_test*"):
        shutil.copy(f, run)
    cp = subprocess.run([sys.executable, str(cfg.root / "scripts/capture_for_report.py"), str(run)],
                        capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr
    md = (run / "REPORT_SUMMARY.md").read_text()
    assert "NON-LLM RUN" in md and "25 / 36" in md and "+6 / 18" in md
    m = json.loads((run / "report_metrics.json").read_text())
    assert m["is_llm_inference"] is False and m["tokens_per_s_median"] is None
