"""Benchmark harness (report §5.2). Records only what was actually measured.

Protocol: cold start (process start -> model loaded), then ``warmup`` build runs that
are discarded, then ``measured`` build runs; we report the median of the measured runs.
Generation metrics (TTFT, tokens, tokens/s) come from the runtime's own stats and are
``null`` when the backend is not an LLM. Nothing is estimated or filled in.
"""

from __future__ import annotations

import csv
import json
import os
import platform
import shutil
import statistics
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

from .config import AppConfig
from .model_runtime import ModelRuntime, peak_rss_mb
from .pipeline import build


def _read(path: str) -> Optional[str]:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def cpu_temp_c() -> Optional[float]:
    t = _read("/sys/class/thermal/thermal_zone0/temp")
    return round(int(t) / 1000.0, 1) if t and t.lstrip("-").isdigit() else None


def throttled() -> Optional[str]:
    """Raspberry Pi firmware throttle flags (``vcgencmd get_throttled``); None if unavailable."""
    if not shutil.which("vcgencmd"):
        return None
    try:
        return subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:  # pragma: no cover
        return None


def _proc_stat() -> Optional[tuple]:
    """(busy, total) jiffies over all CPUs from /proc/stat (Linux)."""
    s = _read("/proc/stat")
    if not s or not s.startswith("cpu "):
        return None
    v = [int(x) for x in s.splitlines()[0].split()[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)          # idle + iowait
    return sum(v) - idle, sum(v)


class CpuMeter:
    """CPU utilisation over an interval: system-wide % (all cores = 100 %) and this
    process's CPU time / wall time (can exceed 100 % when several cores are used)."""

    MIN_INTERVAL_S = 0.5

    def __enter__(self):
        self._sys0, self._p0, self._w0 = _proc_stat(), os.times(), time.perf_counter()
        return self

    def __exit__(self, *exc) -> bool:
        sys1, p1, wall = _proc_stat(), os.times(), time.perf_counter() - self._w0
        self.system_pct = self.process_pct = None
        if wall < self.MIN_INTERVAL_S:      # /proc/stat and os.times tick at ~10 ms: too coarse below this
            return False
        if self._sys0 and sys1 and sys1[1] > self._sys0[1]:
            self.system_pct = round(100.0 * (sys1[0] - self._sys0[0]) / (sys1[1] - self._sys0[1]), 1)
        cpu_s = (p1.user - self._p0.user) + (p1.system - self._p0.system)
        self.process_pct = round(100.0 * cpu_s / wall, 1)
        return False


def device_info() -> Dict[str, object]:
    model = _read("/proc/device-tree/model")
    mem_kb = None
    meminfo = _read("/proc/meminfo")
    if meminfo:
        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                mem_kb = int(line.split()[1])
    return {"device_model": model.replace("\x00", "") if model else None, "machine": platform.machine(),
            "python": platform.python_version(), "cpu_count": os.cpu_count(),
            "mem_total_mb": round(mem_kb / 1024, 1) if mem_kb else None, "kernel": platform.release()}


def _median(vals: List[Optional[float]]) -> Optional[float]:
    v = [x for x in vals if x is not None]
    return round(statistics.median(v), 4) if v else None


def run_benchmark(cfg: AppConfig, passage: Path, runtime: ModelRuntime, warmup: int, measured: int,
                  process_start: float, out_dir: Path, run_id: str) -> Dict[str, object]:
    t_load0 = time.perf_counter()
    load_s = runtime.load()
    cold_start_s = time.perf_counter() - process_start
    runs: List[Dict[str, object]] = []
    for i in range(warmup + measured):
        temp_before = cpu_temp_c()
        with CpuMeter() as cpu:
            art = build(cfg, passage, runtime)
        calls = art.generation_calls
        ttfts = [c.get("ttft_ms") for c in calls if c.get("ok")]
        gen_tokens = sum(int(c.get("generated_tokens") or 0) for c in calls if c.get("ok"))
        gen_time = sum(float(c.get("wall_time_s") or 0) for c in calls if c.get("ok"))
        runs.append({
            "run": i, "phase": "warmup" if i < warmup else "measured", **art.timings,
            "llm_calls": len(calls), "llm_calls_ok": sum(1 for c in calls if c.get("ok")),
            "llm_outputs_accepted": art.llm_outputs_accepted,
            "ttft_ms_first_call": ttfts[0] if ttfts else None,
            "generated_tokens": gen_tokens if runtime.is_llm else None,
            "tokens_per_s": round(gen_tokens / gen_time, 2) if runtime.is_llm and gen_time > 0 and gen_tokens else None,
            "explanation_sources": {k: v.source for k, v in art.explanations.items()},
            "cpu_system_pct": cpu.system_pct, "cpu_process_pct": cpu.process_pct,
            "cpu_temp_before_c": temp_before, "cpu_temp_after_c": cpu_temp_c(), "peak_rss_mb": round(peak_rss_mb(), 1),
        })
    m = [r for r in runs if r["phase"] == "measured"]
    model_file = None
    desc = runtime.describe()
    if desc.get("pte_path") and Path(str(desc["pte_path"])).exists():
        model_file = round(Path(str(desc["pte_path"])).stat().st_size / 1e6, 1)
    summary = {
        "run_id": run_id, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "backend": desc,
        "is_llm_inference": runtime.is_llm,
        "label": "LLM inference measurements" if runtime.is_llm else
                 "NON-LLM pipeline timing (template backend) - not model inference",
        "device": device_info(), "warmup_runs": warmup, "measured_runs": measured,
        "cold_start_s": round(cold_start_s, 3), "model_load_s": round(load_s, 3),
        "median": {k: _median([r[k] for r in m]) for k in
                   ("t_build_s", "t_preprocessing_s", "t_model_generation_s", "t_validation_and_templates_s",
                    "cpu_system_pct", "cpu_process_pct",
                    "ttft_ms_first_call", "generated_tokens", "tokens_per_s")},
        "peak_rss_mb": round(peak_rss_mb(), 1), "model_file_mb": model_file,
        "cpu_temp_end_c": cpu_temp_c(), "throttled": throttled(), "runs": runs,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"benchmark_{run_id}.json").write_text(json.dumps(summary, indent=2, default=str))
    with open(out_dir / f"benchmark_{run_id}.csv", "w", newline="") as f:
        cols = [k for k in runs[0] if k != "explanation_sources"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(runs)
    return summary


def repair_latency_stats(latencies: List[float]) -> Dict[str, Optional[float]]:
    if not latencies:
        return {"n": 0, "median_ms": None, "max_ms": None}
    return {"n": len(latencies), "median_ms": round(statistics.median(latencies) * 1000, 3),
            "max_ms": round(max(latencies) * 1000, 3)}
