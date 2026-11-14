# Experimental equation-to-LaTeX (PC)

**Disabled at the user's request.** The active reader now uses Tesseract only at
`http://127.0.0.1:5000/read`. The `/math` link opens that same text-only interface.
Equation-recognition requests are refused. The material below is historical
documentation of the earlier experiments, not the current reading workflow.


Student UI follow-up: the default `/math` screen is now **Choose photo → Read
image → Check the result**, with the original photo and readable output beside
each other. Region counts, raw OCR, timing, copyable LaTeX and manual crop controls
are under optional editing/More tools sections. Region overlays are off by default.

Fraction layout fix: numerator/bar/denominator components are grouped into one
equation row before recognition, and long fraction bars are protected from page-rule
removal. The user's two-step fraction example is retained as a regression fixture.
Both equations are now complete crops and the first is transcribed correctly.
The model still misreads the leading implication arrow on the second line as a
Greek symbol; the suspicious array output is flagged for checking. No perfect
recognition claim is made. Latest regression: **221 passed, 11 skipped**.

## Automatic text + equations

The `/math` page now also accepts complete questions and textbook regions. Choose
**Extract text + equations automatically** after uploading; no equation selection
is required for this mode. A webcam capture can be opened through **Recognise
equations from this photo** on its existing passage review screen.

The automatic workflow:

1. Decodes the original image and creates a separate layout-analysis copy.
2. Finds visual rows and strong column-divider rules, removing page rules from
   the text-analysis copy. Clear ruled two-column layouts retain column order.
3. Uses Tesseract for the words, and proposes equation regions using symbols,
   short mathematical tokens and fraction-like spatial structure. Inline equations
   retain their preceding and following text as separate ordered spans.
4. Sends the proposed regions, cropped from the **original image pixels**, to one
   isolated pix2tex batch. The model loads once for all equations on the page.
5. Shows an original-image region overlay, approximate reconstructed document
   preview, editable text/LaTeX blocks, raw OCR alternatives and combined text.

This detector is heuristic, not a trained general document-layout system. It can
miss equations, treat notation as text or include non-equation regions. Unruled
multi-column documents, diagrams, tables, handwriting and complex layouts are not
guaranteed. It does not reproduce the original typography or images. Use the manual
crop retry when a region is missed, and compare all content with the original.

Math drafts are **not verified formulas**. Simple disagreements between raw OCR
and math-model output are flagged; this is not a general mathematical equivalence
checker. Automatic recognition can still change Latin/Greek letters, equality
signs, case and other symbols. The visible source and editable blocks remain
essential. No generated math draft becomes an approved lesson automatically.

`ocr.math.max_regions` defaults to 24 equations. Extra equation candidates remain
visible as unresolved OCR; content is not silently truncated. More than 160 visual
rows is rejected with a request to use a smaller region. A missing math model or
math-worker failure retains the text and unresolved equation regions with warnings.
Pure text images do not load the math model.

The JSON result from `/math/extract` includes ordered blocks with `kind`, `text`,
optional `latex`, original-image `bbox`, `column`, `row`, detector reason, warnings
and timing. All output remains a review draft. Copy the reviewed combined result
when needed; existing passage requirements and lesson approval are unchanged.

Executed examples: the user's ruled two-column poster was separated into two
columns and automatically produced 12 equation drafts. Some drafts still confused
Latin `v` with other letters. A generated mixed question retained surrounding
sentences plus standalone/inline equation locations, but its math model made a
known error in a standalone `F=ma` draft. This was flagged as a disagreement with
text OCR. These examples demonstrate detection/ordering, not perfect recognition.
See `docs/evidence/mixed_ocr_windows/` for the actual outputs and regression results.

## Manual equation retry

Open **http://127.0.0.1:5000/math**. This optional experiment uses local CPU
[pix2tex](https://github.com/lukas-blecher/LaTeX-OCR) to recognise **one cropped
equation**. It does not replace Tesseract for paragraphs or Qwen for lesson wording.
The original no-extra-model requirement was extended at the user's request to try
LaTeX recognition, with the model isolated from the existing environment.

1. Upload a clear JPG/PNG, or choose **Try the formula poster** on this PC.
   From a captured passage, **Recognise equations from this photo** opens the
   same image in this crop editor without another upload.
2. Drag a rectangle tightly around one complete equation, including fraction bars,
   subscripts and exponents. Exclude headings, borders and neighboring formulas.
3. Choose **Recognise selected equation**. First model load takes additional time.
4. Compare the cropped original, editable LaTeX and formatted preview. Correct
   every error manually. Copy the result when ready.

Rendering LaTeX and recognising it are distinct operations. Editing LaTeX updates
the preview without rerunning OCR. The preview uses bundled KaTeX to generate native
MathML; no remote renderer, CDN, web fonts, TeX compiler, Node or shell execution is
used. `trust:false`, bounded macro expansion and size limits follow
[KaTeX's security guidance](https://katex.org/docs/security.html).

The output remains an **unapproved draft equation**. It is not inserted into a
confirmed passage or lesson. The existing passage length/sentence requirements,
supported formula registry, concept gate and teacher approval are unchanged.
Neither recognisable symbols nor valid LaTeX establish scientific correctness.
The poster itself contains incorrect labels; transcription is not a correction
of its scientific content.

## Separate desktop setup (Windows)

Never run these commands in the working `.venv` or pinned Pi runtime environment.
CPU packages and downloaded model files live only in `.venv-math`.

```powershell
python -m venv .venv-math
.\.venv-math\Scripts\python -m pip install --upgrade pip
.\.venv-math\Scripts\python -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple
.\.venv-math\Scripts\python -m pip install -r requirements-math-ocr.txt
.\.venv-math\Scripts\python scripts/download_math_weights.py
.\.venv-math\Scripts\python -m pip check
```

The one-time setup downloads weights from the pix2tex project's release. It sends
no images. Runtime starts a separate worker with offline mode enabled, refuses
missing weights, disables requests/downloads and clipboard writes, and limits CPU
threads. Crop/result temporary files are cleaned up after processing. Image bytes
stay on this machine. The model reloads per request for isolation; timings include
separate model load and recognition durations.

`ocr.math.enabled` controls the experiment. Optional `ocr.math.python_path` selects
the separate interpreter; the default is `.venv-math/Scripts/python.exe` on Windows
and `.venv-math/bin/python` on Linux. Requests have a configurable timeout.
The local poster shortcut uses `ocr.math.example_scan_id`; if the capture is deleted
or on another device, upload an image instead.

There is **no Raspberry Pi compatibility or performance claim** for this model.
The original Qwen `.pte` files, tokenizer, XNNPACK settings and installed model
environment are untouched. Keep using ordinary Tesseract paragraph OCR for the
lightweight Pi demonstration until this separate experiment is measured there.

## Changes

Added `ocr/math_ocr.py`, `scripts/math_ocr_worker.py`, explicit model setup script,
`requirements-math-ocr.txt`, a local `/math` crop/editor page, local KaTeX JS/license,
crop validation and API tests. Normal passage OCR is unchanged. The main scan page
links to the experiment. A single equation is not a lesson passage and cannot
automatically bypass either review gate.

## Executed PC test results (14 November 2026)

The actual local model was run on three small crops from the user-provided poster:

| Crop | Actual model output | Comparison |
|---|---|---|
| Force | `F=m a` | matches visible formula |
| Density | `\rho={\frac{m}{V}}` | matches visible formula including fraction |
| Kinetic energy | `K E={\frac{1}{2}}m\nu^{2}` | **incorrect symbol**: Greek nu instead of Latin v; manual correction required |

Model loading measured approximately 4.5–4.7 seconds; individual recognition
approximately 0.085–0.254 seconds on this Windows PC, with 4 CPU threads. These
three examples are a smoke test, not an accuracy benchmark or Pi measurement.
The kinetic-energy error is retained in evidence, not silently rewritten.

A real HTTP POST to `/math/recognize`, including CSRF token, original poster and
density crop coordinates, returned the correct LaTeX draft. The page, local
renderer asset and poster endpoint returned HTTP 200. Both environment dependency
checks passed. Full regression: **214 passed, 11 skipped**. Browser visual/manual
interaction and Raspberry Pi math OCR acceptance remain untested.
See [math experiment evidence](evidence/math_ocr_windows/README.md).
