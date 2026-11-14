# Expected outputs (reference for regression tests)

Generated with the **template backend (NO LLM inference)** on a laptop:

```bash
PYTHONPATH=src python -m level_bridge.main process
PYTHONPATH=src python -m level_bridge.main build --backend template
PYTHONPATH=src python -m level_bridge.main demo --backend template --answers data/test_cases/priya_answers.json --run-id expected_template
```

| File | Deterministic? | Notes |
|---|---|---|
| stage1_passage.json | yes | 177 words, S1–S11, sha256 of the passage |
| stage2_knowledge_map.json | yes | core types definition 4 / quantitative 4 / cause_effect 1 |
| stage3_key_term_registry.json | yes | 7 required terms |
| stage4_explanations_TEMPLATE.json | yes (template) | `source: template` – these are NOT model outputs |
| stage5_item_bank_TEMPLATE.json | yes (template stems) | with the LLM, stems may be reworded (`stem_source: llm`) |
| priya_learning_report_TEMPLATE.json | scores/states yes; timings no | 25/36, +3, 28, CBM +6/18 |
| priya_session_transcript_TEMPLATE.txt | yes except timings | terminal rendering |

With the real model on the Pi, stages 1–3, the numeric solutions, the routing, the states
and the credit/CBM totals must be identical (they never depend on the LLM). Explanation and
stem **wording** will differ; each LLM output is accepted only if it passes validation, and the
report records which outputs came from the LLM and which fell back to templates.
