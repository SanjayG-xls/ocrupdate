# Raspberry Pi 5 integration directive - Level Bridge STEM

You are working on my existing Level Bridge STEM v0.2.4 project on Raspberry Pi 5.
Integrate the Tesseract feature supplied in this handoff into my existing working
Qwen/ExecuTorch project. Inspect the Pi and existing repository first, make a short
plan, then implement and test. Do not replace the project or stop at a plan.

## My final decisions - take precedence over historical experiment documentation

1. **OCR must use Tesseract only.** Do not install, enable or call pix2tex,
   Pix2Text, formula-recognition models, a vision-language model or cloud OCR.
2. **Do not change the supplied Tesseract processing behavior or OCR backend.**
   This task is deployment/integration, not a new OCR experiment. Do not tune,
   rewrite or replace preprocessing, orientation, candidate selection, thresholds,
   Tesseract settings, layout reconstruction, warning rules or local storage.
3. You may improve **HTML/CSS/JavaScript UI layout, screen placement, labels,
   responsiveness and usability**, provided existing request contracts and review
   gates are preserved. "Placement" means where controls appear on screen; it does
   NOT authorize changes to placement assessment, learning levels or scoring.
4. Preserve my working Qwen model, tokenizer, ExecuTorch version, XNNPACK setup,
   generation settings and existing teaching/learning/reporting behavior.
5. All normal operation must work offline. Download dependencies only during
   explicit setup. No image/text uploads, CDNs, remote fonts or remote inference.

The project contains historical, disabled math OCR code, assets and tests. Their
presence does not authorize using them. `ocr.math.enabled` is false. Do not follow
old experimental setup instructions or install `requirements-math-ocr.txt`.

## Start by inspecting these files

Read `START_HERE.md`, `PI_SETUP_AND_DEMO.md`, `HANDOFF_MANIFEST.json`,
`MODEL_MANIFEST.json`, and the handoff's `project/` directory. Then inspect the
actual Pi project, model configuration and environment before merging anything.

Relevant implementation:

- `src/level_bridge/ocr/camera.py`: backend USB webcam capture/preview and release.
- `ocr/preprocessing.py`, `quality.py`, `processor.py`: OpenCV and Tesseract pipeline.
- `ocr/verification.py`: review warnings; no scientific rewriting.
- `ocr/service.py`: UUID storage, editable text, confirmation hashes, lesson build.
- `ocr/web.py`: local Flask routes and upload/CSRF/path controls.
- `ocr/templates/reader.html`, `ocr/static/reader.js`: current simple text reader.
- `ocr/templates/scan.html`, `ocr/static/scan.js`, `scan.css`: capture and teacher flow.
- `src/level_bridge/main.py`: optional `ocr-ui` command and existing CLI integration.
- `passage_processor.py`, `pipeline.py`, `lesson_pack.py`, `concept_validator.py`:
  reuse their existing validation/build/approval behavior.
- `config/config.yaml`, `config/model_config.yaml`, `requirements-ocr.txt`.

## What has already been implemented

The text reader at `/read` uses local Tesseract through `pytesseract`. `/math` is
only a compatibility URL for the same text-only reader. It no longer runs math OCR.
`POST /upload` and the compatibility `POST /math/extract` both use the existing
`ScanService.upload` -> `processor.process_image` Tesseract path.
`POST /math/recognize` refuses equation conversion.

The simple UI shows: Choose photo -> Read text -> editable extracted text -> Copy
text / Delete scan. The existing `/` interface also supports webcam preview,
capture, upload, passage correction/confirmation and teacher lesson preparation.
The webcam is captured by the Pi backend, not solely by browser getUserMedia.

Camera behavior: first usable Linux V4L2 device by default, configurable device,
requested 1920x1080 with driver fallback, 1.5 second exposure warm-up on capture,
unique local files and proper release. Upload works without a webcam.

Image input is checked for actual JPEG/PNG format, extension, dimensions and size.
Default bounds are 12 MiB and 20 million pixels. Original bytes are retained.
OpenCV generates optional OCR candidates. Tesseract returns English text with
confidence, boxes and layout identifiers. The original and corrected text can be
compared. OCR confidence is not a probability of scientific correctness.

Storage is local:

```
data/ocr/captures/   original images
data/ocr/processed/  OCR and review JSON records
data/ocr/reviewed/   unique confirmed UTF-8 passage revisions
data/packs/          lesson packs
```

The delete operation removes captured/intermediate files, retaining previously
verified passages and lesson packs. No student identity fields were added.

## Preserve the two distinct gates

Gate A: the human compares and corrects the OCR, validates it with the existing
`passage_processor.process_text`, and explicitly confirms it. Target: 150-300
words; hard range: 50-450 words and at least two sentences. Do not truncate pages.
An edit revokes confirmation. Confirmed files are UTF-8 and are not overwritten.

Gate B: the existing Qwen/ExecuTorch lesson build, explanation validation and teacher
`pack-review` approval still apply. OCR confirmation is not teacher approval.
Pending OCR-marked packs are refused during student session/replay. Preserve
explicit template-demo labeling; do not disguise a fallback as real inference.

Do not change CBM, assessment credits, misconception repair, R1-R4 routing,
placement assessment, learner memory, USB profile transfer or the CBS portal.

## Protect the Pi's working model environment

The handoff includes these copied artifacts for transfer convenience:

```
project/models/Qwen2.5-0.5B-Instruct-8da4w-gptq-2k.pte
project/models/tokenizer.json
```

Their sizes and hashes are in `MODEL_MANIFEST.json`. Prefer the Pi's already
working artifacts/configuration. Never overwrite or replace them automatically
with the bundled copies. If using the copies, first verify compatibility explicitly.

The PC could not load Qwen because ExecuTorch was not installed there. Export
version, tokenizer pairing and real context capacity are NOT verified by the PC
tests. Do not infer context capacity from `2k` in a filename. The configuration's
`export_max_seq_length` is intentionally null. `arm_int8_backup.pte` is not bundled,
not selected, and remains unchanged on the PC.

Do not retrain, quantize, rename, edit or re-export any `.pte` or tokenizer file.
Do not upgrade/reinstall executorch, torch, torchao or transformers. Keep the
existing pinned ExecuTorch 1.4.0 environment. Preserve the Pi model's own known-good
configuration if it differs from this PC snapshot. Resolve relative model paths
against the correct project root when integrating; do not blindly copy YAML.

## Integration order

1. Back up the existing Pi source/configuration and record its current environment
   and model checks. Do not reset learner data or overwrite model files.
2. Run the Pi's existing baseline tests and model smoke check before integration.
3. Merge the OCR addition additively. Use the supplied OCR backend unchanged.
   Preserve existing Pi-specific changes in the model adapter/core. If the CLI
   differs, add only the OCR entry point and the demonstrated approval guard.
4. Install system Tesseract with English/OSD data and optional OCR dependencies.
   Review pip's dry-run first; do not let OCR setup replace model-runtime packages.
   Do not install Windows environments or experimental math dependencies.
5. Keep `ocr.enabled: true`, `ocr.math.enabled: false`, loopback binding and request
   security. The transfer copy already uses `ocr.camera_index: null` for Pi auto
   selection. Selecting the actual camera node, configuring the local executable
   path or storage location is allowed hardware/path configuration; it does not
   authorize changing OCR processing settings.
6. First test a JPG/PNG upload. Then USB preview/capture. Then corrected passage
   confirmation, real Qwen lesson build, teacher approval and a model-free session.
7. Only after that, make any desired UI/layout changes. Keep backend calls/gates.
8. Run regressions and test offline after disconnecting internet. Measure OCR time
   separately from Qwen generation. Report real Pi measurements separately from PC.

Use `PROTECTED_OCR_SHA256.json` and `verify_handoff.py` to verify the transferred
OCR/core reference files have not been modified. If preserving a different existing
Pi core revision, document the difference rather than blindly replacing it with
the handoff copy. Do not weaken/remove existing tests to obtain a pass.

## Evidence and final report

Latest executed Windows software suite: **221 passed, 11 skipped**. A real local
Tesseract upload of the newspaper photo returned **228 recognised words in about
2.3 seconds**. This is not an accuracy guarantee or a Raspberry Pi benchmark.
The no-model Teach/Learn/Improve demo passed earlier. Real Pi webcam acceptance,
Pi Qwen load/inference and disconnected Pi operation remain to be verified.

Finish with files changed, installation/run commands, executed test results, real
backend/inference status, unchanged OCR/backend checksums, and honest remaining
hardware/model limitations. Do not claim all textbook layouts or mathematics are
recognised reliably. Do not claim the integration is complete without running the
available checks. Implement the authorized integration without asking approval
between ordinary reversible stages.
