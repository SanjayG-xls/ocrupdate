# Offline textbook scanning

**Current mode:** the simple reader at `/read` (also available at the old `/math`
URL) now uses Tesseract only. Equation recognition is disabled at the user's request.
No pix2tex, learned formula model or LaTeX renderer is loaded by the reader.
Choose a photo, press **Read text**, correct/copy the extracted text, or delete the
saved scan. Webcam capture remains available through the existing Scan Concept page.
The newspaper photo from the reported failure produced 228 words in about 2.3 seconds
on the Windows PC. This is a processing-time observation, not an accuracy guarantee.
The separate equation experiment environment is not required for this workflow.

**PC follow-up:** Tesseract 5.4.0.20240606 has since been installed through winget
(`UB-Mannheim.TesseractOCR`) under the user's local Programs folder, with `eng`
and `osd` data. Windows install folders are detected when PATH omits Tesseract;
`ocr.tesseract_cmd` can also select an explicit executable. An actual synthetic
printed-English OCR test passed. Latest regression: **202 passed, 11 skipped**.
The original audit below records the environment before this installation;
Pi acceptance and Qwen inference are still pending. This PC currently selects
`ocr.camera_index: 1` for its external USB camera; reset to null on the Pi.

Implemented for Level Bridge STEM v0.2.4. OCR is optional preprocessing; the learning
engine, CBM, R1–R4, learner memory, CBS and ExecuTorch adapter are unchanged.

## Install on Raspberry Pi OS (64 bit)

Use the **existing working model virtual environment**. Do not reinstall or upgrade
torch, torchao, transformers or ExecuTorch to add OCR.

```bash
cd ~/level_bridge_stem
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng v4l-utils libglib2.0-0
source .venv/bin/activate
python -m pip install -r requirements-ocr.txt
python -m pip check
tesseract --version
tesseract --list-langs
export PYTHONPATH="$PWD/src"
python -m level_bridge.main ocr-ui
```

If no environment exists, create one with `python3 -m venv .venv` and install core
`requirements.txt` first. OCR dependencies do not install a model runtime. Keep the
project's existing Pi runtime installation procedure and ExecuTorch 1.4.0 pin.
OpenCV here is headless: preview is served through the local browser.

Open **http://127.0.0.1:5000** in the Pi browser. Set `ocr.enabled: false` in
`config/config.yaml` to disable the feature. No optional OCR imports are made by
the ordinary process/build/session commands.

Raspberry Pi OS requires a virtual environment for pip-managed packages; see the
[official OS documentation](https://www.raspberrypi.com/documentation/computers/os.html).
These installation commands are provided for Pi acceptance, not claimed as executed
on a Pi in this change.

For offline setup, prepare an architecture/Python-matched wheelhouse on a connected
Pi using `python -m pip download -r requirements-ocr.txt -d wheelhouse`, copy it by USB,
then `python -m pip install --no-index --find-links wheelhouse -r requirements-ocr.txt`.
Install Tesseract and its English language package beforehand, or provide the OS
packages and their dependencies through a local apt mirror. Runtime does not
download language data, models, fonts or JavaScript.

## Demonstration: capture → review → lesson → student

1. Start `python -m level_bridge.main ocr-ui`. Choose **Start webcam preview**.
   The Pi backend opens a USB camera; the browser does not use getUserMedia.
2. Place a clear English textbook paragraph under the camera and press **Capture
   Image**. Alternatively, use **Upload Image** with a local JPG/PNG, with or
   without a camera. Preview stops before capture to release the camera.
3. Compare the original photograph and editable passage. Zoom the original;
   review highlighted uncertain words, numbers, units and formula candidates.
   Choose 150–300 words when possible; hard limits are 50–450 words and at least
   two sentences. Full pages are never silently truncated.
4. Edit mistakes, choose **Verify Passage**, read the corrected text, select
   **I have verified…**, then **Confirm verified passage**. Invalid text cannot
   be confirmed. Any edit resets confirmation in the browser and stored record.
5. Choose **Prepare AI Lesson**. The configured ExecuTorch backend is used, with
   no silent template-only model-load fallback. An explicit **Template
   demonstration** checkbox is available for no-model demonstrations.
6. The screen displays backend, actual successful generation status, accepted
   explanations, rejected attempts, template fallbacks, timing breakdown,
   generated explanation drafts and the unique pack path. No lesson is approved
   by OCR confirmation. Review the generated explanations with the existing CLI.

The UI prints commands with the **actual generated absolute pack filename**:

```bash
python -m level_bridge.main pack-review --pack "/actual/generated/ocr_ID_UUID.lbpack.json"
python -m level_bridge.main session --pack "/actual/generated/ocr_ID_UUID.lbpack.json"
```

Use interactive `pack-review` for teacher inspection, edits or template replacement.
`--approve-all` is for a scripted demonstration after reviewing the content.
Student sessions refuse pending packs containing the new `ocr_verification`
provenance marker. Historical non-OCR packs retain their existing warning behavior.
Learning remains model-free after approval. Existing session flags `--learner`,
`--consent`, `--answers`, profile export/import and `portal` work unchanged.

The saved UTF-8 passage path is also displayed; it can be used directly with the
existing `process --passage PATH` and `pack-build --passage PATH --out PACK` commands.
Those general-purpose CLI commands retain their historical behavior. To retain the
OCR provenance marker and enforce teacher approval automatically, build in the OCR UI.

## Capture, storage and privacy

`ocr.camera_index: null` probes `/dev/video*` for a usable capture device on Linux;
Capture discards startup frames for `ocr.camera_warmup_s` (default 1.5 seconds)
after reopening the device, allowing automatic exposure to settle. Preview stops
before capture to avoid competing camera handles. OCR filters affect only analysis
candidates, never the saved original or the webcam's hardware image settings.
select `/dev/video0` (or an integer index) explicitly if needed. Capture requests
1920×1080, using whatever resolution the camera actually provides. Errors explain
connection, permissions and busy-camera causes. Upload remains independent.

```text
data/ocr/captures/UUID.png                  original, unchanged bytes
data/ocr/processed/UUID.json                OCR words, layout, candidates, review/build record
data/ocr/reviewed/UUID_REVISION_UUID.txt     immutable reviewed UTF-8 passage revision
data/packs/ocr_UUID_BUILD_UUID.lbpack.json  pending teacher approval
```

Every capture, confirmation and build has a unique name. The delete button removes
the source capture and intermediate OCR JSON, preserving reviewed passages and packs.
Reviewed passages/packs can be removed manually through the OS when no longer needed.
These local data folders are excluded from version control. No identity fields or
automatic third-party transmissions were added.

The web layer checks file extension, JPEG/PNG signature/decoder, byte size, pixel
dimensions and minimum dimensions. It discards uploaded filenames in favor of UUIDs;
image serving is limited to that scan's capture folder. CSRF tokens, same-site cookies,
trusted Host checking, no-store headers, CSP and escaped text rendering protect the UI.
Text is never executed as a shell command. Model control tokens are refused, and the
system prompt treats passage text as data rather than instructions.

Loopback is the default. For **explicit trusted LAN use**, add the Pi hostname/IP to
`ocr.trusted_hosts`, then run:

```bash
python -m level_bridge.main ocr-ui --host 0.0.0.0 --allow-lan
```

This is a local demonstration server without accounts or TLS. Keep LAN mode on a
trusted isolated network; other devices on it can operate the teacher tools.
Default Host restriction follows [Flask's security guidance](https://flask.palletsprojects.com/en/stable/web-security/).

## OCR behavior and limits

The processor preserves original bytes and compares grayscale, CLAHE contrast,
denoised Otsu threshold and, when detected, small-angle deskew candidates using
confidence plus text coverage. Reliable Tesseract OSD orientation is used; sparse
paragraphs may not supply reliable orientation. Rotate the source before upload if
needed. This heuristic is not guaranteed to select the correct scientific text.

Words retain Tesseract confidence, bounding boxes, paragraph/line IDs and text offsets.
Reading order follows Tesseract page/block/paragraph/line order. Bounding boxes refer
to the selected preprocessing candidate; the UI deliberately does not draw those
coordinates on an untransformed original image. An overlay/crop editor is not included.

The error detector reuses the existing formula and unit registries. It flags formula
symbols/fractions, all detected numbers, known units, unfamiliar number-adjacent units,
malformed slash strings, and simple explicit ratio formulas that conflict with the
five supported relationships. It never silently corrects text. Unsupported notation
requires human review. This is not a general equation solver or semantic validator.
Handwriting, diagrams, complex mathematics and chemical notation are outside scope.

If Tesseract is missing, the photo remains available with a visible error. Install
Tesseract, then run OCR again, or carefully transcribe and review the photographed
passage manually. That manual path is not claimed as successful OCR.

## Troubleshooting and Pi acceptance

* Check `v4l2-ctl --list-devices` and `ls -l /dev/video*`. Select a capture node,
  close other camera apps and ensure the current user has video-device permission.
* If 1080p is unsupported, the driver supplies a supported mode; inspect with
  `v4l2-ctl --list-formats-ext`. Improve focus and lighting before increasing resolution.
* Check `tesseract --list-langs` contains `eng`. The executable must be on the
  process PATH; pytesseract alone does not include the OCR engine.
* Missing model is an explicit build error. Use the labeled template checkbox for
  software demonstration; it does not verify real inference.

```bash
python -m pytest -q
LB_OCR_HARDWARE=1 python -m pytest -q tests/hardware/test_webcam_capture.py
python -m level_bridge.main check-model
python -m level_bridge.main infer --max-new-tokens 48
LB_HARDWARE=1 python -m pytest -q tests/hardware/test_pi_hardware.py
bash scripts/run_product_demo.sh --backend template
```

On the Pi, complete a photographed-text browser round trip, real Qwen lesson build,
interactive teacher review and model-free student session. Disconnect internet and
repeat. Record OCR `ocr_duration_s` separately from model `t_model_generation_s`
and lesson `t_build_s`. Browser visual inspection, USB capture, actual OCR, model
loading, inference and disconnected operation remain hardware acceptance checks.

## Implementation and executed evidence (Windows laptop, 14 November 2026)

* Original baseline: **173 passed, 10 skipped**.
* Final software regression: see `docs/evidence/ocr_windows/regression.txt`.
* Optional OCR Python dependencies installed in `.venv`; `pip check` found no broken
  requirements. No torch/ExecuTorch installation or upgrade was attempted.
* Tests generate small reproducible images and mock Tesseract/camera hardware. They
  exercise decoding, poor light/blur indicators, reliable orientation, candidate
  selection, empty extraction, executable failure, formulas/units, layout, both
  review gates, disk tampering, upload limits, CSRF/Host protection and lesson replay.
* The existing Windows product demo completed with `-NoReset -NoOpen -SkipTests`;
  this preserves existing data and avoids opening a browser. Template sessions,
  CBM, repair, learner memory, USB profile import and CBS remained operational.
* A real loopback HTTP server served the page and local JavaScript with HTTP 200.
  The browser itself was not available for visual/manual interaction testing.
* **Tesseract executable and ExecuTorch are unavailable here.** No actual image-to-text
  conversion, webcam capture, model load or real Qwen inference is claimed.

Model files found, preserved and hashed (full hashes in `local_audit.json`):

| File | Bytes | Status |
|---|---:|---|
| `models/Qwen2.5-0.5B-Instruct-8da4w-gptq-2k.pte` | 417495296 | configured intended artifact; load failed because ExecuTorch is absent |
| `models/arm_int8_backup.pte` | 769370752 | preserved; not selected or loaded |
| `models/tokenizer.json` | 7031645 | found and preserved; runtime compatibility unverified |

The intended artifact is selected by its descriptive name and existing Qwen project
configuration. Its provenance/quantisation, tokenizer pairing, export version and
actual context capacity **could not be independently confirmed** from available
export records or runtime. The previous 1024 context value came from the project's
export recipe, not this imported artifact; it is now null rather than guessing 2048
from `2k` in the filename. No `.pte` was renamed, modified, quantized or exported.
Use the pinned 1.4.0 runtime on the Pi to establish compatibility and context behavior.

New files: `src/level_bridge/ocr/` (camera, decoding/preprocessing, quality, extraction,
verification, review service, Flask routes and local assets), `requirements-ocr.txt`,
`scripts/verify_ocr.py`, OCR unit/integration/hardware tests, this guide and evidence.
Modified: app/model YAML, `main.py` (optional command and OCR-pack approval guard),
`lesson_pack.py` (OCR-pack approval enforced on replay),
`pyproject.toml` (optional dependencies/assets), `.gitignore`, Windows demo switches,
README and architecture/test/demo documentation. The model adapter and learning
engine source files were not changed.
