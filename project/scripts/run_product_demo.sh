#!/usr/bin/env bash
# Teach · Learn · Improve demo (report Section 7) - one Pi plays both the teacher hub and the student device.
#   bash scripts/run_product_demo.sh                  # pack build uses the configured backend (LLM on the Pi)
#   bash scripts/run_product_demo.sh --backend template   # laptop / no model (labelled, not inference)
#   USB=/media/$USER/USBSTICK bash scripts/run_product_demo.sh   # export bundles to a real USB drive
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
BACKEND_ARGS=()
if [[ "${1:-}" == "--backend" ]]; then BACKEND_ARGS=(--backend "$2"); fi
USB="${USB:-usb_export}"
M="python -m level_bridge.main"
echo "== reset demo stores (data/learners, data/hub, data/packs, $USB/*.lbprofile.json)"
rm -rf data/learners data/hub data/packs; mkdir -p "$USB"; rm -f "$USB"/*.lbprofile.json
echo; echo "== 1 TEACH: build lesson packs once on the hub"
$M pack-build "${BACKEND_ARGS[@]}" --allow-template-fallback --passage data/passages/speed_passage.txt --out data/packs/speed.lbpack.json
$M pack-build "${BACKEND_ARGS[@]}" --allow-template-fallback --passage data/passages/density_passage.txt --out data/packs/density.lbpack.json
echo; echo "== 1 TEACH: teacher review (scripted approve here; run 'pack-review --pack <file>' for the interactive review)"
$M pack-review --pack data/packs/speed.lbpack.json --approve-all
$M pack-review --pack data/packs/density.lbpack.json --approve-all
echo; echo "== 2 LEARN: model-free sessions from the packs (pseudonymous IDs only)"
$M session --pack data/packs/speed.lbpack.json   --answers data/test_cases/priya_answers.json         --learner STU-7F3A --consent --run-id demo_priya_speed
$M session --pack data/packs/density.lbpack.json --answers data/test_cases/priya_density_answers.json --learner STU-7F3A --run-id demo_priya_density | tail -8
$M session --pack data/packs/speed.lbpack.json   --answers data/test_cases/strong_reader_answers.json --learner STU-K2M9 --consent --run-id demo_ravi_speed   | tail -3
$M session --pack data/packs/density.lbpack.json --answers data/test_cases/ravi_density_answers.json  --learner STU-K2M9 --run-id demo_ravi_density | tail -3
$M session --pack data/packs/speed.lbpack.json   --answers data/test_cases/meena_speed_answers.json  --learner STU-M4Q8 --consent --run-id demo_meena_speed  | tail -3
echo; echo "== 3 IMPROVE: learner memory, USB export, hub import, CBS portal"
$M profile-show --learner STU-7F3A
for L in STU-7F3A STU-K2M9 STU-M4Q8; do $M profile-export --learner "$L" --out "$USB"; done
$M hub-import --dir "$USB"
$M portal
echo; echo "Open outputs/cbs_portal.html in the Pi's browser (no network needed)."
