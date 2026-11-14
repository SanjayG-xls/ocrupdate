#!/usr/bin/env bash
# Sequence Q (no model) - full automated suite on laptop or Pi. Hardware tests are skipped
# unless LB_HARDWARE=1. Writes outputs/test_summary.txt and outputs/junit.xml.
set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p outputs logs
python -m pytest -v --junitxml=outputs/junit.xml 2>&1 | tee outputs/test_summary.txt
code=${PIPESTATUS[0]}
echo "== no-model end-to-end (template backend - NOT LLM inference)"
python -m level_bridge.main demo --backend template --answers data/test_cases/priya_answers.json \
       --run-id no_model_check > outputs/no_model_check.txt 2>&1 || code=1
tail -3 outputs/no_model_check.txt
[[ $code -eq 0 ]] && echo "ALL NO-MODEL TESTS PASS" || echo "FAILURES - see outputs/test_summary.txt"
exit $code
