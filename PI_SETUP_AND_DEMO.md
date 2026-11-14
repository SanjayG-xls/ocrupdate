# Transfer, integrate and run

## 1. Transfer

Copy the entire `Level_Bridge_RPi5_Tesseract_Handoff_2026-11-14` folder to your USB
drive, then onto the Pi. Alternatively, from a PC terminal with OpenSSH installed:

```powershell
scp -r "$env:USERPROFILE\Desktop\Level_Bridge_RPi5_Tesseract_Handoff_2026-11-14" <pi-user>@<pi-host>:~/
```

Replace the angle-bracket placeholders with your actual Pi username/hostname.
This copies to a separate handoff directory, not over the working project.

On the Pi:

```bash
cd ~/Level_Bridge_RPi5_Tesseract_Handoff_2026-11-14
python3 verify_handoff.py
```

## 2. Preserve the working Pi first

Have the other AI inspect and back up the existing Pi source/configuration and
record the current Python/model environment. Use the supplied prompt. Do not copy
the reference project's files over a working installation blindly. In particular,
preserve the Pi's model configuration, artifacts and runtime-specific fixes.

The bundled model is a transfer copy, not a certified replacement. Existing `.pte`
files, including any Pi backup, must not be overwritten or re-exported. The
bundle has no Windows virtual environment to run on ARM.

## 3. System and optional OCR packages

On 64-bit Raspberry Pi OS, after the other AI merges the OCR integration into the
working project, activate that project's **existing working** Python environment:

```bash
cd /path/to/existing/level_bridge_stem
source /path/to/existing/venv/bin/activate
python -m pip freeze > before_ocr_environment.txt
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd v4l-utils libglib2.0-0
python -m pip install --dry-run --report ocr_install_plan.json -r requirements-ocr.txt
```

Inspect the proposed changes first. It must not replace executorch, torch,
torchao, transformers or the working model's tokenizer/runtime packages. Check
NumPy changes against the existing environment too. Resolve a conflict before
installing; do not repair it by upgrading the model stack.

When compatible:

```bash
python -m pip install -r requirements-ocr.txt
python -m pip check
tesseract --version
tesseract --list-langs
v4l2-ctl --list-devices
export PYTHONPATH="$PWD/src"
python -m level_bridge.main ocr-ui
```

The required Python OCR packages are Flask 3.1.2, OpenCV headless 4.12.0.88,
pytesseract 0.3.13 and Pillow 11.3.0. OS Tesseract packaging/version may differ from
Windows; verify behavior on the actual Pi. Do not install `requirements-math-ocr.txt`.

Internet is only needed for package setup. Download matching ARM/Python wheels
and OS packages in advance if the Pi must be installed offline. Runtime reads
local executable/language data/model files and has no cloud dependency.

## 4. UI and capture

Open in the Pi's browser:

- `http://127.0.0.1:5000/read`: simple Tesseract image-to-editable-text reader.
- `http://127.0.0.1:5000/`: webcam capture, passage verification and lesson flow.
- `/math`: compatibility alias for the simple text reader, NOT math recognition.

The handoff camera setting is null (first usable V4L2 device). Select a concrete
`/dev/video*` node if required. Capture requests 1080p and uses a 1.5-second warm-up;
it releases preview before reopening for a still photo. Upload is independent.

Stay on loopback for the demonstration. LAN use requires explicit `--allow-lan`
and a matching hostname/IP in `ocr.trusted_hosts`; do not expose it publicly.

## 5. Acceptance and final demo

```bash
python -m pytest -q
LB_OCR_HARDWARE=1 python -m pytest -q tests/hardware/test_webcam_capture.py
python -m level_bridge.main check-model
python -m level_bridge.main infer --max-new-tokens 48
```

Point the webcam at a clear printed English paragraph for the hardware OCR test.
These are checks to run on the Pi, not results already achieved in this handoff.
Keep the working model's own existing configuration for the model commands.

Demonstrate:

1. Upload a clear JPG/PNG; Tesseract returns editable text with no math-model load.
2. Preview and capture from the USB webcam. Compare with upload behavior.
3. In `/`, correct OCR and select a 50-450 word passage with at least two sentences
   (target 150-300). Verify and explicitly confirm it.
4. Prepare a lesson with the existing real Qwen/ExecuTorch backend. Confirm actual
   inference status; template mode is only a clearly labeled fallback/demo.
5. Copy the **actual generated pack filename** from the UI into:

```bash
python -m level_bridge.main pack-review --pack "/actual/generated/file.lbpack.json"
python -m level_bridge.main session --pack "/actual/generated/file.lbpack.json"
```

Teacher approval must happen before the student session. Then demonstrate existing
CBM, report, learner memory and CBS behavior. Disconnect internet and repeat the
local workflow. Record OCR and model timings separately, labeled Raspberry Pi 5.

## Integrity and what the other AI may edit

`verify_handoff.py` checks bundled models and protected reference code. It does not
load a model or certify runtime compatibility. Backend files and scientific
learning logic are protected. UI assets and UI routing can be adjusted while
preserving API contracts, security, storage and human approval. Camera/device/path
binding is the only expected deployment-specific OCR configuration change.
