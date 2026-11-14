"""Level Bridge STEM – offline, adaptive learning assistant (Namma AI Hackathon 2026, PS1).

The package is split into:

* a deterministic learning engine (passage analysis, answer engines, validation,
  routing, scoring) that runs and is tested on any Linux laptop, and
* a model-runtime adapter layer (``model_runtime``) that talks to ExecuTorch on the
  Raspberry Pi 5. The engine never depends on the LLM for correctness.
"""

__version__ = "0.2.4"
