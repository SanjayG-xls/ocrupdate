# Demo script (5–7 minutes)

**Setup before judges arrive (10 min):** Pi 5 on mains power with cooler, keyboard + monitor
(no SSH needed), project in `~/level_bridge_stem`, venv active, model verified:

```bash
cd ~/level_bridge_stem && source .venv/bin/activate
bash scripts/verify_model.sh                       # must print load ok
python -m level_bridge.main infer --repeat 1       # warms the page cache
clear
```

Have a second terminal open on `outputs/` and the folder `outputs/e2e_<latest>/` from a full
rehearsal run ready (fallback evidence).

## Live vs recorded – say it explicitly

| Shown | Status |
|---|---|
| Network off, offline check | **live** |
| Model load + summary/L1/L2 generation on the Pi | **live** (timings appear on screen) |
| Learning session (Priya answers) | **live**, answers typed by presenter or scripted file |
| 5-run benchmark medians | **recorded** – `outputs/e2e_<time>/benchmark_*.json` from rehearsal (a benchmark takes several minutes) |
| Automated test suite | **recorded** – `test_summary.txt` (rerun live only if time allows: ~5 s) |

## Timeline

| Time | Action | Command / what to say |
|---|---|---|
| 0:00–0:40 | Problem | "Students can read a passage but not explain it. Level Bridge gives explanation support at three levels and checks understanding – fully offline on a low-cost Raspberry Pi 5." |
| 0:40–1:20 | Prove offline | `sudo nmcli networking off` then `python -m level_bridge.main offline-check --require-offline` → point at `"offline": true`, `"backend_is_local": true` |
| 1:20–2:30 | Build on device | `python -m level_bridge.main build` → point at: backend `executorch_runner`, each explanation's `source` (llm / llm_retry / template) and `validated`, T_build breakdown. "The model writes wording only; Python checks every term, number, unit and the formula." |
| 2:30–5:00 | Session | `python -m level_bridge.main demo --answers data/test_cases/priya_answers.json` (or interactive: omit `--answers` and answer by meaning as listed in that file – option letters are generated, so read the options on screen). Narrate: placement 1/3 → L1; **Q2 = 540** → *wrong operation*, "540 km·h is not a speed", repair from S3; second chance cyclist 12 ✓ → Repaired (+3 recovery, outside maximum); L2; L3 original text; bridge with S3–S4 verbatim, Meena 4 km/h ✓ → Transferred. |
| 5:00–5:40 | Report | Final block: "Assessment 25 / 36 · Recovery +3 · Total 28 · CBM +6 / 18 – all computed from the answers." Show `learning_report_*.json` concept states. |
| 5:40–6:30 | Evidence | open recorded `benchmark_*.json` (medians, TTFT, tokens/s, peak RSS, temperature, throttle flags) and `test_summary.txt` |
| 6:30–7:00 | Close | `sudo nmcli networking on`. Honest limits: rule-based extraction for short textbook passages; Consolidated state is proposed, not implemented. |

## Fallback plan

| Problem during demo | Fallback |
|---|---|
| Model fails to load | Say so. Show the recorded `outputs/e2e_<time>/terminal.txt` from rehearsal (real model). Then run live `python -m level_bridge.main demo --backend template --answers data/test_cases/priya_answers.json` and state clearly: **"this run uses templates, no LLM"** – the banner and report say `LLM inference: NO`. |
| Generation slow / timeout | Continue: the generator falls back to validated templates and labels them; show the recorded LLM run for wording. |
| LLM output rejected by the validator | Use it as a feature: open `outputs/stage4_explanations.json` and show the named failed check (e.g. `unit_consistency`). |
| Monitor/keyboard issue | Present from the recorded artefacts on a laptop; nothing recorded is presented as live. |
| Network cannot be disabled | Skip the offline claim live; show the recorded `outputs/offline_*_check.txt` from `scripts/test_offline_mode.sh`. |

Never present a template run, a scripted test double or a laptop run as on-device LLM inference.
