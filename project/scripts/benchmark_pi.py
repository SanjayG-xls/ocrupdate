#!/usr/bin/env python3
"""Sequence P - benchmark on the Raspberry Pi 5 (warm-up + 5 measured runs, median, CSV + JSON).

    python scripts/benchmark_pi.py                       # configured backend (executorch_runner)
    python scripts/benchmark_pi.py --backend template    # NON-LLM pipeline timing only (labelled)

Cold start is measured from Python process start to model loaded. Run with the Pi idle,
on mains power with active cooling, and record ambient conditions in the README table.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
run_id = time.strftime("pi_%Y%m%d_%H%M%S")
cmd = [sys.executable, "-m", "level_bridge.main", "benchmark", "--run-id", run_id, *sys.argv[1:]]
sys.exit(subprocess.call(cmd, cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src")}))
