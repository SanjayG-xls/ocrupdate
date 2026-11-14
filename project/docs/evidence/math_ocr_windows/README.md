# Local pix2tex experiment — Windows PC

14 November 2026. Actual inference, with downloaded upstream weights in a separate
`.venv-math` environment, not Qwen inference. No images were sent to a remote API.

`force.json`, `density.json` and `kinetic_energy.json` are the actual model outputs
on cropped regions of the user's poster. The kinetic energy sample has a known
recognition error: `\nu` instead of `v`. It must be manually corrected; retain
this result when reporting the model's limitations.

`http_smoke.json` is the result of a real local HTTP upload/crop request for density.
`weights.json` records sizes, upstream URLs and hashes of the downloaded model files.
`regression.txt` records 214 passing tests and 11 skips. The model samples were run
separately from pytest. Both Python environments passed `pip check`.

No browser visual test or Raspberry Pi result is claimed.
See [setup and operating instructions](../../MATH_OCR.md).
