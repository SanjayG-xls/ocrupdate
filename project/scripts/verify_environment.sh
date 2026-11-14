#!/usr/bin/env bash
# Sequence A - version report + config/test sanity. Writes outputs/environment_report.json.
set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
echo "== OS / hardware"
uname -a
[[ -r /proc/device-tree/model ]] && { tr -d '\0' < /proc/device-tree/model; echo; }
grep -E "MemTotal" /proc/meminfo || true
command -v vcgencmd >/dev/null && vcgencmd get_throttled || echo "vcgencmd not available (not a Pi or not installed)"
echo "== Python packages (writes outputs/environment_report.json)"
python -m level_bridge.main check-env
code=$?
echo "== Environment tests"
python -m pytest -q tests/unit/test_a_environment.py || code=1
[[ $code -eq 0 ]] && echo "ENVIRONMENT OK" || echo "ENVIRONMENT PROBLEMS - see docs/TROUBLESHOOTING.md"
exit $code
