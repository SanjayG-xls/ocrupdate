# Troubleshooting

Always look first at `logs/<command>_<run>.jsonl` (structured log) and, for crashes,
`logs/error_<run>.log` (full traceback). Exit codes: 0 ok · 2 config/input · 3 model unavailable · 4 unexpected error.

## 1. Installation

| Symptom | Cause | Fix |
|---|---|---|
| `Python 3.x unsupported` | ExecuTorch 1.4.0 wheels are cp310–cp313 | Raspberry Pi OS Bookworm ships 3.11 – use the system `python3` |
| `No matching distribution found for executorch==1.4.0` on the Pi | 32-bit OS (armv7l) | install **64-bit** Raspberry Pi OS (`uname -m` must print `aarch64`) |
| pip cannot resolve `torch>=2.13` | index has no matching aarch64 build | `PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu bash scripts/install_dependencies.sh --pi` |
| `ModuleNotFoundError: transformers` when the runner is imported | the runner imports `transformers` but the wheel does not declare it | `pip install -r requirements-pi.txt` (it includes `transformers`) |
| install killed / very slow | low RAM / SD card | use a 64-bit OS on SSD/USB if possible; add swap: `sudo dphys-swapfile swapoff; sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile; sudo dphys-swapfile setup; sudo dphys-swapfile swapon` |

## 2. Model

| Symptom | Cause | Fix |
|---|---|---|
| export: Hydra `Could not append to config. An item is already at '…'` | that key is already in the yaml | change `+key=` to `++key=` for that key in `scripts/export_model_host.sh` |
| export downloads `Qwen/Qwen2.5-0.5B` | `+base.checkpoint` missing | pass the converted **Instruct** `.pth` |
| `Missing operator: [..] llama::custom_sdpa.out` / `Failed to load method 'forward'` | custom ops not registered before loading | the adapter imports `executorch.extension.llm.custom_ops.custom_ops` automatically; check `registered_op_libs` in `outputs/model_check.json` |
| every call `RuntimeError: Generation failed` | prompt longer than the exported `max_seq_length` (seen with a 256-token export) | export with `max_seq_length=1024` |
| `Model file not found: models/…pte` | not exported / not copied | `bash scripts/export_model_host.sh` on the host, `scp` to `models/` |
| `TextLLMRunner could not load the model: …` | `.pte` exported with a different ExecuTorch version, wrong backend, or corrupt copy | compare `sha256sum` with the host; re-export with ExecuTorch **1.4.0**. Do not switch to another model to make it work – report the exact error |
| `Tokenizer file not found` | tokenizer.json missing | copy `tokenizer.json` from the HF Instruct checkpoint |
| output is gibberish or never stops | base (non-Instruct) checkpoint, missing EOS metadata, or wrong prompt template | export the **Instruct** model with the `get_eos_ids` metadata; keep `prompt_format: qwen_chat` |
| `timeout after 180 s` | slow generation, thermal throttling | check `vcgencmd get_throttled` (0x0 = ok), add cooling, reduce `max_new_tokens` in `config/config.yaml` |
| context errors | prompt + `max_new_tokens` > exported `max_seq_length` (1024) | shorten passage or `max_new_tokens`, or re-export with a larger context |
| every explanation `source: template` with the real model | model outputs failed validation twice | read the `attempts[].validation` entries in `outputs/stage4_explanations.json` – they name the failed check. This is the intended safe behaviour, and it is reported as template, never as LLM |

## 3. Running

| Symptom | Fix |
|---|---|
| `Could not find config/config.yaml` | run from the project root or `export LB_ROOT=/path/to/level_bridge_stem` |
| `ModuleNotFoundError: level_bridge` | `pip install -e .` or `export PYTHONPATH=$PWD/src` |
| `PASSAGE ERROR: … supported range is 50-450` | passage too short/long for the rule-based extractor |
| `script has no answer for delivered item Q3b` | a scripted answers file does not cover the path the learner took – add that item |
| hardware tests show `SKIPPED` | they need `LB_HARDWARE=1` and are only meaningful on the Pi |

## 4. Offline test

* Do **not** run `scripts/test_offline_mode.sh` over SSH – `nmcli networking off` cuts the session. The script refuses when `SSH_CONNECTION` is set.
* If you lose access, at the Pi console: `sudo nmcli networking on`.
* `nmcli not found`: Bookworm uses NetworkManager; on older images use `sudo rfkill block wifi` and unplug Ethernet, then `python -m level_bridge.main offline-check --require-offline`.

## 5. Benchmark

* Close other programs; run on the official 27 W supply with active cooler; let the Pi idle 5 min.
* `throttled` other than `throttled=0x0` means results are affected – record it, do not discard silently.
* A benchmark run with `--backend template` is labelled `NON-LLM pipeline timing`; never quote it as model performance.
