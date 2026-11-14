#!/usr/bin/env bash
# Build a tiny RANDOM-WEIGHT Llama-architecture .pte (2 layers, dim 64, KV cache + custom SDPA,
# XNNPACK) for testing the ExecuTorch runtime adapter on any CPU without downloading a model.
# Needs executorch==1.4.0 installed (pip install -r requirements-pi.txt) and git.
# The tokenizer.json is the Llama-3.2-1B-Instruct tokenizer shipped inside the ExecuTorch repo (v1.4.0).
# Output text is noise by design. This is a contract test, NOT the project model.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=models/test; mkdir -p "$OUT"
TMP=$(mktemp -d)
cat > "$TMP/params.json" <<'J'
{"dim": 64, "n_layers": 2, "n_heads": 4, "n_kv_heads": 2, "vocab_size": 128256, "multiple_of": 32,
 "norm_eps": 1e-5, "rope_theta": 500000.0, "use_scaled_rope": true}
J
cat > "$TMP/tiny.yaml" <<'Y'
base:
  metadata='{"get_bos_id":128000, "get_eos_ids":[128009, 128001]}'
model:
  use_kv_cache: True
  use_sdpa_with_kv_cache: True
  dtype_override: fp32
backend:
  xnnpack:
    enabled: True
Y
if [[ ! -f "$OUT/tokenizer.json" ]]; then
  git clone --quiet --depth 1 --branch v1.4.0 --filter=blob:none --sparse https://github.com/pytorch/executorch.git "$TMP/et"
  git -C "$TMP/et" sparse-checkout set examples/mediatek/models/llm_models/weights/Llama-3.2-1B-Instruct
  cp "$TMP/et/examples/mediatek/models/llm_models/weights/Llama-3.2-1B-Instruct/tokenizer.json" "$OUT/tokenizer.json"
fi
python -m executorch.extension.llm.export.export_llm --config "$TMP/tiny.yaml" \
  +base.model_class=llama3 +base.params="$TMP/params.json" \
  +export.max_seq_length=1024 +export.max_context_length=1024 \
  +export.output_name="$PWD/$OUT/tiny_random_llama.pte" > "$OUT/export.log" 2>&1
ls -lh "$OUT"/tiny_random_llama.pte "$OUT"/tokenizer.json
echo "Run: LB_ET_TEST_DIR=$OUT python -m pytest tests/integration/test_executorch_runtime.py -v"
