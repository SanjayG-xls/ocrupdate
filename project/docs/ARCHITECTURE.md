# Architecture

## Optional OCR input path

`ocr.camera` (backend USB capture) or validated local upload → `ocr.preprocessing`
and `ocr.processor` (OpenCV/Tesseract) → `ocr.verification` (review flags) →
`ocr.service` (editable review, hash-bound human confirmation, immutable UTF-8 file)
→ existing `pipeline.build` / `lesson_pack.make_pack` → teacher `pack-review` →
existing model-free session. `ocr.web` serves local Flask HTML/CSS/JavaScript.
Both human OCR verification and educational approval remain distinct gates.
OCR-marked pending packs are refused for student sessions. No OCR dependency is
imported by ordinary core workflows. [Installation and constraints](OCR.md).

## 1. Split of responsibilities

```
                 ┌─────────────────────── deterministic learning engine (Python) ───────────────────────┐
passage.txt ──►  passage_processor ─► sentence_segmenter ─► knowledge_map ─► key_term_registry
                      │                                         │                 │
                      │                    formula_engine ◄─────┤                 │
                      │                    quantity_parser      │                 ▼
                      │                                         ├──────► concept_validator ◄────────┐
                      ▼                                         ▼                                    │
               question_generator (items, keys,      explanation_generator ── prompt ──► model_runtime ──► ExecuTorch
               numeric solutions, error models)        (validate → 1 retry → template)          (TextLLMRunner, .pte)
                      │                                         │
                      ▼                                         ▼
     adaptive_router (R1–R4) ── misconception_detector ── repair_engine ── bridge_check
                      │
          concept_states · scoring (credits) · cbm  ──►  learning_report (JSON + terminal)
                 └────────────────────────────────────────────────────────────────────────────────────┘
```

The **LLM only produces wording** (summary, L1, L2, optional stem rewording, optional repair
wording). Every fact that decides correctness – terms, the formula, numbers, units, relation
direction, answer keys, numeric solutions, error models, routing, states, credits – is produced or
checked by Python. A model output is used only after it passes the validator; otherwise the
generator retries once with the validator's reasons and then falls back to a deterministic
template. The source of every text (`llm`, `llm_retry`, `template`, `original`) is recorded.

`model_runtime` is the only module that touches ExecuTorch. The engine imports it through the
`ModelRuntime` interface (`load()`, `generate(prompt, max_new_tokens) -> GenerationResult`).

## 2. Modules

| Module | Responsibility |
|---|---|
| `config.py` | project root detection, YAML loading, JSON-lines structured logging |
| `passage_processor.py` | normalisation, word-count limits (target 150–300, hard 50–450), sha256 |
| `sentence_segmenter.py` | sentence ids S1…Sn; decimals and abbreviations protected |
| `quantity_parser.py` | units with dimensions/factors, aliases, quantity and answer parsing |
| `formula_engine.py` | formulas (speed, density), `compute()` with dimension checks and explicit conversions, error models, numeric evaluation |
| `knowledge_map.py` | rule-based extraction: definitions, formula facts, worked examples (verified by recomputation), relationships, cause–effect, unit facts, concepts |
| `key_term_registry.py` | the terms every explanation must preserve (+ synonyms) |
| `concept_validator.py` | checks listed in §4 |
| `model_runtime.py` | `executorch_runner` (primary), `llama_main` (alternative), `template` (no LLM), `scripted` (tests) |
| `explanation_generator.py` | summary/L1/L2 with retry + template fallback; L3 = original text + separate glosses |
| `question_generator.py` | placement probes, assessment, second-chance and transfer items; guarded LLM stem rewording |
| `placement.py` | R1 |
| `misconception_detector.py` | MCQ error codes; numeric answers re-solved and matched against error models |
| `repair_engine.py` | template repair (optional validated LLM wording), Safety Net (word card + worked example) |
| `bridge_check.py` | verbatim extract of the transfer item's source sentences |
| `adaptive_router.py` | session engine: R1–R4, repair, second chance, step-down, bridge |
| `concept_states.py` | state machine (§5) |
| `cbm.py`, `scoring.py` | certainty-based marking; Bloom-weighted credits and recovery credits |
| `learning_report.py` | report JSON and terminal rendering |
| `offline_checker.py` | route/interface/nmcli/DNS/TCP checks |
| `benchmark.py` | warm-up + measured runs, medians, CSV/JSON |
| `pipeline.py` | build-phase orchestration with T_build breakdown |
| `answer_providers.py` | scripted (by intent) and interactive learners |
| `main.py` | CLI |

## 3. ExecuTorch integration (what is verified and what is not)

Verified from the `executorch==1.4.0` `manylinux_2_28_aarch64` wheel (`_llm_runner.pyi`, `version.py`):
`executorch.extension.llm.runner.TextLLMRunner(model_path, tokenizer_path, data_path=None)`,
`.generate(prompt, GenerationConfig, token_callback, stats_callback)`, `.reset()`, `.stop()`,
`GenerationConfig(echo, max_new_tokens, temperature, …)` and the `Stats` fields used for TTFT and
token counts. `executorch` is a namespace package; the runner module imports `torch` and
`transformers` on import.

**Verified on x86-64 with the real runtime** (executorch 1.4.0, torch 2.15.0, transformers 4.57.1)
using a tiny random-weight Llama `.pte` exported with `export_llm` (KV cache, custom SDPA, XNNPACK):

* The custom operator libraries must be imported **before** `TextLLMRunner` loads a KV-cache export. Without them, loading fails with `Missing operator: llama::custom_sdpa.out`. The libraries are `executorch.extension.pybindings.portable_lib`, `executorch.extension.llm.custom_ops.custom_ops` and `executorch.kernels.quantized`. The adapter imports them and records which ones loaded.
* The C++ runner writes tokens and a `PyTorchObserver {…}` line to fd 1. The adapter captures that output so the learner's terminal stays clean, and keeps the observer line as raw evidence.
* `Stats.to_json_string()` uses `prompt_tokens` / `generated_tokens`, and the adapter maps both naming forms.
* `stop()` ends a timed-out generation, and the runner is usable again afterwards.
* Prompts for the summary, L1, L2 and stems measured 290–364 tokens with a Llama-3 tokenizer. With `max_new_tokens` ≤ 300 they fit the 1024 context. The Qwen tokenizer is of similar granularity but has not been measured yet.

**Not yet verified (requires the Pi):** that the exported `.pte` loads in this runner on the Pi 5,
generation quality, latency, memory and thermals. The hardware tests and benchmark produce this
evidence; nothing in the project states those results in advance.

Prompts use the Qwen2.5 ChatML template; temperature 0 (greedy) makes outputs repeatable. Each
call runs in a worker thread with a timeout; on timeout `runner.stop()` is called and the result
is `ok: false`.

## 4. Validator checks

| Check | Applies to | Rejects |
|---|---|---|
| `well_formed` | all | empty output, special/control tokens, prompt artifacts |
| `key_term_coverage` | summary (≥50 %), L1/L2 (100 %) | missing registry terms (synonyms accepted) |
| `formula_preserved` | summary, L1, L2 | formula absent or altered (e.g. time ÷ distance) |
| `original_text_unchanged` | L3 | any edit of the passage |
| `numerical_consistency` | all | numbers not in the passage (or the item, for repair) |
| `unit_consistency` | all | number–unit pairs not in the passage (60 m/s for 60 km/h) |
| `relationship_direction` | all | statements contradicting the formula ("more time is faster") |
| `unsupported_content` | summary, L1, L2, repair | sentences with ≥4 content words not in the passage |
| `l1_short_sentences` | L1 | sentences longer than 14 words |

## 5. Concept states

| From | Event | To |
|---|---|---|
| Learning | correct_first | Provisional |
| Learning | wrong_first | Fragile |
| Provisional / Repaired / Transferred | wrong (later inconsistent answer) | Fragile |
| Fragile | second_chance_correct | Repaired (not mastery) |
| Fragile | second_chance_wrong | Fragile (unresolved → Safety Net) |
| Provisional / Repaired | transfer_correct | Transferred (initial evidence only) |
| Provisional / Repaired | transfer_wrong | Fragile |
| Transferred | independent_correct | Consolidated – **proposed, disabled** (`routing.enable_consolidated_state`) |

Anything else raises `IllegalTransition`.

## 6. Scoring

* Bloom weights: recall 1, understand 2, apply 3, transfer 4. Assessment credits = weight × certainty if correct, else 0; item maximum = weight × 3.
* Second-chance items: recovery credits = weight if correct, reported **outside** the maximum.
* CBM (Gardner-Medwin): correct 1/2/3, wrong 0/−2/−6 for certainty 1/2/3; applied to assessment, transfer and second-chance items; placement is unscored.
* All totals are computed from the response log (`ScoreLedger`); the Priya figures 25/36, +3, 28, +6/18 are test expectations, not stored values.

## 7. Interpretations of cases the report leaves open

1. **Assessment maximum** is computed over the items actually delivered in the session (a learner placed at L3 has a maximum of 12, not 36).
2. **One unresolved error** at a rung (second chance also wrong): Safety Net + teacher note; R3 is not satisfied, so no climb; the session ends at that rung.
3. **Two unresolved errors** at a rung: step down one rung (R3). At L1: end with Safety Net and teacher notes.
4. **Returning to a rung whose items were already delivered** (after a step-down and recovery): the session ends with a teacher note instead of repeating items.
5. **Transfer on a concept never assessed** (learner placed at L3): treated as that concept's first assessment (Learning → Provisional/Fragile) and flagged.
6. **A correct answer on a concept that is already Fragile** (different item, same concept): no state change; only the second chance can move Fragile → Repaired.

## 8. Timing definitions

`T_build = T_preprocessing + T_model_generation + T_validation_and_templates`, measured per run.
Model loading is not inside T_build (reported as model load and cold start). TTFT and token counts
come from the runner's `Stats`; if a backend does not report them they are `null`.


## Teach · Learn · Improve modules (report Section 7)

| Module | File | Role |
|---|---|---|
| TEACH | `lesson_pack.py` | signed lesson pack; teacher review (approve / edit through the gate / template); deterministic replay without a model |
| TEACH | `formula_engine.py` (`FORMULAS`, `QUANTITY_ALIASES`, `_FORMULA_PATTERNS`) | speed, density, pressure, resistance, power; error models for every formula |
| LEARN | `source_tags.py` | [S3] tags on L1/L2 sentences at display time (numbers → formula → relationship → rarity-weighted overlap) |
| LEARN | `adaptive_router.Session.on_event` | live display of explanations, repairs and routing in interactive mode |
| IMPROVE | `learner_memory.py` | session timeline, pseudonymous profile, error families, recurring patterns, prerequisite hints |
| IMPROVE | `profile_bundle.py` | SHA-256 bundles, consent check, idempotent merge on the hub |
| IMPROVE | `cbs_portal.py` | static offline HTML: credit table, heatmap, concept states, reteach suggestions |
