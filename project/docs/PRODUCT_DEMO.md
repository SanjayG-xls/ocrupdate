# Teach · Learn · Improve – live-round runbook (14 Nov 2026)

For the new webcam/upload → OCR → human verification → lesson build → teacher
approval demonstration, follow [the OCR runbook](OCR.md). Real Pi camera, Tesseract
and Qwen acceptance is pending; Windows software tests and template demos are
documented separately there. On Windows, the existing demo accepts `-NoReset
-NoOpen -SkipTests` for a non-resetting scripted run after regression tests.

Report Section 7. One Raspberry Pi plays both roles in the demo: the **teacher hub** (builds and reviews lesson
packs with the LLM, imports profiles, shows the CBS portal) and the **student device** (model-free session).

## 0. What is verified and what is not

| Item | Status |
|---|---|
| `gate-report` and `compare` demo commands | Implemented; tests with a scripted model. **Real-model output not yet seen** – run on the Pi first |
| Formula library: speed, density, pressure, resistance (Ohm's law), power; 5 phrasings of a formula sentence | Implemented; automated tests |
| Practice passages: `data/passages/{speed,density,pressure,ohms_law,power}_passage.txt` | All extract formula, worked example and 2 relationships; templates pass the gate (tests) |
| Lesson packs, teacher review, model-free replay | Implemented; tests (replay reproduces Priya 25/36, CBM +6/18) |
| Source tags [S3] on L1/L2 lines (display only) | Implemented; tests |
| Learner memory, recurring patterns, USB bundles (SHA-256, consent), hub import, CBS portal | Implemented; tests (tamper rejected, re-import adds nothing) |
| Question-rewording check (statements / answer leaks rejected) | Implemented; regression tests with the 3 bad rewordings from the Pi 500 log |
| Any of the above measured on a Raspberry Pi 5 | **Pending** – run section 2 on the board |
| Real students or teachers | **None** – all learners are scripted files |

Never say "it works on any passage". Say: **"it works on passages that state one of the five library formulas,
and on definition and cause-effect sentences; we showed five practice passages, and we add a formula with one
library entry."**

## 1. Before you leave (laptop)

```bash
bash scripts/run_all_tests.sh                       # expect: 173 passed, 10 skipped + no-model demo
bash scripts/run_product_demo.sh --backend template # whole Teach -> Learn -> Improve flow, no model
```

## 2. On the Raspberry Pi 5 (first 45 minutes – baseline before any change)

```bash
bash scripts/verify_environment.sh
python -m level_bridge.main check-model
bash scripts/run_end_to_end.sh                      # PoC benchmark: label every number "Raspberry Pi 5"
bash scripts/run_product_demo.sh                    # pack build now uses the LLM (configured backend)
```

Report Pi 5 numbers **next to** the Pi 500 numbers (report Section 5.2), never merged.

## 3. When the organiser passage arrives

```bash
cp organiser.txt data/passages/organiser_passage.txt
python -m level_bridge.main process --passage data/passages/organiser_passage.txt
```

Check the output line by line:

* `Knowledge map core types` – is a formula found? If not, and the passage states a ratio formula that is not in
  the library, add one entry to `FORMULAS` (`formula_engine.py`), its units (`quantity_parser.py`), three
  contexts in `config/item_contexts.yaml` and, optionally, wording in `_PHRASING` (`question_generator.py`).
  Run `pytest -q` after the change.
* No formula at all (e.g. biology)? The loop still runs on definition and cause-effect items. Say so plainly.

Then build the lesson pack with the LLM and review it as the teacher would:

```bash
python -m level_bridge.main pack-build  --passage data/passages/organiser_passage.txt --out data/packs/organiser.lbpack.json
python -m level_bridge.main pack-review --pack data/packs/organiser.lbpack.json        # [a]pprove [e]dit [t]emplate
python -m level_bridge.main session --pack data/packs/organiser.lbpack.json --learner STU-DEMO1 --consent   # interactive
```

If LLM question rewording misbehaves on the day: `questions.llm_stem_rewording: false` in `config/config.yaml`.

## 4. Demo story (about 6 minutes) - three moments the judges can see

Prepare on the Pi before judging (so nothing waits on screen):
```bash
python -m level_bridge.main pack-build --passage data/passages/organiser_passage.txt --out data/packs/organiser.lbpack.json
python -m level_bridge.main compare   --passage data/passages/organiser_passage.txt > outputs/compare_live.txt
```
Run `compare` once beforehand and read the result. If the model gets everything right, say so honestly:
"right this time - but nothing guarantees it; ours is computed".

1. **Offline** - turn Wi-Fi off on screen: "everything from now on is offline".
2. **Their passage** - `process`: the formula, terms and relationships Python extracted.
3. **Moment 1 - AI alone vs Level Bridge** - `compare` (or `cat outputs/compare_live.txt`):
   the same Qwen model answering on its own, next to Python-computed answers with units, and its raw
   summary failing our gate checks.
4. **Moment 2 - the gate catching the AI** - `gate-report`: each model draft, ACCEPTED or REJECTED, with
   the exact reasons in red. Then `pack-review`: the teacher approves; an edit that drops the formula is refused.
5. **Moment 3 - a judge plays the student** - `session --pack data/packs/organiser.lbpack.json --learner STU-JUDGE --consent`.
   Ask the judge to answer one question wrong on purpose: the system names the mistake, explains it through
   the units, gives a second chance, and finishes on the original sentences.
6. **IMPROVE** - export the judge's profile to USB, `hub-import` (show a tampered bundle being rejected),
   `portal`: the judge appears in the class table next to the scripted class.
7. **Evidence** - Raspberry Pi 5 numbers measured today; one honest line: "not yet tested with real classrooms".

Pitch line: *"The model writes; Python decides. The AI runs once per lesson on the teacher's Pi; the student's
device needs no model and no internet; her record travels by USB under a pseudonymous ID."*

## 5. Likely judge questions

| Question | Answer |
|---|---|
| Does it work on our passage? | Show `process` output live. Library formulas + definition + cause-effect are supported; anything else is listed as unsupported, not guessed. |
| How much is AI? | Summary and wording come from the model when they pass the gate; L1/L2 fell back to templates on the Pi 500. Teacher review makes every draft checkable. Python computes every answer. |
| Why should we trust a 0.5B model? | It never decides correctness. Validation gate + teacher approval + source tags back to the textbook sentence. |
| Isn't learner data sensitive? | Pseudonymous IDs, names rejected by the CLI, consent flag required for export, SHA-256 integrity, nothing on a network (DPDP Act 2023, Section 9). |
| Is the pattern detection proven to help? | No. It reports observed behaviour; learning impact needs a classroom study. |
| Pi 5 vs Pi 500? | Same SoC (BCM2712); report both, labelled. |
