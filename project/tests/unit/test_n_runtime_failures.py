"""Sequences B and N (no hardware): runtime adapters and failure handling.

Real ExecuTorch loading/inference is tested in tests/hardware (LB_HARDWARE=1).
"""
import time
from pathlib import Path

import pytest

from conftest import load_fixture
from level_bridge.explanation_generator import ExplanationGenerator
from level_bridge.model_runtime import (ExecuTorchRunnerRuntime, LlamaMainRuntime, RuntimeUnavailable,
                                        ScriptedRuntime, TemplateRuntime, _fill_stats, GenerationResult,
                                        clean_output, create_runtime, format_prompt)

FX = load_fixture("llm_outputs.json")


def _et(tmp_path, timeout=1.0):
    return ExecuTorchRunnerRuntime(tmp_path / "missing.pte", tmp_path / "tok.json", None, 0.0, "sys", "qwen_chat", timeout)


def test_missing_model_file(tmp_path):
    with pytest.raises(RuntimeUnavailable, match="Model file not found"):
        _et(tmp_path).load()


def test_load_failure_when_executorch_missing_or_bad_file(tmp_path):
    (tmp_path / "missing.pte").write_bytes(b"not a pte")
    (tmp_path / "tok.json").write_text("{}")
    with pytest.raises(RuntimeUnavailable):
        _et(tmp_path).load()        # either import fails (laptop) or the runner rejects the file


def test_llama_main_missing_binary(tmp_path):
    rt = LlamaMainRuntime(tmp_path / "llama_main", tmp_path / "m.pte", tmp_path / "t.json", 0.0, "", "qwen_chat", 5, [])
    with pytest.raises(RuntimeUnavailable, match="llama_main binary not found"):
        rt.load()


def test_unknown_backend_rejected(cfg):
    with pytest.raises(ValueError, match="Unknown backend"):
        create_runtime(cfg.model, cfg.path, "cloud_api")


class _SlowRunner:
    stopped = False

    def reset(self):
        pass

    def generate(self, prompt, config, token_cb, stats_cb):
        token_cb("Speed ")
        time.sleep(3)

    def stop(self):
        _SlowRunner.stopped = True


class _GC:
    def __init__(self, **kw):
        self.kw = kw


def test_timeout_stops_runner(tmp_path):
    rt = _et(tmp_path, timeout=0.3)
    rt._runner, rt._GenerationConfig = _SlowRunner(), _GC
    res = rt.generate("x", 10)
    assert not res.ok and "timeout" in res.error and _SlowRunner.stopped


class _EmptyRunner(_SlowRunner):
    def generate(self, prompt, config, token_cb, stats_cb):
        token_cb("<|im_end|>")


def test_empty_output_is_failure(tmp_path):
    rt = _et(tmp_path)
    rt._runner, rt._GenerationConfig = _EmptyRunner(), _GC
    res = rt.generate("x", 10)
    assert not res.ok and res.error == "empty model output"


def test_runner_passes_greedy_config(tmp_path):
    seen = {}

    class R(_SlowRunner):
        def generate(self, prompt, config, token_cb, stats_cb):
            seen["prompt"], seen["cfg"] = prompt, config.kw
            token_cb("ok")

    rt = _et(tmp_path)
    rt._runner, rt._GenerationConfig = R(), _GC
    assert rt.generate("hello", 7).ok
    assert seen["cfg"] == {"echo": False, "max_new_tokens": 7, "temperature": 0.0}
    assert seen["prompt"].startswith("<|im_start|>system") and seen["prompt"].endswith("<|im_start|>assistant\n")


def test_stats_mapping():
    r = GenerationResult(True, "x", "executorch_runner", 1.0)
    _fill_stats(r, {"model_load_start_ms": 0, "model_load_end_ms": 900, "inference_start_ms": 1000,
                    "prompt_eval_end_ms": 1400, "first_token_ms": 1450, "num_prompt_tokens": 210,
                    "num_generated_tokens": 64})
    assert (r.model_load_ms, r.ttft_ms, r.prompt_eval_ms, r.prompt_tokens, r.generated_tokens) == (900, 450, 400, 210, 64)


def test_clean_output_and_prompt_format():
    assert clean_output("Speed is fast.<|im_end|>junk") == "Speed is fast."
    assert format_prompt("u", "s", "raw") == "s\n\nu\n"


def test_template_runtime_never_ok():
    r = TemplateRuntime().generate("x", 5)
    assert not r.ok and r.backend == "template"


@pytest.mark.parametrize("outputs", [[FX["malformed"], FX["malformed"]], [FX["empty"], FX["empty"]],
                                     [FX["missing_terms_l2"], FX["wrong_formula_l2"]],
                                     [RuntimeError("load failure"), TimeoutError("timeout")]])
def test_failures_fall_back_and_are_flagged(analysed, outputs):
    passage, km, reg, v = analysed
    e = ExplanationGenerator(passage, km, reg, v, ScriptedRuntime(outputs), 2).generate("l2")
    assert e.source == "template" and e.fallback and len(e.attempts) == 2


def test_fallback_not_counted_as_llm(cfg):
    from level_bridge.pipeline import build
    art = build(cfg, cfg.root / "data/passages/speed_passage.txt",
                ScriptedRuntime(fn=lambda p: FX["malformed"]))
    assert art.llm_outputs_accepted == 0
    assert all(c["ok"] for c in art.generation_calls)   # runtime returned text, validator rejected it
    assert {k: e.source for k, e in art.explanations.items() if k != "l3"} == {"summary": "template", "l1": "template", "l2": "template"}
