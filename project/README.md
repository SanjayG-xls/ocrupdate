# Level Bridge STEM

**Offline textbook scanning:** USB webcam or JPG/PNG upload, Tesseract extraction,
editable human review, verified passage storage and existing lesson preparation.
Start with `python -m level_bridge.main ocr-ui` after installing
`requirements-ocr.txt` and system Tesseract. [OCR installation, demo and evidence](docs/OCR.md).

> **Live-round update (14 Nov 2026) – Teach · Learn · Improve (report Section 7).** New: lesson packs with
> teacher review, model-free sessions from a pack, [S3] source tags, learner memory with recurring-pattern
> detection, checksummed USB profile bundles and an offline CBS portal; formula library extended to pressure,
> resistance and power; more robust extraction (five formula phrasings); question-rewording check tightened.
> **173 automated tests pass without a model (52 new). Nothing new has been measured on a Raspberry Pi yet.**
> **Windows laptop:** `powershell -ExecutionPolicy Bypass -File scripts\windows_demo.ps1` (setup + tests + full demo, no model).
> Runbook: [`docs/PRODUCT_DEMO.md`](docs/PRODUCT_DEMO.md) · one-command demo: `bash scripts/run_product_demo.sh --backend template`.
>
> | Command | Module |
> |---|---|
> | `pack-build --passage P [--out F]` | TEACH: build a lesson pack on the hub (LLM build phase) |
> | `pack-review --pack F [--approve-all \| --edit l1=file \| --use-template l2]` | TEACH: teacher review; edits must pass the gate |
> | `session --pack F --learner STU-7F3A [--consent] [--answers A]` | LEARN + IMPROVE: model-free session, profile update |
> | `profile-show --learner STU-7F3A` | IMPROVE: learner memory and patterns |
> | `profile-export --learner STU-7F3A --out /media/usb` | IMPROVE: SHA-256 bundle (refused without consent) |
> | `hub-import --dir /media/usb` · `portal` | IMPROVE: merge on the hub; write `outputs/cbs_portal.html` |
> | `gate-report` · `compare --passage P` | DEMO: model drafts accepted/rejected by the gate · AI alone vs Level Bridge |

Offline, adaptive learning assistant for Class 6–10 science passages. It runs on a **Raspberry Pi 5**
with **ExecuTorch**, which is the Namma AI Hackathon 2026, PS1 setting. A small on-device LLM
(Qwen2.5-0.5B-Instruct, exported to `.pte`) writes the wording. A deterministic Python engine
checks every term, number, unit, formula and relation, and it also does all answering, routing
and scoring.

---

## 1. Status: what is verified and what is not

| Part | Status |
|---|---|
| Deterministic engine: passage → knowledge map → registry → validator → items → routing → states → credits/CBM | **Implemented and tested** (119 automated tests pass on Linux x86-64, Python 3.13) |
| Priya walk-through from the report | **Reproduced by the engine**: placement 1/3 → L1 → L2 → L3 → bridge. Assessment 25 / 36, Recovery +3, Total 28, CBM +6 / 18 |
| ExecuTorch adapter (`TextLLMRunner`, `GenerationConfig`, `Stats`) | **Verified against the real executorch 1.4.0 runtime on x86-64** (torch 2.15.0, transformers 4.57.1) with a tiny random-weight `.pte` exported by `export_llm`: load, custom-op registration, generation, stats (TTFT, tokens), timeout/stop/recovery, validation and fallback. 6 real-runtime tests pass (`tests/integration/test_executorch_runtime.py`) |
| Qwen2.5-0.5B-Instruct export, loading on the Pi (aarch64), generation quality, latency, memory, thermals | **NOT yet verified**. This needs the Pi and the commands in §9–§13. No performance figures are claimed anywhere |
| Template backend | No LLM. It is used for tests and as a labelled fallback, and it is **never** reported as inference |

## 2. How the PS1 requirements map to this project

| PS1 requirement | Where it is handled |
|---|---|
| Offline, no cloud AI | the app has no HTTP client; `offline-check`; `scripts/test_offline_mode.sh` |
| On-device inference with ExecuTorch on the Pi | `src/level_bridge/model_runtime.py` (`executorch_runner`) |
| Takes a 150–300-word passage | `passage_processor.py` (warns outside that range; rejects below 50 or above 450 words) |
| Simplified explanation, summary and questions | `explanation_generator.py`, `question_generator.py` |
| Adapts to the learner | `adaptive_router.py` (rules R1–R4), `concept_states.py`, `scoring.py`, `cbm.py` |

## 3. Requirements

* **Laptop** (development and the no-model tests): any Linux or macOS machine with Python 3.10–3.13.
* **Raspberry Pi 5**: 4 GB or 8 GB RAM, **64-bit** Raspberry Pi OS (Bookworm), active cooler, 27 W supply. Python 3.10–3.13 (Bookworm ships 3.11).
* **Export host**: x86-64 Linux with about 8 GB of free RAM and about 10 GB of free disk.

## 4. Directory structure

```
level_bridge_stem/
├── README.md  requirements.txt  requirements-pi.txt  pyproject.toml  .gitignore  .env.example
├── config/            config.yaml · model_config.yaml · synonyms.yaml · item_contexts.yaml
├── models/README.md   export and verification steps (the .pte is not shipped)
├── data/passages/     speed_passage.txt (177 words, S1–S11) + density, pressure, ohms_law, power practice passages
├── data/expected_outputs/  reference stage JSONs and the Priya report (template backend, labelled)
├── data/test_cases/   scripted learners: priya · strong_reader · repair_failure · step_down · priya_density · ravi_density · meena_speed
├── src/level_bridge/  engine + runtime adapters + CLI (main.py)
├── scripts/           install · verify · export · per-sequence test wrappers · offline · benchmark · end-to-end
├── tests/unit · tests/integration · tests/hardware (LB_HARDWARE=1) · tests/fixtures
├── outputs/  logs/    run artefacts (git-ignored)
└── docs/              TEST_PLAN · ARCHITECTURE · TROUBLESHOOTING · DEMO_SCRIPT · EXECUTION_CHECKLIST
```

## 5. Quick start on a laptop (no model)

```bash
cd level_bridge_stem
bash scripts/install_dependencies.sh          # creates .venv and installs pinned packages
source .venv/bin/activate
bash scripts/run_all_tests.sh                 # full test suite + a no-model end-to-end run
```

Expected output (the last lines):

```
================= 119 passed, 10 skipped in ~3s =================
== no-model end-to-end (template backend - NOT LLM inference)
   Assessment 25 / 36 | Recovery +3 (outside maximum) | Total earned 28 | CBM +6 / 18
ALL NO-MODEL TESTS PASS
```

The skipped tests are the hardware tests, which only run on the Pi with `LB_HARDWARE=1`, and the
real-runtime contract tests, which need `LB_ET_TEST_DIR` (see below).

**Optional: test the real ExecuTorch runtime on a laptop** (about 3 GB of downloads, no model download):

```bash
pip install -r requirements-pi.txt                 # executorch 1.4.0 + torch + transformers
bash scripts/export_tiny_test_model.sh             # random-weight 2-layer Llama .pte, ~64 MB
LB_ET_TEST_DIR=models/test python -m pytest tests/integration/test_executorch_runtime.py -v   # 6 passed
```

This proves the adapter works with the real runner. The text it generates is noise by design, so
every explanation correctly falls back to a template. It says nothing about Pi performance.

## 6. CLI reference

Run commands as `python -m level_bridge.main <command>`, or as `level-bridge <command>` after `pip install -e .`.

| Command | Purpose | Main output |
|---|---|---|
| `check-env` | versions and whether the ExecuTorch runner can be imported | `outputs/environment_report.json` |
| `check-model [--backend B]` | checks the files, size and sha256, and runs a load test | `outputs/model_check.json` |
| `infer [--prompt P] [--repeat N] [--max-new-tokens K]` | raw inference with the runner's stats | `outputs/inference_*.json` |
| `process [--passage F]` | runs analysis stages 1–3 | `outputs/stage1..3_*.json` |
| `build [--backend B] [--allow-template-fallback]` | builds explanations and the item bank | `outputs/stage4_explanations.json`, `stage5_item_bank.json`, `stage_build_log.json` |
| `session` / `demo [--answers F] [--run-id ID]` | a learning session: scripted with `--answers`, otherwise interactive | `learning_report_*.json`, `knowledge_map_*.json`, `session_events_*.json`, `session_transcript_*.txt` |
| `offline-check [--require-offline] [--no-probe]` | network state and whether the backend is local | `outputs/offline_check.json` |
| `benchmark [--warmup N] [--runs M]` | runs warm-up passes, then measured passes | `outputs/benchmark_*.json` and `.csv` |

Global options: `--root`, `--model-config`, `-v`.

Exit codes: `0` ok, `2` config or input error, `3` model unavailable, `4` unexpected error (traceback in `logs/error_*.log`).

**Backends.** The default is `executorch_runner`. Without a model, `build`, `session` and `demo`
**stop with exit code 3**. To run without a model, use one of these two options:

* `--backend template` runs deliberately without an LLM.
* `--allow-template-fallback` tries the model first and, if it is unavailable, falls back to templates. A banner says so and the report records `fallback_used: true`.

## 7. Configuration

* `config/config.yaml` sets:
  * passage limits
  * the retry budget (`max_attempts: 2`, which means one retry)
  * `max_new_tokens` for each kind of output
  * R1 mapping, step-down threshold and the Consolidated switch (off)
  * Bloom weights and the CBM table
  * benchmark run counts
* `config/model_config.yaml` sets:
  * the backend and model paths
  * temperature (0, which is greedy)
  * the prompt format (Qwen ChatML)
  * the timeout and system prompt
  * artifact metadata and the recorded sha256
* `config/synonyms.yaml` lists accepted surface forms for registry terms.
* `config/item_contexts.yaml` holds the numeric contexts: train 180 km/3 h, cyclist 24 km/2 h, Meena 2 km/30 min, buses, cars, and Asha/Ravi.

## 8. Raspberry Pi setup

```bash
# on the Pi (64-bit OS):  uname -m   ->  aarch64
sudo apt update && sudo apt install -y python3-venv git
git clone <your repo> ~/level_bridge_stem    # or copy the ZIP and unzip it
cd ~/level_bridge_stem
bash scripts/install_dependencies.sh --pi    # executorch==1.4.0 (+ torch, torchao, tokenizers), transformers
source .venv/bin/activate
bash scripts/verify_environment.sh
```

Check that the output shows `"executorch": "1.4.0..."` and `"executorch_llm_runner_importable": true`.
The exact package set that was resolved is saved in `outputs/pip_freeze.txt`.

## 9. Model export (on the x86-64 host)

```bash
bash scripts/export_model_host.sh
scp ~/lb_export/qwen2_5_0_5b_instruct_8da4w.pte ~/lb_export/tokenizer.json pi@<pi-host>:~/level_bridge_stem/models/
```

The export uses XNNPACK with 8da4w quantisation, a KV cache and a 1024-token context, with ExecuTorch
**1.4.0** on both sides. Check the example file names against the repository tag before you run it.
Details are in [models/README.md](models/README.md).

## 10. Model verification (sequence B, on the Pi)

```bash
bash scripts/verify_model.sh --write-checksum
python scripts/test_model_inference.py
```

Expected results:

* `outputs/model_check.json` contains `"load": {"ok": true, ...}`.
* There are three `infer` runs, each with `ok=True`, a `ttft_ms` value and `generated_tokens > 0`.
* The repeated prompts give identical text.
* The hardware pytest reports 4 passed.

If loading fails, the exact runner error is printed and the script stops. Do **not** substitute another model. See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) §2.

## 11. Running the test sequences

| Seq | What it tests | Command | Where |
|---|---|---|---|
| A | environment | `bash scripts/verify_environment.sh` · `python scripts/test_environment.py` | laptop + Pi |
| B | model and inference | `python scripts/test_model_inference.py` | **Pi** |
| C | passage stages | `python -m level_bridge.main process` · `python scripts/test_passage_processing.py` | any |
| D | registry, knowledge map, validator | `python scripts/test_registry_validator.py` | any |
| E | explanations (validation, retry, fallback) | `python scripts/test_explanations.py` · on the Pi: `python -m level_bridge.main build` | any / Pi |
| F | summary and items; level independent of rung | `python scripts/test_question_generation.py` · `python scripts/test_cognitive_bias.py` | any |
| G | placement R1 | `python scripts/test_placement.py` | any |
| H, M | routing and the bridge | `python scripts/test_routing.py` | any |
| I | numeric engine | `python scripts/test_numeric_engine.py` | any |
| J | 540 misconception | `python scripts/test_misconception.py` | any |
| K | credits and CBM | `python scripts/test_scoring_cbm.py` | any |
| L | concept states | `python scripts/test_concept_states.py` | any |
| N | failure handling | `python scripts/test_failures.py` | any |
| O | offline | `bash scripts/test_offline_mode.sh` (**at the Pi console, not over SSH**) | **Pi** |
| P | benchmark | `python scripts/benchmark_pi.py` | **Pi** |
| Q | everything | `bash scripts/run_end_to_end.sh` (Pi) · `bash scripts/run_all_tests.sh` (no model) | Pi / any |

The full matrix, with preconditions, inputs, pass criteria and failure conditions for each test, is in [docs/TEST_PLAN.md](docs/TEST_PLAN.md).

## 12. End-to-end master command (sequence Q)

```bash
bash scripts/run_end_to_end.sh                   # Pi, real model, scripted Priya learner
bash scripts/run_end_to_end.sh --interactive     # Pi, live learner at the keyboard
BACKEND=template bash scripts/run_end_to_end.sh  # any machine, no model (labelled NON-LLM)
```

The command writes everything into `outputs/e2e_<time>/`:

* `terminal.txt`
* `learning_report_*.json`
* `knowledge_map_*.json`
* `session_events_*.json`
* `benchmark_*.json` and `benchmark_*.csv`
* `test_summary.txt` and `junit.xml`
* `*.jsonl` structured logs
* `errors.log`
* `inference.txt` and `inference_*.json` (3 raw generations with runner stats)
* **`REPORT_SUMMARY.md` and `report_metrics.json`**: one report-ready page. Every metric (device, versions, model size and sha256, cold start, load, T_build breakdown, TTFT, tokens/s, CPU %, peak RAM, temperature, throttling, repair latency, LLM outputs accepted, offline status, scores, concept states, test result) is read from the evidence files. Anything not measured says "not measured"; template runs are labelled NON-LLM at the top.

If the model is missing, it stops at step 2 with exit code 3. To rebuild the summary for any run
folder: `python scripts/capture_for_report.py outputs/e2e_<time>`. Run the offline test first, so
the summary can include the offline result.

## 13. Benchmark and offline evidence

* Run `python scripts/benchmark_pi.py`. It does 1 warm-up run and then 5 measured runs, and reports the median of the measured runs. It records:
  * cold start and model load
  * T_build, split into preprocessing, model generation and validation/templates
  * TTFT, tokens and tokens/s, all taken from the runner's `Stats`
  * CPU utilisation: system-wide % and process % (measured only for intervals of 0.5 s or more)
  * peak RSS and model file size
  * CPU temperature and `vcgencmd get_throttled`
* Run `bash scripts/test_offline_mode.sh`. It turns off all networking with `nmcli`, proves the device is offline, runs a full session with the real model, and then turns networking back on. It refuses to run over SSH.

Copy the numbers into your report only from these files. The metric table to fill in is in [docs/EXECUTION_CHECKLIST.md](docs/EXECUTION_CHECKLIST.md).

## 14. Example session (template backend, laptop)

This is an excerpt from `data/expected_outputs/priya_session_transcript_TEMPLATE.txt`:

```
PLACEMENT  1/3 -> R1: start at L1
Q2 [L1 · APPLY · quantitative · C3] A train covers 180 km in 3 h. What is the average speed in km/h? (type a number)
      answer 540 km/h · certainty 3 -> ✗ FRAGILE [wrong_operation_multiply]   credits +0  CBM -6
   REPAIR (template)
      180 km × 3 h = 540 km·h, which is not a unit of speed.
      Use the rule from S3: speed = distance ÷ time.
      speed = 180 km ÷ 3 h  ->  60 km/h.
   2ND CHANCE Q2b: A cyclist rides 24 km in 2 h. ...
      answer 12 km/h · certainty 2 -> ✓ REPAIRED   recovery +3  CBM +2
R3  all L1 items resolved -> climb to L2
...
BRIDGE  S3, S4 exactly as printed (verbatim=True)
T1 [L3 · TRANSFER · quantitative · C3] Meena walks 2 km to school in 30 min. ...
      answer 4 km/h · certainty 3 -> ✓ TRANSFERRED   credits +12  CBM +3
LEARNING REPORT
   backend: template   LLM inference: NO (templates)   LLM outputs accepted: 0
   Assessment 25 / 36 | Recovery +3 (outside maximum) | Total earned 28 | CBM +6 / 18
```

On the Pi with the model, the banner shows `executorch_runner` and labels each explanation with
its source. The wording changes, but the numbers, routing, states and credits do not.

## 15. Output files

| File | Contents |
|---|---|
| `stage1_passage.json` | normalised text, word count, sentences with ids, sha256 |
| `stage2_knowledge_map.json` | definitions, formula, verified worked example, relationships, cause–effect, units, concepts |
| `stage3_key_term_registry.json` | 7 required terms with sentence ids, meanings and synonyms |
| `stage4_explanations.json` | summary, L1, L2 and L3, each with its source, validation and every attempt |
| `stage5_item_bank.json` | 12 items: keys, explanations, source ids, labels, numeric solutions and error models |
| `learning_report_*.json` | placement, path, concept states and history, scores, teacher notes, run info (backend, LLM-accepted count, timings) |
| `session_events_*.json` | every event in order |
| `benchmark_*.json` / `.csv` | per-run and median metrics, device info, thermal data |

## 16. How the explanation pipeline guarantees correctness

1. Python extracts facts from the passage and builds the registry.
2. The LLM drafts the summary, L1 and L2.
3. The validator runs 9 checks (listed in ARCHITECTURE.md §4).
4. If a draft fails, the LLM gets one retry, and the prompt includes the failed checks.
5. If the retry also fails, a deterministic template is used instead. The template passes the same validator.

Numeric answers are always computed by `formula_engine.compute()`. The LLM never decides correctness.

## 17. Adaptive logic

* **R1 placement:** a score of 0–1 starts at L1, 2 starts at L2, 3 starts at L3.
* **R2:** a wrong answer leads to a repair and one second chance.
* **R3:** the learner climbs when every item at the rung is resolved. Two unresolved errors step the learner down; at L1 this triggers the Safety Net and a teacher note.
* **R4:** a bridge check on the verbatim passage.

The concept states are Learning, Provisional, Fragile, Repaired and Transferred. Consolidated is proposed and turned off. The open cases are interpreted in ARCHITECTURE.md §7.

## 18. Scoring

* Assessment credits = Bloom weight × certainty, for correct answers only.
* Recovery credits = weight, for a correct second chance. They are reported **outside** the maximum.
* CBM uses +1/+2/+3 for correct answers and 0/−2/−6 for wrong ones.
* All totals are computed from the responses.

## 19. Demo

See [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md). It is a 5–7 minute timeline, marks what is live and what is recorded, and includes a fallback plan.

## 20. Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md). It covers installation, model, running, offline and benchmark problems.

## 21. Known limitations

* Knowledge extraction is rule-based. It is tuned for short textbook passages with explicit definitions, a "calculated by dividing" formula and comparative sentences. Other phrasing may be missed, and those passages are reported with fewer facts rather than with invented ones.
* There are two formulas (speed and density). Other topics need entries in `FORMULAS` and `item_contexts.yaml`.
* Synonym matching uses a list, not semantic matching.
* The Consolidated state and the representation switch in the Safety Net are proposed extensions and are not implemented.
* The `transformers` pin in `requirements-pi.txt` is our choice. The ExecuTorch runner imports it, but the wheel does not declare it.

## 22. Honesty rules followed in this package

* No ExecuTorch API is used that is not present in the 1.4.0 wheel.
* No inference result, latency, memory or thermal figure appears before it has been measured.
* Mocks (`ScriptedRuntime`) appear only in tests and are labelled.
* Template output is never counted as LLM output. `llm_outputs_accepted` counts validated model outputs only.
* A model that cannot be loaded is reported with its exact error and is never silently replaced.
