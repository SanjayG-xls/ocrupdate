#!/usr/bin/env python3
"""Sequence K wrapper. Runs on laptop or Pi; no model needed. Usage: python scripts/test_scoring_cbm.py [-k expr]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _run_pytest import run  # noqa: E402

sys.exit(run("K", ["tests/unit/test_k_scoring_cbm.py"]))
