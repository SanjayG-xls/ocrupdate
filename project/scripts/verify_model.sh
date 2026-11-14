#!/usr/bin/env bash
# Sequence B - verify the exported model artifact on the Pi (size, sha256, load test).
#   bash scripts/verify_model.sh                  # check against recorded checksum
#   bash scripts/verify_model.sh --write-checksum # record the current .pte sha256 in config/model_config.yaml
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
PTE=$(python - <<'PY'
import yaml; c = yaml.safe_load(open("config/model_config.yaml")); print(c["executorch_runner"]["pte_path"])
PY
)
TOK=$(python - <<'PY'
import yaml; c = yaml.safe_load(open("config/model_config.yaml")); print(c["executorch_runner"]["tokenizer_path"])
PY
)
for f in "$PTE" "$TOK"; do
  if [[ ! -f "$f" ]]; then echo "MISSING: $f  (see models/README.md)"; exit 3; fi
  echo "$f  $(du -h "$f" | cut -f1)"
done
SUM=$(sha256sum "$PTE" | cut -d' ' -f1)
echo "sha256($PTE) = $SUM"
if [[ "${1:-}" == "--write-checksum" ]]; then
  python - "$SUM" <<'PY'
import re, sys
p = "config/model_config.yaml"; s = open(p).read()
s = re.sub(r"sha256: .*", f"sha256: \"{sys.argv[1]}\"", s, count=1)
open(p, "w").write(s); print("recorded in", p)
PY
fi
python -m level_bridge.main check-model
