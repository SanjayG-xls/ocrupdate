# Test plan and master test matrix

## OCR extension

Run `python -m pytest -q` with optional OCR Python dependencies installed to include
OCR decoding/preprocessing, camera lifecycle mocks, scientific review flags,
passage validation, API security, confirmation invalidation and approval integration.
`LB_OCR_HARDWARE=1 python -m pytest -q tests/hardware/test_webcam_capture.py` is
opt-in actual capture/OCR, with the webcam pointing at printed English text.
Mocks do not count as hardware acceptance. Full commands, Windows evidence and
Pi acceptance steps are in [OCR.md](OCR.md).

All commands run from the project root with the virtual environment active
(`source .venv/bin/activate`; the package is installed with `pip install -e .`, otherwise
prefix commands with `PYTHONPATH=src`).

* **LLM?** – needs the exported `.pte` model and a working ExecuTorch runtime.
* **Pi?** – must be run on the Raspberry Pi 5 to count as evidence.
* Everything marked *no / no* runs on any Linux laptop and is part of `bash scripts/run_all_tests.sh`.
* Template-backend runs are labelled `NON-LLM` in every output and are never evidence of inference.

Short command forms: `LB = python -m level_bridge.main`, `PT = python -m pytest -v`.

## A – Environment and dependencies

| ID | Feature | Preconditions | Input | Command | Expected behaviour / output | Pass criteria | Failure conditions | LLM? | Pi? |
|---|---|---|---|---|---|---|---|---|---|
| A1 | Install | Python 3.10–3.13 | requirements*.txt | `bash scripts/install_dependencies.sh [--pi]` | venv created, packages installed, `outputs/pip_freeze.txt` | exit 0 | unsupported Python; pip cannot resolve torch (see TROUBLESHOOTING §1) | no | `--pi` yes |
| A2 | Version report | A1 | – | `bash scripts/verify_environment.sh` | `outputs/environment_report.json` with Python, PyYAML, torch, transformers, executorch versions; `executorch_llm_runner_importable` | `required_ok: true`; on Pi also `executorch_version_matches_pin: true` and runner importable `true` | import errors listed verbatim | no | for ET part |
| A3 | Pins | – | requirements files | `PT tests/unit/test_a_environment.py` | every requirement uses `==`; ExecuTorch pin = config | all pass | unpinned line | no | no |
| A4 | Config | – | config/*.yaml | same | YAML parses; backend local; temperature 0 | all pass | parse error | no | no |

## B – Model loading and inference (real model)

| ID | Feature | Preconditions | Input | Command | Expected | Pass | Failure | LLM? | Pi? |
|---|---|---|---|---|---|---|---|---|---|
| B1 | Artifact present | `.pte`, tokenizer in models/ | – | `bash scripts/verify_model.sh` | sizes, sha256, load result in `outputs/model_check.json` | `load.ok: true`, `model_load_s` recorded | `Model file not found` / `TextLLMRunner could not load the model: <exact error>` → exit 3. **Do not substitute another model.** | yes | yes |
| B2 | Single inference | B1 | "In one sentence, what is speed?" | `LB infer --max-new-tokens 48` | text + `ttft_ms`, `prompt_tokens`, `generated_tokens`, wall time, peak RSS → `outputs/inference_*.json` | `ok: true`, `generated_tokens > 0` | empty output, timeout, runner exception (all reported with `ok: false`) | yes | yes |
| B3 | Repeated inference | B1 | "Name the unit of speed." ×3 | `LB infer --repeat 3 --max-new-tokens 24` | 3 runs; identical text (greedy, temperature 0) | all ok; texts identical | non-deterministic text → check temperature | yes | yes |
| B4 | Hardware pytest | B1 | – | `LB_HARDWARE=1 PT tests/hardware` | 4 tests run (version, single, determinism, build) | all pass | skipped = not run (not a pass) | yes | yes |
| B6 | Adapter contract (REAL runtime, any CPU) | executorch 1.4.0 installed; `bash scripts/export_tiny_test_model.sh` | random-weight tiny `.pte` | `LB_ET_TEST_DIR=models/test PT tests/integration/test_executorch_runtime.py` | load with custom ops, stats, determinism, timeout + recovery, bad file → RuntimeUnavailable, noise rejected → template | 6 passed | missing operator / import errors | real runtime, not the project model | no |
| B5 | Adapter contract (mock) | – | fake runner objects | `PT tests/unit/test_n_runtime_failures.py -k "greedy or stats or prompt"` | GenerationConfig(echo=False, max_new_tokens, temperature=0.0); ChatML prompt; stats mapped | pass | – | no (mock) | no |

## C – Passage processing

| ID | Feature | Preconditions | Input | Command | Expected | Pass | Failure | LLM? | Pi? |
|---|---|---|---|---|---|---|---|---|---|
| C1 | Stages to JSON | – | speed_passage.txt | `LB process` | `outputs/stage1_passage.json`, `stage2_knowledge_map.json`, `stage3_key_term_registry.json` | 177 words, S1–S11; JSON equals `data/expected_outputs` | mismatch | no | no |
| C2 | Segmentation | – | decimals/abbreviations | `PT tests/unit/test_c_passage.py` | "2.5" and "e.g." do not split | pass | – | no | no |
| C3 | Unsupported passage | – | empty / 1 sentence / <50 words | `LB process --passage tests/fixtures/unsupported_passage.txt` | `PASSAGE ERROR: …`, exit 2 | exit 2 | crash | no | no |

## D – Knowledge map and key-term registry

| ID | Feature | Preconditions | Input | Command | Expected | Pass | Failure | LLM? | Pi? |
|---|---|---|---|---|---|---|---|---|---|
| D1 | Core types | – | passage | `PT tests/unit/test_d_registry_validator.py -k core_types` | definition 4, quantitative 4, cause_effect 1 | pass | – | no | no |
| D2 | Registry (7) | – | passage | `-k seven_entries` | speed, speed = distance ÷ time, m/s, km/h, average speed, speedometer, odometer; "motion" not required | pass | – | no | no |
| D3 | Synonyms | – | "kilometres per hour", "divide the distance by the time" | `-k synonyms` | recognised as km/h and the formula | pass | – | no | no |
| D4–D11 | Validator rejects | – | fixtures/llm_outputs.json | `-k rejects` | missing terms→`key_term_coverage`; wrong formula→`formula_preserved`; 75 km/h→`numerical_consistency`; 60 m/s→`unit_consistency`; "more time is faster"→`relationship_direction`; new facts→`unsupported_content`; special tokens / empty→`well_formed` | each rejected with that check | accepted | no | no |
| D12 | Validator accepts faithful text | – | good_summary, good_l2 | `-k accepts` | passed | pass | false rejection | no | no |
| D13 | L3 unchanged | – | passage / edited passage | `-k l3_must` | original passes; one edited number fails | pass | – | no | no |

**Documented limits of D.** The knowledge map is rule-based (regular patterns for "is called",
"is calculated by dividing … by …", "If … the one that … is faster", "That is why …"). It is
designed for short textbook passages of this shape and will miss facts expressed in other
constructions. Synonym matching is a configured list (`config/synonyms.yaml`), not semantic
similarity. The unsupported-content check flags sentences with ≥4 content words absent from the
passage; it can miss a short invented fact that reuses passage words.

## E – L1/L2/L3 explanations

| ID | Feature | Preconditions | Input | Command | Expected | Pass | Failure | LLM? | Pi? |
|---|---|---|---|---|---|---|---|---|---|
| E1 | First attempt accepted | – | scripted good L2 | `PT tests/unit/test_e_explanations.py -k first_attempt` | `source: llm`, 1 attempt | pass | – | no (mock) | no |
| E2 | One retry with feedback | – | wrong formula, then good | `-k retry` | `source: llm_retry`; 2nd prompt contains validator reason | pass | – | no (mock) | no |
| E3 | Template fallback | – | 2 invalid outputs | `-k fall_back` | `source: template`, `fallback: true`, both attempts recorded as rejected | pass | – | no | no |
| E4 | No false claim | – | runtime error + empty | `-k never_reported` | template; every attempt `generation_ok: false` | pass | – | no | no |
| E5 | L3 original | – | – | `-k l3_is_original` | text identical to passage, glosses separate | pass | – | no | no |
| E6 | Real-model build | B1 | passage | `LB build` | `outputs/stage4_explanations.json` with per-kind `source` and attempts; `stage_build_log.json` with per-call stats | exit 0; sources honestly recorded (llm / llm_retry / template) | – | yes | yes |

## F – Summary and questions

| ID | Feature | Preconditions | Input | Command | Expected | Pass | Failure | LLM? | Pi? |
|---|---|---|---|---|---|---|---|---|---|
| F1 | Composition | – | – | `PT tests/unit/test_f_questions.py` | 3 placement, 4 assessment, 4 second chance, 1 transfer | pass | – | no | no |
| F2 | Item completeness | – | – | same | each item: key, explanation, source sentence ids, knowledge type, cognitive level, concept id | pass | – | no | no |
| F3 | L1 can Apply, L3 can Recall | – | – | `python scripts/test_cognitive_bias.py` | rung and cognitive level independent; credits follow level | pass | – | no | no |
| F4 | Transfer wording simple | – | T1 | test_f | ≤25 words | pass | – | no | no |
| F5 | Answers from Python | – | Q2 | test_f | solution 60 km/h computed by formula engine; numeric entry, no invalid distractors | pass | – | no | no |
| F6 | LLM stem rewording guarded | – | stem with changed number | `-k rewording` | rejected "numbers changed", template stem kept | pass | – | no (mock) | no |

## G – Placement (R1)

| ID | Input | Command | Expected | LLM? | Pi? |
|---|---|---|---|---|---|
| G1–G4 | 0/3, 1/3, 2/3, 3/3 | `PT tests/unit/test_g_placement.py` | L1, L1, L2, L3; note "not a diagnosis" | no | no |
| G5 | probe types | same | literal, word_in_context, inference | no | no |

## H – Routing (R2–R4)

| ID | Feature | Input | Command | Expected | LLM? | Pi? |
|---|---|---|---|---|---|---|
| H1 | Correct path | priya_answers.json | `PT tests/integration/test_h_routing.py -k priya` | L1 → L2 → L3 → bridge; R3, R3, R4 | no | no |
| H2 | Incorrect → repair | Q2 = 540 | same | repair event `wrong_operation_multiply` | no | no |
| H3 | Repair success | Q2b = 12 | `-k repair_success` | Repaired, recovery +3 | no | no |
| H4 | Repair failure | repair_failure_answers.json | `-k repair_failure` | Safety Net, teacher note, end at L1 | no | no |
| H5 | L1→L2, L2→L3 climb | priya | H1 | climb events | no | no |
| H6 | Step-down | step_down_answers.json | `-k step_down` | L2 → L1 (R3 step_down), then end (items already delivered) | no | no |
| H7 | Two unresolved at L1 | – | `-k l1_ends` | end with 2 teacher notes | no | no |
| H8 | Bridge activation | strong_reader_answers.json | `-k placement_3` | R4, verbatim extract S3+S4 | no | no |

## I – Numeric engine

| ID | Input | Command | Expected |
|---|---|---|---|
| I1 | 180 km / 3 h | `PT tests/unit/test_i_formula_engine.py` | Formula, Substitute, Calculate, Answer: 60 km/h |
| I2 | 24 km / 2 h | same | 12 km/h |
| I3 | 2 km / 30 min | same | Convert 30 min = 0.5 h; 4 km/h |
| I4 | 120 km / 2 h | same | 60 km/h |
| I5 | time 0 | same | `InvalidInput: time must be greater than zero` |
| I6 | missing unit | same | `InvalidInput: Missing unit …` |
| I7 | kg / h | same | `InvalidInput: distance must be a length` |
| I8 | never 540 km/h | same | 540 exists only as error model labelled km·h |

All I tests: no LLM, no Pi.

## J – Misconception and repair (540 case)

| ID | Input | Command | Expected |
|---|---|---|---|
| J1 | Q2 "540 km/h" | `PT tests/unit/test_j_misconception.py` | `wrong_operation_multiply`, expected 60 km/h |
| J2 | repair text | same | contains "540 km·h", "60 km/h", "S3" |
| J3 | Q2b cyclist "12" / "12 km/h" | same | correct; "48" incorrect |
| J4 | other errors | same | 0.0167 inverted, 180 ignored variable, 183 add, 77 generic |
| J5 | state/credit/CBM updates | `-k priya` (H1) | C3 Fragile → Repaired → Transferred; Q2 0 credits, CBM −6; Q2b recovery +3, CBM +2 |

## K – Credits and CBM

| ID | Input | Command | Expected |
|---|---|---|---|
| K1–K6 | (✓,1)(✓,2)(✓,3)(✗,1)(✗,2)(✗,3) | `PT tests/unit/test_k_scoring_cbm.py` | +1 +2 +3 0 −2 −6 |
| K7 | recovery outside max | same | max 9, recovery 3 |
| K8 | Priya ledger (computed) | same + H1 + `test_opq_cli -k end_to_end` | 25/36, +3, 28, CBM +6/18 – computed from responses, not stored |

## L – Concept states

| ID | Command | Expected |
|---|---|---|
| L1 legal transitions (8) | `PT tests/unit/test_l_concept_states.py` | final states per table in ARCHITECTURE.md |
| L2 illegal transitions (4) | same | `IllegalTransition` (e.g. Repaired never → Provisional) |
| L3 Consolidated | same | refused unless `enable_consolidated_state: true` |
| L4 readable report | `LB demo --backend template --answers data/test_cases/priya_answers.json` | LEARNING REPORT table per concept with flags |

## M – Bridge check

| ID | Input | Command | Expected |
|---|---|---|---|
| M1 | Meena 2 km in 30 min = "4 km/h" | H1 / H8 | ✓, C3 Transferred, +12 credits; extract S3, S4 verbatim |
| M2 | "60 km/h" | `-k meena_wrong` | ✗, C3 Fragile, repair shown |

## N – Failure handling

| ID | Failure | Command | Expected | LLM? |
|---|---|---|---|---|
| N1 | missing model | `PT tests/unit/test_n_runtime_failures.py -k missing_model`; `LB build` without model | `RuntimeUnavailable`; CLI exit 3 with instructions | no |
| N2 | load failure | `-k load_failure` | `RuntimeUnavailable` | no |
| N3 | timeout | `-k timeout` | `ok: false`, "timeout", `runner.stop()` called | no |
| N4 | empty output | `-k empty_output` | `ok: false`, "empty model output" | no |
| N5–N8 | malformed / missing terms / wrong formula / wrong relation | `-k failures_fall_back` + D tests | template fallback, `fallback: true` | no |
| N9 | retry failure | E3 | 2 attempts recorded, template | no |
| N10 | unsupported passage | C3 | exit 2 | no |
| N11 | fallback ≠ LLM | `-k fallback_not_counted` | `llm_outputs_accepted: 0`; report `is_llm_inference` false for template | no |
| N12 | explicit fallback flag | `LB build --allow-template-fallback` without model | runs; banner "WARNING … template fallback" and `fallback_used: true` | no |

## O – Offline operation

| ID | Command | Expected | Pi? |
|---|---|---|---|
| O1 | `LB offline-check` | JSON: default route, interfaces, nmcli state, DNS/TCP probes, `backend_is_local` | any |
| O2 | `bash scripts/test_offline_mode.sh` (at the Pi console, NOT over SSH) | networking off → `offline: true` → full Priya session with the real model → networking back on | yes |

## P – Benchmark

| ID | Command | Records |
|---|---|---|
| P1 | `python scripts/benchmark_pi.py` | cold start, model load, per run: T_build, preprocessing, model generation, validation/templates, TTFT (first call), generated tokens, tokens/s, CPU temperature before/after, peak RSS; summary: medians of 5 measured runs after 1 warm-up, model file size, device, throttle flags. `outputs/benchmark_*.json` + `.csv` |
| P2 | `PT tests/integration/test_opq_cli.py -k benchmark` | template run labelled NON-LLM; token fields `null` |

Repair latency is measured inside every session (`run.timings.repair_latency`). No figure is
written into the report or README until it has been produced by P1 on the Pi.

## Q – End to end

| ID | Command | Output |
|---|---|---|
| Q1 | `bash scripts/run_end_to_end.sh` (Pi) | `outputs/e2e_<time>/`: terminal.txt, learning_report_*.json, knowledge_map_*.json, session_events_*.json, benchmark_*.json/.csv, test_summary.txt, junit.xml, *.jsonl logs, errors.log |
| Q2 | `bash scripts/run_all_tests.sh` (laptop or Pi, no model) | full pytest + no-model demo; `outputs/test_summary.txt` |
| Q3 | `PT tests/integration/test_expected_outputs.py` | deterministic stages identical to `data/expected_outputs` |
