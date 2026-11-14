#!/usr/bin/env python3
"""Turn a run folder into a report-ready summary (REPORT_SUMMARY.md + report_metrics.json).

    python scripts/capture_for_report.py                      # latest outputs/e2e_* folder
    python scripts/capture_for_report.py outputs/e2e_<time>   # a specific folder

Every value is read from an evidence file in that folder. Anything missing is written as
"not measured". Nothing is estimated. A template (non-LLM)
run is labelled as such at the top of the summary.
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
NR = "not measured"


def _latest_run() -> Path:
    runs = sorted(glob.glob(str(ROOT / "outputs" / "e2e_*")))
    if not runs:
        sys.exit("No outputs/e2e_* folder found. Run: bash scripts/run_end_to_end.sh")
    return Path(runs[-1])


def _load(d: Path, pattern: str) -> Optional[Dict[str, Any]]:
    files = sorted(d.glob(pattern))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _get(obj: Any, *path, default=None):
    for p in path:
        if obj is None:
            return default
        obj = obj.get(p) if isinstance(obj, dict) else None
    return default if obj is None else obj


def _fmt(v, unit: str = "", nd: int = 2) -> str:
    if v is None:
        return NR
    if isinstance(v, float):
        v = f"{v:.4g}"
    return f"{v}{(' ' + unit) if unit else ''}"


def main() -> int:
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else _latest_run()
    if not d.is_absolute():
        d = (Path.cwd() / d) if (Path.cwd() / d).exists() else ROOT / d
    rep = _load(d, "learning_report_*.json")
    bench = _load(d, "benchmark_*.json")
    env = _load(d, "environment_report.json")
    mc = _load(d, "model_check.json")
    off = _load(d, "offline_check.json")
    inf = _load(d, "inference_*.json")
    tests = (d / "test_summary.txt").read_text(encoding="utf-8") if (d / "test_summary.txt").exists() else ""

    is_llm = bool(_get(rep, "run", "is_llm_inference"))
    backend = _get(rep, "run", "backend", "backend", default=NR)
    dev = _get(bench, "device", default={})
    med = _get(bench, "median", default={})
    runs = _get(bench, "runs", default=[]) or []
    measured = [r for r in runs if r.get("phase") == "measured"]
    scores = _get(rep, "scores", default={})
    rl = _get(rep, "run", "timings", "repair_latency", default={})
    m_tests = re.findall(r"(\d+) passed|(\d+) failed|(\d+) skipped", tests.splitlines()[-1] if tests.strip() else "")
    test_line = tests.strip().splitlines()[-1].strip("= ") if tests.strip() else NR

    metrics = {
        "run_folder": d.name, "backend": backend, "is_llm_inference": is_llm,
        "fallback_used": _get(rep, "run", "backend", "fallback_used"),
        "device_model": dev.get("device_model"), "machine": dev.get("machine"), "mem_total_mb": dev.get("mem_total_mb"),
        "python": _get(env, "python"), "executorch": _get(env, "packages", "executorch"),
        "torch": _get(env, "packages", "torch"), "transformers": _get(env, "packages", "transformers"),
        "runner_importable": _get(env, "executorch_llm_runner_importable"),
        "model_file_mb": _get(bench, "model_file_mb") or _get(mc, "pte_path", "size_mb"),
        "model_sha256": _get(mc, "pte_path", "sha256"),
        "cold_start_s": _get(bench, "cold_start_s"), "model_load_s": _get(bench, "model_load_s"),
        "warmup_runs": _get(bench, "warmup_runs"), "measured_runs": _get(bench, "measured_runs"),
        "t_build_median_s": med.get("t_build_s"), "t_preprocessing_median_s": med.get("t_preprocessing_s"),
        "t_model_generation_median_s": med.get("t_model_generation_s"),
        "t_validation_median_s": med.get("t_validation_and_templates_s"),
        "ttft_first_call_median_ms": med.get("ttft_ms_first_call"),
        "generated_tokens_median": med.get("generated_tokens"), "tokens_per_s_median": med.get("tokens_per_s"),
        "cpu_system_pct_median": med.get("cpu_system_pct"), "cpu_process_pct_median": med.get("cpu_process_pct"),
        "peak_rss_mb": _get(bench, "peak_rss_mb"),
        "cpu_temp_start_c": measured[0].get("cpu_temp_before_c") if measured else None,
        "cpu_temp_end_c": _get(bench, "cpu_temp_end_c"), "throttled": _get(bench, "throttled"),
        "repair_latency_median_ms": rl.get("median_ms"), "repair_latency_max_ms": rl.get("max_ms"),
        "llm_outputs_accepted_session": _get(rep, "run", "llm_outputs_accepted"),
        "llm_outputs_accepted_per_benchmark_run": [r.get("llm_outputs_accepted") for r in measured] or None,
        "explanation_sources": _get(rep, "run", "explanation_sources"),
        "offline": _get(off, "offline"), "offline_backend_local": _get(off, "backend_is_local"),
        "placement": f"{_get(rep, 'placement', 'score')}/{_get(rep, 'placement', 'out_of')}" if rep else None,
        "rung_path": _get(rep, "rung_path"), "end_reason": _get(rep, "end_reason"),
        "assessment": f"{scores.get('assessment_credits')} / {scores.get('assessment_max')}" if scores else None,
        "recovery": scores.get("recovery_credits"), "total_earned": scores.get("total_earned"),
        "cbm": f"{scores.get('cbm_total'):+d} / {scores.get('cbm_max')}" if scores else None,
        "tests": test_line,
        "inference_runs_ok": [r.get("ok") for r in _get(inf, "runs", default=[])] or None,
    }
    (d / "report_metrics.json").write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")

    L = []
    L.append(f"# Level Bridge STEM – run evidence `{d.name}`\n")
    if not is_llm:
        L.append("> **NON-LLM RUN (template backend).** These numbers are pipeline timings without model "
                 "inference and must not be reported as on-device LLM performance.\n")
    if metrics["fallback_used"]:
        L.append("> **Model was unavailable – template fallback was used.**\n")
    L.append("## Device and software\n")
    L.append("| Item | Value |\n|---|---|")
    for k, lab in [("device_model", "Device"), ("machine", "Architecture"), ("mem_total_mb", "RAM (MB)"),
                   ("python", "Python"), ("executorch", "ExecuTorch"), ("torch", "torch"),
                   ("transformers", "transformers"), ("runner_importable", "TextLLMRunner importable"),
                   ("backend", "Inference backend"), ("model_file_mb", "Model file (MB)"),
                   ("model_sha256", "Model sha256")]:
        L.append(f"| {lab} | {_fmt(metrics[k])} |")
    L.append("\n## Performance (median of measured runs after warm-up)\n")
    L.append(f"Warm-up runs: {_fmt(metrics['warmup_runs'])} · measured runs: {_fmt(metrics['measured_runs'])}\n")
    L.append("| Metric | Value |\n|---|---|")
    for k, lab, u in [("cold_start_s", "Cold start (process start → model loaded)", "s"),
                      ("model_load_s", "Model load", "s"),
                      ("t_build_median_s", "T_build (passage → validated explanations + items)", "s"),
                      ("t_preprocessing_median_s", "  of which preprocessing", "s"),
                      ("t_model_generation_median_s", "  of which model generation", "s"),
                      ("t_validation_median_s", "  of which validation + templates", "s"),
                      ("ttft_first_call_median_ms", "Time to first token (first call)", "ms"),
                      ("generated_tokens_median", "Generated tokens per build", ""),
                      ("tokens_per_s_median", "Decode throughput", "tokens/s"),
                      ("cpu_system_pct_median", "CPU utilisation, system (all cores = 100 %)", "%"),
                      ("cpu_process_pct_median", "CPU utilisation, process (per core = 100 %)", "%"),
                      ("peak_rss_mb", "Peak memory (RSS)", "MB"),
                      ("repair_latency_median_ms", "Repair latency, median", "ms"),
                      ("repair_latency_max_ms", "Repair latency, max", "ms"),
                      ("cpu_temp_start_c", "CPU temperature, first measured run", "°C"),
                      ("cpu_temp_end_c", "CPU temperature, end", "°C"),
                      ("throttled", "Throttle flags (vcgencmd)", "")]:
        L.append(f"| {lab} | {_fmt(metrics[k], u)} |")
    L.append("\n## LLM use and validation\n")
    L.append(f"* Explanation sources (session): `{metrics['explanation_sources']}`")
    L.append(f"* LLM outputs accepted after validation (session): {_fmt(metrics['llm_outputs_accepted_session'])}")
    L.append(f"* Accepted per benchmark run: {_fmt(metrics['llm_outputs_accepted_per_benchmark_run'])}")
    L.append(f"* Raw inference runs ok: {_fmt(metrics['inference_runs_ok'])}  (`python -m level_bridge.main infer --repeat 3`)")
    L.append("\n## Offline operation\n")
    L.append(f"* offline = {_fmt(metrics['offline'])}, backend local = {_fmt(metrics['offline_backend_local'])}"
             + ("" if off else "  → run `bash scripts/test_offline_mode.sh` at the Pi console"))
    L.append("\n## Learning session\n")
    L.append("| Item | Value |\n|---|---|")
    for k, lab in [("placement", "Placement"), ("rung_path", "Path"), ("end_reason", "End"),
                   ("assessment", "Assessment credits"), ("recovery", "Recovery credits (outside maximum)"),
                   ("total_earned", "Total earned"), ("cbm", "CBM")]:
        L.append(f"| {lab} | {_fmt(metrics[k])} |")
    if rep:
        L.append("\n| Concept | State | Flags |\n|---|---|---|")
        for c in rep["concepts"]:
            L.append(f"| {c['cid']} {c['label']} | {c['state'] if c['assessed'] else 'not assessed'} | "
                     f"{'; '.join(c['flags']) or '–'} |")
    L.append(f"\n## Automated tests\n\n`{metrics['tests']}`\n")
    L.append("## Evidence files in this folder\n")
    for f in sorted(p.name for p in d.iterdir() if p.is_file()):
        L.append(f"* `{f}`")
    missing = [k for k, v in metrics.items() if v is None]
    if missing:
        L.append("\n## Not yet measured\n\n" + ", ".join(f"`{m}`" for m in missing))
    (d / "REPORT_SUMMARY.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"\nREPORT SUMMARY  ({d})")
    print(f"  backend {backend} · LLM inference {'yes' if is_llm else 'NO (templates)'}"
          f" · LLM outputs accepted {_fmt(metrics['llm_outputs_accepted_session'])}")
    for k in ("cold_start_s", "model_load_s", "t_build_median_s", "ttft_first_call_median_ms",
              "tokens_per_s_median", "cpu_system_pct_median", "peak_rss_mb", "cpu_temp_end_c", "throttled"):
        print(f"  {k:<28} {_fmt(metrics[k])}")
    print(f"  scores: {metrics['assessment']} · +{metrics['recovery']} · {metrics['total_earned']} · CBM {metrics['cbm']}")
    print(f"  written: {d / 'REPORT_SUMMARY.md'}, {d / 'report_metrics.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
