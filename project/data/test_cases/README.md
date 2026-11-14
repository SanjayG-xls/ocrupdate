# Scripted learners

Answers are written by **intent** (`correct`, `error:<code>`, `text:<option>`, or a numeric `value`),
never by option letter, because option order is generated. Run any of them:

```bash
PYTHONPATH=src python -m level_bridge.main demo --answers data/test_cases/<file>.json            # Pi, real model
PYTHONPATH=src python -m level_bridge.main demo --backend template --answers data/test_cases/<file>.json  # no model
```

| File | Path | Purpose |
|---|---|---|
| priya_answers.json | L1 → L2 → L3 → bridge | report §4 demo: 540 repair, 25/36, +3, 28, CBM +6/18 |
| strong_reader_answers.json | L3 → bridge | placement 3/3 |
| repair_failure_answers.json | L1 (ends) | Safety Net + teacher note |
| step_down_answers.json | L2 → L1 → L2 (ends) | R3 step-down |
