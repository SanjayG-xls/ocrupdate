#!/usr/bin/env python3
"""Sequence A wrapper. Runs on laptop or Pi; no model needed. Usage: python scripts/test_environment.py [-k expr]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _run_pytest import run  # noqa: E402

sys.exit(run("A", ["tests/unit/test_a_environment.py"]))
