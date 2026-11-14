# OCR software verification — Windows, 14 November 2026

Follow-up after PC setup: Tesseract 5.4.0.20240606 installed with `eng` and `osd`.
Actual generated printed-English image-to-text test passed. Full regression:
**202 passed, 11 skipped** (see `regression_tesseract.txt`). The initial evidence
below is retained unchanged; it predates installation. Real Qwen inference and
Raspberry Pi hardware acceptance remain pending.

These are laptop results, not Raspberry Pi measurements.

| Check | Executed result |
|---|---|
| Baseline `python -m pytest -q` | 173 passed, 10 skipped |
| Final regression | 201 passed, 11 skipped |
| Software failures | 0 |
| Hardware tests | 0 run, 5 skipped (4 original Pi, 1 new webcam/OCR) |
| ExecuTorch integration tests | 0 run, 6 skipped |
| Existing Windows product demo | exit 0; template packs/review, five sessions, profiles, USB import, CBS |
| Optional OCR dependency install | succeeded; `pip check`: no broken requirements |
| Real HTTP loopback smoke | home and JavaScript HTTP 200 |
| Actual Tesseract conversion | not run; executable unavailable |
| Actual camera | not run; no Pi/USB hardware acceptance |
| Real Qwen load/inference | not run; ExecuTorch unavailable |

Files are captured command output, except this explanatory index. `local_audit.json`
contains read-only hashes of all three preserved model/tokenizer artifacts. It does
not certify their provenance or compatibility. Tests use generated images and mock
OCR/camera interfaces; they are not image-to-text accuracy benchmarks.

Reproduce software checks from the project root on Windows:

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m pip check
.\.venv\Scripts\python scripts/verify_ocr.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows_demo.ps1 -NoReset -NoOpen -SkipTests
```

The demo writes the project's standard demonstration lesson packs and pseudonymous
profiles. `-NoReset` skips deletion of existing stores; the original default demo
still resets those demo stores. For Pi setup, pending hardware checks and the
human-review demo, see [OCR.md](../../OCR.md).
