# Level Bridge STEM – run evidence `e2e_20261105_081453`

## Device and software

| Item | Value |
|---|---|
| Device | not measured |
| Architecture | x86_64 |
| RAM (MB) | 8022 |
| Python | 3.13.18 |
| ExecuTorch | 1.4.0 |
| torch | 2.15.0 |
| transformers | 4.57.1 |
| TextLLMRunner importable | True |
| Inference backend | executorch_runner |
| Model file (MB) | 66.2 |
| Model sha256 | 266fc9655ff51ba79db8081b5ece68683807a8ca668dbdd374d6c9abd4fd6d50 |

## Performance (median of measured runs after warm-up)

Warm-up runs: 1 · measured runs: 5

| Metric | Value |
|---|---|
| Cold start (process start → model loaded) | 5.32 s |
| Model load | 5.263 s |
| T_build (passage → validated explanations + items) | 2.015 s |
|   of which preprocessing | 0.0009 s |
|   of which model generation | 2.009 s |
|   of which validation + templates | 0.0046 s |
| Time to first token (first call) | 5 ms |
| Generated tokens per build | 1493 |
| Decode throughput | 743.2 tokens/s |
| CPU utilisation, system (all cores = 100 %) | 83 % |
| CPU utilisation, process (per core = 100 %) | 163.7 % |
| Peak memory (RSS) | 932.3 MB |
| Repair latency, median | 0.017 ms |
| Repair latency, max | 0.017 ms |
| CPU temperature, first measured run | not measured |
| CPU temperature, end | not measured |
| Throttle flags (vcgencmd) | not measured |

## LLM use and validation

* Explanation sources (session): `{'summary': 'template', 'l1': 'template', 'l2': 'template', 'l3': 'original'}`
* LLM outputs accepted after validation (session): 0
* Accepted per benchmark run: [0, 0, 0, 0, 0]
* Raw inference runs ok: [True, True, True]  (`python -m level_bridge.main infer --repeat 3`)

## Offline operation

* offline = not measured, backend local = not measured  → run `bash scripts/test_offline_mode.sh` at the Pi console

## Learning session

| Item | Value |
|---|---|
| Placement | 1/3 |
| Path | ['L1', 'L2', 'L3'] |
| End | bridge check completed |
| Assessment credits | 25 / 36 |
| Recovery credits (outside maximum) | 3 |
| Total earned | 28 |
| CBM | +6 / 18 |

| Concept | State | Flags |
|---|---|---|
| C1 speed | Provisional | – |
| C2 odometer | Provisional | low certainty on Q3: reread S10 |
| C3 speed = distance ÷ time | Transferred | – |
| C4 same time, greater distance -> higher speed | Provisional | – |
| C5 same distance, less time -> faster | not assessed | – |
| C6 speedometer | not assessed | – |
| C7 motion | not assessed | – |
| C8 we usually talk about average speed (because: Most vehicles do not move at a constant speed; they speed up and slow down along the way) | not assessed | – |

## Automated tests

`121 passed, 10 skipped, 1 warning in 8.74s`

## Evidence files in this folder

* `benchmark.txt`
* `benchmark_e2e_20261105_081453.csv`
* `benchmark_e2e_20261105_081453.json`
* `benchmark_e2e_20261105_081453.jsonl`
* `demo_e2e_20261105_081453.jsonl`
* `environment.txt`
* `environment_report.json`
* `errors.log`
* `inference.txt`
* `inference_20261105_081508.json`
* `junit.xml`
* `knowledge_map_e2e_20261105_081453.json`
* `learning_report_e2e_20261105_081453.json`
* `model_check.json`
* `model_check.txt`
* `report_metrics.json`
* `session_events_e2e_20261105_081453.json`
* `session_transcript_e2e_20261105_081453.txt`
* `terminal.txt`
* `test_summary.txt`

## Not yet measured

`device_model`, `cpu_temp_start_c`, `cpu_temp_end_c`, `throttled`, `offline`, `offline_backend_local`
