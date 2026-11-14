#!/usr/bin/env bash
# Sequence A - install pinned dependencies into a virtual environment.
#   Laptop (engine + tests, no model):   bash scripts/install_dependencies.sh
#   Raspberry Pi 5 (adds ExecuTorch):    bash scripts/install_dependencies.sh --pi
set -euo pipefail
cd "$(dirname "$0")/.."
PI=0; [[ "${1:-}" == "--pi" ]] && PI=1
PYTHON="${PYTHON:-python3}"
"$PYTHON" - <<'PY'
import sys
v = sys.version_info
assert (3, 10) <= v[:2] <= (3, 13), f"Python {v.major}.{v.minor} unsupported: need 3.10-3.13 (ExecuTorch 1.4.0 wheels)"
print(f"Python {v.major}.{v.minor}.{v.micro} OK")
PY
if [[ ! -d .venv ]]; then "$PYTHON" -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
if [[ $PI -eq 1 ]]; then
  [[ "$(uname -m)" == "aarch64" ]] || echo "WARNING: --pi on $(uname -m); the Pi target is aarch64 (64-bit OS)."
  # torch>=2.13 is pulled by executorch==1.4.0. If pip cannot resolve it from PyPI on aarch64, rerun with:
  #   PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu bash scripts/install_dependencies.sh --pi
  python -m pip install -r requirements-pi.txt
else
  python -m pip install -r requirements.txt
fi
python -m pip install -e . --no-deps
mkdir -p outputs logs
python -m pip freeze > outputs/pip_freeze.txt
echo "Installed. Exact resolved versions: outputs/pip_freeze.txt"
echo "Next: source .venv/bin/activate && bash scripts/verify_environment.sh"
