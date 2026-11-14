#!/usr/bin/env bash
# Fresh install on a Raspberry Pi 5 (64-bit Raspberry Pi OS, Python 3.10-3.13). Needs internet (~700 MB).
#   bash scripts/install_pi_fresh.sh
# Then copy the model files into models/ (see the end of this script's output).
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== 1/6 system check"
uname -m | grep -q aarch64 || { echo "Not a 64-bit Arm OS ($(uname -m)). Use 64-bit Raspberry Pi OS."; exit 1; }
python3 - <<'PY'
import sys
v = sys.version_info
assert (3, 10) <= v[:2] <= (3, 13), f"Python {v.major}.{v.minor}: ExecuTorch 1.4.0 needs 3.10-3.13"
print(f"Python {v.major}.{v.minor}.{v.micro} OK")
PY
python3 -m venv --help >/dev/null 2>&1 || { echo "Installing python3-venv"; sudo apt-get update && sudo apt-get install -y python3-venv; }
echo "== 2/6 virtual environment"
[[ -d .venv ]] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
echo "== 3/6 runtime dependencies (torch is ~480 MB; this is the slow step)"
if ! python -m pip install -r requirements-pi-runtime.txt; then
  echo "PyPI install failed - retrying with the PyTorch CPU index"
  python -m pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-pi-runtime.txt
fi
echo "== 4/6 ExecuTorch 1.4.0 (without coremltools)"
python -m pip install executorch==1.4.0 --no-deps
python -m pip install -e . --no-deps
mkdir -p outputs logs models
python -m pip freeze > outputs/pip_freeze.txt
echo "== 5/6 import check"
python - <<'PY'
import importlib
for m in ("executorch.extension.llm.custom_ops.custom_ops", "executorch.kernels.quantized",
          "executorch.extension.pybindings.portable_lib", "executorch.extension.llm.runner"):
    importlib.import_module(m)
    print("ok", m)
PY
echo "== 6/6 tests without the model"
python -m pytest -q -p no:cacheprovider | tail -1
cat <<'TXT'

INSTALLED. Next:
  1. Copy the model files into models/ :
       cp /media/$USER/*/qwen*.pte models/qwen2_5_0_5b_instruct_8da4w.pte
       cp /media/$USER/*/tokenizer.json models/
     (or edit pte_path in config/model_config.yaml to match your file name)
  2. source .venv/bin/activate && python -m level_bridge.main check-model
  3. bash scripts/run_end_to_end.sh
If step 5 failed with "No module named coremltools": python -m pip install coremltools==9.0  (slow source build)
TXT
