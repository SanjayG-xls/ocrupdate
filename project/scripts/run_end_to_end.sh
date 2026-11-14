#!/usr/bin/env bash
# Sequence Q - MASTER command (run on the Raspberry Pi 5 with the model installed).
#   bash scripts/run_end_to_end.sh                 # real model, scripted Priya learner
#   bash scripts/run_end_to_end.sh --interactive   # real model, live learner at the keyboard
#   BACKEND=template bash scripts/run_end_to_end.sh   # no model (labelled NON-LLM everywhere)
# Produces: terminal transcript, learning report JSON, knowledge map JSON, benchmark JSON/CSV,
# test summary, structured logs (logs/*.jsonl), an error log (outputs/<run>/errors.log) and
# REPORT_SUMMARY.md + report_metrics.json (every metric filled in from the evidence files).
set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
RUN_ID="e2e_$(date +%Y%m%d_%H%M%S)"
DIR="outputs/$RUN_ID"; mkdir -p "$DIR" logs
B=(); [[ -n "${BACKEND:-}" ]] && B=(--backend "$BACKEND")
ERR="$DIR/errors.log"; : > "$ERR"
step() { echo; echo "==== $1"; }
fail=0

step "1/6 environment";   python -m level_bridge.main check-env > "$DIR/environment.txt" 2>>"$ERR" || fail=1
step "2/6 model check";   if [[ "${BACKEND:-}" != "template" ]]; then
                            python -m level_bridge.main check-model "${B[@]}" > "$DIR/model_check.txt" 2>>"$ERR" \
                              || { echo "MODEL NOT AVAILABLE - see $DIR/model_check.txt"; cat "$DIR/model_check.txt"; exit 3; }
                            python -m level_bridge.main infer "${B[@]}" --repeat 3 --max-new-tokens 48 \
                              > "$DIR/inference.txt" 2>>"$ERR" || fail=1
                            grep -E "^--- run" "$DIR/inference.txt"
                          fi
step "3/6 automated tests (no model)"
python -m pytest -q --junitxml="$DIR/junit.xml" > "$DIR/test_summary.txt" 2>>"$ERR" || fail=1
tail -1 "$DIR/test_summary.txt"
step "4/6 learning session"
if [[ "${1:-}" == "--interactive" ]]; then
  python -m level_bridge.main demo "${B[@]}" --run-id "$RUN_ID" 2>>"$ERR" | tee "$DIR/terminal.txt" || fail=1
else
  python -m level_bridge.main demo "${B[@]}" --answers data/test_cases/priya_answers.json --run-id "$RUN_ID" \
    2>>"$ERR" | tee "$DIR/terminal.txt" || fail=1
fi
step "5/6 benchmark (warm-up + measured runs)"
python -m level_bridge.main benchmark "${B[@]}" --run-id "$RUN_ID" > "$DIR/benchmark.txt" 2>>"$ERR" || fail=1
grep -E '"label"|t_build_s|ttft|tokens_per_s|peak_rss|cold_start|model_load' "$DIR/benchmark.txt" | head -12
step "6/6 collect artifacts"
for f in learning_report knowledge_map session_events session_transcript benchmark; do
  mv outputs/${f}_"$RUN_ID".* "$DIR/" 2>/dev/null || true
done
cp logs/*"$RUN_ID"*.jsonl "$DIR/" 2>/dev/null || true
for f in environment_report model_check offline_check; do cp "outputs/$f.json" "$DIR/" 2>/dev/null || true; done
cp outputs/inference_*.json outputs/pip_freeze.txt "$DIR/" 2>/dev/null || true
cp outputs/offline_*_check.txt "$DIR/" 2>/dev/null || true
step "report summary"
python scripts/capture_for_report.py "$DIR" 2>>"$ERR" || fail=1
ls -1 "$DIR"
[[ -s "$ERR" ]] && echo "stderr captured in $ERR"
[[ $fail -eq 0 ]] && echo "END-TO-END COMPLETE: $DIR" || echo "END-TO-END FINISHED WITH ERRORS: $DIR"
exit $fail
