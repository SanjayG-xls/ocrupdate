#!/usr/bin/env python3
"""Sequence B - REAL model loading and inference. Run on the Raspberry Pi 5 with the .pte present.

    python scripts/test_model_inference.py            # check-model + 1 inference + 3 repeats + hardware tests

Exits non-zero and prints the exact error if ExecuTorch or the model is unavailable.
It never substitutes another model or the template backend.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-m", "level_bridge.main"]
env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "LB_HARDWARE": "1"}

steps = [
    ("B1 model files + load", PY + ["check-model"]),
    ("B2 single inference", PY + ["infer", "--prompt", "In one sentence, what is speed?", "--max-new-tokens", "48"]),
    ("B3 repeated inference x3", PY + ["infer", "--prompt", "Name the unit of speed.", "--repeat", "3",
                                       "--max-new-tokens", "24"]),
    ("B4 hardware pytest", [sys.executable, "-m", "pytest", "-v", "tests/hardware"]),
]
failed = 0
for name, cmd in steps:
    print(f"\n== {name}: {' '.join(cmd[1:])}", flush=True)
    code = subprocess.call(cmd, cwd=ROOT, env=env)
    print(f"== {name}: {'PASS' if code == 0 else 'FAIL'} (exit {code})")
    if code:
        failed += 1
        if name.startswith("B1"):
            print("Model could not be loaded - see the error above and docs/TROUBLESHOOTING.md. Stopping.")
            break
sys.exit(1 if failed else 0)
