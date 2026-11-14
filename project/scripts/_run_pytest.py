"""Helper for the scripts/test_*.py wrappers: run selected pytest files and print a verdict."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(sequence: str, targets: list[str], extra: list[str] | None = None) -> int:
    print(f"== Sequence {sequence}: pytest {' '.join(targets)}")
    cmd = [sys.executable, "-m", "pytest", "-v", *targets, *(extra or []), *sys.argv[1:]]
    code = subprocess.call(cmd, cwd=ROOT)
    print(f"== Sequence {sequence}: {'PASS' if code == 0 else 'FAIL'} (exit {code})")
    return code
