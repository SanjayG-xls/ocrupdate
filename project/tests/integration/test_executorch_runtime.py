"""Real ExecuTorch runtime contract test (any CPU) with a small RANDOM-WEIGHT .pte.

This proves the adapter works with the real executorch 1.4.0 TextLLMRunner (load, custom-op
registration, generation, stats, stop/timeout, validation + fallback). Output text is noise by
design, so this is NOT evidence of explanation quality or of Raspberry Pi performance.

    bash scripts/export_tiny_test_model.sh          # writes models/test/tiny_random_llama.pte + tokenizer.json
    LB_ET_TEST_DIR=models/test python -m pytest tests/integration/test_executorch_runtime.py -v
"""
import os
from pathlib import Path

import pytest

from level_bridge.model_runtime import ExecuTorchRunnerRuntime, RuntimeUnavailable
from level_bridge.pipeline import build

D = os.environ.get("LB_ET_TEST_DIR")
pytestmark = pytest.mark.skipif(not D, reason="set LB_ET_TEST_DIR (see scripts/export_tiny_test_model.sh)")


def _rt(timeout=60.0):
    d = Path(D)
    return ExecuTorchRunnerRuntime(d / "tiny_random_llama.pte", d / "tokenizer.json", None, 0.0, "test", "raw", timeout)


@pytest.fixture(scope="module")
def rt():
    r = _rt()
    r.load()
    return r


def test_load_registers_custom_ops(rt):
    assert "executorch.extension.llm.custom_ops.custom_ops" in rt.describe()["registered_op_libs"]
    assert rt.describe()["executorch_version"].startswith("1.4.0")


def test_generate_reports_stats(rt):
    r = rt.generate("Speed is", 12)
    assert r.ok and r.backend == "executorch_runner"
    assert r.prompt_tokens and r.generated_tokens and r.ttft_ms is not None


def test_greedy_is_deterministic(rt):
    assert rt.generate("Speed is", 8).text == rt.generate("Speed is", 8).text


def test_timeout_path_with_real_runner():
    r = _rt(timeout=0.0005)
    r.load()
    res = r.generate("Speed is the distance an object covers", 300)
    assert (not res.ok and "timeout" in (res.error or "")) or res.ok   # very fast CPUs may finish first
    r.timeout_s = 60                                                   # runner must recover after stop()
    assert r.generate("Speed is", 4).ok


def test_bad_file_is_runtime_unavailable(tmp_path):
    (tmp_path / "x.pte").write_bytes(b"garbage")
    tok = Path(D) / "tokenizer.json"
    r = ExecuTorchRunnerRuntime(tmp_path / "x.pte", tok, None, 0.0, "", "raw", 5)
    with pytest.raises(RuntimeUnavailable):
        r.load()
        res = r.generate("x", 2)       # if loading is deferred, the failure surfaces here
        if not res.ok:
            raise RuntimeUnavailable(res.error)


def test_noise_output_is_rejected_and_labelled(cfg, rt):
    art = build(cfg, cfg.root / "data/passages/speed_passage.txt", rt)
    assert all(c["ok"] for c in art.generation_calls)            # real generations happened
    assert art.llm_outputs_accepted == 0                         # random weights -> nothing validated
    assert {k: e.source for k, e in art.explanations.items() if k != "l3"} == {
        "summary": "template", "l1": "template", "l2": "template"}
