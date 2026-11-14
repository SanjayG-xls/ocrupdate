"""Hardware tests – run ONLY on the Raspberry Pi 5 with the exported model present:

    LB_HARDWARE=1 pytest tests/hardware -v

These are the only tests that exercise real ExecuTorch inference. Results are what the
runner reports; nothing is asserted about speed (that is measured by the benchmark).
"""
import os

import pytest

from level_bridge.model_runtime import create_runtime
from level_bridge.pipeline import build

pytestmark = pytest.mark.skipif(os.environ.get("LB_HARDWARE") != "1", reason="set LB_HARDWARE=1 on the Pi")


@pytest.fixture(scope="module")
def runtime(cfg):
    rt = create_runtime(cfg.model, cfg.path)
    rt.load()
    return rt


def test_executorch_version(cfg):
    import executorch.version as v
    assert v.__version__.startswith(cfg.model["executorch_runner"]["expected_executorch_version"])


def test_single_inference(runtime):
    r = runtime.generate("In one sentence, what is speed?", 48)
    assert r.ok, r.error
    assert r.generated_tokens and r.generated_tokens > 0


def test_repeat_inference_is_deterministic(runtime):
    a = runtime.generate("Name the unit of speed.", 24)
    b = runtime.generate("Name the unit of speed.", 24)
    assert a.ok and b.ok and a.text == b.text      # temperature 0 -> greedy


def test_build_with_real_model(cfg, runtime):
    art = build(cfg, cfg.root / "data/passages/speed_passage.txt", runtime)
    assert all(c["backend"] == "executorch_runner" for c in art.generation_calls if "backend" in c)
    # Record (do not assume) how many outputs passed validation:
    print("explanation sources:", {k: e.source for k, e in art.explanations.items()})
    print("LLM outputs accepted:", art.llm_outputs_accepted)
