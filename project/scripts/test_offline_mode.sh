#!/usr/bin/env bash
# Sequence O - prove the full session runs with networking disabled (run ON THE PI, at the console).
#
#  !! WARNING: `nmcli networking off` drops Wi-Fi AND Ethernet. If you are connected over SSH you
#  !! will lose the session. Run this from a keyboard/monitor on the Pi, or with a local serial
#  !! console. The script re-enables networking at the end (or run `sudo nmcli networking on`).
set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
if [[ -n "${SSH_CONNECTION:-}" && "${FORCE:-0}" != "1" ]]; then
  echo "Refusing to disable networking over SSH ($SSH_CONNECTION). Run at the Pi console, or FORCE=1 at your own risk."
  exit 2
fi
command -v nmcli >/dev/null || { echo "nmcli not found (NetworkManager required: Raspberry Pi OS Bookworm)"; exit 2; }
RUN_ID="offline_$(date +%Y%m%d_%H%M%S)"
echo "== disabling networking"; sudo nmcli networking off; sleep 3
python -m level_bridge.main offline-check --require-offline | tee "outputs/${RUN_ID}_check.txt"
OFF=${PIPESTATUS[0]}
code=0
if [[ $OFF -eq 0 ]]; then
  echo "== full scripted session with the real model, network OFF"
  python -m level_bridge.main demo --answers data/test_cases/priya_answers.json --run-id "$RUN_ID" || code=$?
else
  echo "Network still reachable - offline test NOT valid."; code=2
fi
echo "== re-enabling networking"; sudo nmcli networking on
[[ $code -eq 0 ]] && echo "OFFLINE TEST PASS (evidence: outputs/${RUN_ID}_check.txt, outputs/learning_report_${RUN_ID}.json)" \
                  || echo "OFFLINE TEST FAIL (exit $code)"
exit $code
