#!/usr/bin/env python3
"""Sequence L wrapper. Runs on laptop or Pi; no model needed. Usage: python scripts/test_concept_states.py [-k expr]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _run_pytest import run  # noqa: E402

sys.exit(run("L", ["tests/unit/test_l_concept_states.py"]))
