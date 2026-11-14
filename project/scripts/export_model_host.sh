#!/usr/bin/env bash
# Export Qwen2.5-0.5B-Instruct to an ExecuTorch .pte (XNNPACK, 8da4w) on an x86-64 Linux HOST.
# Not run on the Pi. Takes the ExecuTorch repo at tag v1.4.0 (same version as the Pi runtime).
#
# File paths and config fields were checked against the v1.4.0 tag (examples/models/qwen2_5/,
# extension/llm/export/config/llm_config.py). The export itself has NOT been run by us yet.
set -euo pipefail
WORK="${WORK:-$HOME/lb_export}"
OUT_NAME="qwen2_5_0_5b_instruct_8da4w.pte"
mkdir -p "$WORK" && cd "$WORK"

# 1) ExecuTorch source at the pinned tag + its Python environment
if [[ ! -d executorch ]]; then
  git clone --branch v1.4.0 --depth 1 https://github.com/pytorch/executorch.git
fi
cd executorch
python3 -m venv .venv && source .venv/bin/activate
./install_executorch.sh           # installs executorch 1.4.0 + matching torch/torchao into this venv
pip install "huggingface_hub[cli]"

# 2) Hugging Face checkpoint (Instruct variant) - weights + tokenizer.json
huggingface-cli download Qwen/Qwen2.5-0.5B-Instruct --local-dir "$WORK/hf_qwen2_5_0_5b_instruct"

# 3) Convert HF weights to the ExecuTorch Llama-style checkpoint
python examples/models/qwen2_5/convert_weights.py "$WORK/hf_qwen2_5_0_5b_instruct" "$WORK/qwen2_5_0_5b_instruct.pth"

# 4) Export: XNNPACK, 8-bit dynamic activations / 4-bit weights, KV cache, 1024 context
# Run from the repo root (as in examples/models/qwen2_5/README.md at v1.4.0).
# +base.checkpoint is REQUIRED: without it the exporter fetches the BASE model Qwen/Qwen2.5-0.5B
# (HUGGING_FACE_REPO_IDS in examples/models/llama/export_llama_lib.py), not the Instruct model.
python -m extension.llm.export.export_llm \
  --config examples/models/qwen2_5/config/qwen2_5_xnnpack_q8da4w.yaml \
  +base.model_class="qwen2_5_0_5b" \
  +base.checkpoint="$WORK/qwen2_5_0_5b_instruct.pth" \
  +base.params="examples/models/qwen2_5/config/0_5b_config.json" \
  +export.max_seq_length=1024 \
  +export.max_context_length=1024 \
  +export.output_name="$WORK/$OUT_NAME" \
  ++base.metadata='"{\"get_bos_id\":151643, \"get_eos_ids\":[151645, 151643]}"'
# Quoting copied from examples/models/llama/README.md (v1.4.0): the outer '"..."' keeps the value a
# JSON *string* for Hydra instead of parsing it as a dict.
# Hydra: '+key' adds a key the yaml does not set; '++key' overrides one it does. The v1.4.0 yaml
# already sets base.metadata with EOS [151643] only, so we override it ('++') to add 151645
# (<|im_end|>), which ends Instruct/ChatML replies. The yaml sets use_kv_cache, use_sdpa_with_kv_cache,
# xnnpack and qmode 8da4w (verified in examples/models/qwen2_5/config/qwen2_5_xnnpack_q8da4w.yaml).

cp "$WORK/hf_qwen2_5_0_5b_instruct/tokenizer.json" "$WORK/tokenizer.json"
sha256sum "$WORK/$OUT_NAME" "$WORK/tokenizer.json"
ls -lh "$WORK/$OUT_NAME"
echo "Copy to the Pi:  scp $WORK/$OUT_NAME $WORK/tokenizer.json pi@<pi-host>:~/level_bridge_stem/models/"
