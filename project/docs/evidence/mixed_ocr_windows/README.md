# Automatic mixed text/equation OCR — Windows PC

Actual local Tesseract + isolated pix2tex HTTP tests, 14 November 2026. No
Raspberry Pi, model-accuracy benchmark or real Qwen inference is claimed.

* `poster_result.json`: uploaded the user's poster to `/math/extract` without
  manual crop coordinates. The heuristic detected two ruled columns and produced
  12 equation drafts in source column order. Some symbols are incorrect (notably
  Latin v versus other letters); all output remains review-required.
* `question_result.json`: uploaded a generated question containing preceding text,
  a standalone equation, following text and a sentence with inline `F = ma`.
  Surrounding text and equation locations were preserved. The actual math model
  made an error in the standalone equation; the raw text OCR alternative and
  disagreement warning are retained, not rewritten as a successful formula.
* `regression.txt`: **220 passed, 11 skipped**. Added tests cover inline span
  boundaries, two-column ruled layout, fraction-row grouping, batched isolated
  workers, temporary cleanup, missing-model degradation, output disagreement and
  API request protection. No tests were weakened.

Both environments pass `pip check`. Recognition uses original image pixels after
detecting candidates on an analysis copy. The model loads once for a whole batch.
Combined output is a draft and does not bypass passage validation or teacher review.

The HTTP page and recognition endpoints were exercised. A headless-browser
screenshot attempt was blocked by execution policy; browser visual interaction
has not been claimed as verified in this change.

See [operating instructions and limitations](../../MATH_OCR.md).
