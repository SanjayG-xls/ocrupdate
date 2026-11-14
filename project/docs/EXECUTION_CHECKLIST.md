# Execution checklist

Tick each line only with the evidence file in hand. Evidence goes into `outputs/`.

## Laptop (any Linux, no model) – already passing in development

- [ ] `bash scripts/install_dependencies.sh` → exit 0
- [ ] `bash scripts/verify_environment.sh` → `ENVIRONMENT OK`
- [ ] `bash scripts/run_all_tests.sh` → `ALL NO-MODEL TESTS PASS` (119 passed, 10 skipped: hardware + real-runtime tests) · `outputs/test_summary.txt`
- [ ] `python -m level_bridge.main demo --backend template --answers data/test_cases/priya_answers.json` → 25 / 36 · +3 · 28 · CBM +6 / 18
- [ ] optional real-runtime contract: `pip install -r requirements-pi.txt && bash scripts/export_tiny_test_model.sh && LB_ET_TEST_DIR=models/test python -m pytest tests/integration/test_executorch_runtime.py -v` → 6 passed

## Host export (x86-64 Linux)

- [ ] `bash scripts/export_model_host.sh` → `.pte` + `tokenizer.json`; record size and sha256 ______
- [ ] ExecuTorch version used for export = **1.4.0**

## Raspberry Pi 5 (64-bit Raspberry Pi OS)

- [ ] `uname -m` = `aarch64`; Python 3.10–3.13 · RAM ____ GB · cooler fitted · 27 W supply
- [ ] `bash scripts/install_dependencies.sh --pi` → `outputs/pip_freeze.txt` saved
- [ ] `bash scripts/verify_environment.sh` → `executorch: 1.4.0…`, `executorch_llm_runner_importable: true`
- [ ] copy model; `bash scripts/verify_model.sh --write-checksum` → `outputs/model_check.json` `load.ok: true` (sha256 matches host)
- [ ] `python scripts/test_model_inference.py` → B1–B4 PASS · `outputs/inference_*.json`
- [ ] `python -m level_bridge.main build` → note sources per explanation: summary ____ L1 ____ L2 ____ · LLM outputs accepted ____
- [ ] `bash scripts/run_all_tests.sh` on the Pi → all pass
- [ ] `LB_HARDWARE=1 python -m pytest tests/hardware -v` → 4 passed
- [ ] At the console: `bash scripts/test_offline_mode.sh` → `OFFLINE TEST PASS`
- [ ] `python scripts/benchmark_pi.py` → `outputs/benchmark_pi_*.json/.csv`; throttled = ______
- [ ] `bash scripts/run_end_to_end.sh` → `outputs/e2e_<time>/` complete (keep as demo fallback)
- [ ] open `outputs/e2e_<time>/REPORT_SUMMARY.md` → copy its tables into the report; every value comes from a file in that folder

## Fill in the report/README only from evidence

| Metric | Value | Evidence file |
|---|---|---|
| Model file size | | model_check.json |
| Model load (s) | | benchmark json `model_load_s` |
| Cold start (s) | | `cold_start_s` |
| T_build median (s) | | `median.t_build_s` |
| Model generation median (s) | | `median.t_model_generation_s` |
| TTFT first call median (ms) | | `median.ttft_ms_first_call` |
| Tokens/s median | | `median.tokens_per_s` |
| Repair latency median (ms) | | learning_report `run.timings.repair_latency` |
| Peak RSS (MB) | | `peak_rss_mb` |
| CPU utilisation system / process (%) | | `median.cpu_system_pct`, `median.cpu_process_pct` |
| CPU temp end (°C) / throttled | | `cpu_temp_end_c`, `throttled` |
| LLM outputs accepted (of 3 + stems) | | `runs[].llm_outputs_accepted` |

## Demo readiness

- [ ] rehearsal timed at 5–7 min with `docs/DEMO_SCRIPT.md`
- [ ] fallback folder `outputs/e2e_<time>/` present on the Pi and on a laptop
- [ ] `sudo nmcli networking on` restores the network


## Live round (14 Nov 2026) – Raspberry Pi 5 and Teach · Learn · Improve

- [ ] Baseline first: `verify_environment.sh` → `check-model` → `run_end_to_end.sh` on the Pi 5; label results "Raspberry Pi 5"
- [ ] `bash scripts/run_product_demo.sh` (LLM pack build) – note pack-build T_build and which explanations came from the LLM
- [ ] Organiser passage: `process` first; fix extraction gaps before any feature work (docs/PRODUCT_DEMO.md §3)
- [ ] `pack-review` interactively once, including a refused edit
- [ ] `test_offline_mode.sh` at the Pi console (not over SSH) with the product demo
- [ ] Open `outputs/cbs_portal.html` in the Pi browser with networking off
- [ ] Freeze code 60–90 min before judging; rehearse twice
