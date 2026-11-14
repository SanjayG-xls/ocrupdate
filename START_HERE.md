# Level Bridge STEM - Raspberry Pi 5 Tesseract handoff

Send this entire folder to the Raspberry Pi by USB or SCP.

1. Give the other AI **PROMPT_FOR_OTHER_AI.md**.
2. Tell it the location of your existing working Pi project and Python environment.
3. Follow **PI_SETUP_AND_DEMO.md**. Prefer integration into the existing working
   project; do not overwrite it wholesale with this reference copy.

## Included

- `project/`: complete tracked project source, configuration, requirements, tests,
  scripts, documentation and report from GitHub commit
  `7c3d400f2110647276e31d7dc318ef9bef2bc952`.
- The configured Qwen `.pte` and `tokenizer.json`, copied byte-for-byte into
  `project/models/`. **Keep your already working Pi model unless verified otherwise.**
- `verify_handoff.py`: dependency-free integrity check.
- JSON manifests recording source, copied artifacts and protected backend hashes.
- `evidence/`: latest executed PC test result and Tesseract-only smoke result.

The transfer copy has one intentional Pi setting change: `ocr.camera_index` is
`null` for auto-detection. Your working PC folder was not changed.

Current decision: **Tesseract only. Equation recognition stays disabled.** UI layout
can change; OCR processing and the established model/learning runtime must not.
Earlier math experiment files are historical/inactive, not Pi install requirements.

## Not included

Windows virtual environments, Git metadata, private learner profiles, captured
photos, generated packs/USB profiles, runtime logs, credentials, disabled math-model
weights and `arm_int8_backup.pte`. The backup remains preserved on the PC.

Normal text OCR requires system Tesseract and English language data; Python
dependencies alone do not supply the OCR executable. Windows model loading was
not verified. Read the prompt's model limitations before using bundled artifacts.

GitHub source: https://github.com/SanjayG-xls/namma-ai-
