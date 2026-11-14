"""Model-runtime adapters. The learning engine only sees the :class:`ModelRuntime` interface.

Backends
--------
``executorch_runner`` (primary)
    ``executorch.extension.llm.runner.TextLLMRunner`` from the **executorch==1.4.0**
    wheel. Verified API (from the wheel's ``_llm_runner.pyi``)::

        TextLLMRunner(model_path: str, tokenizer_path: str, data_path: Optional[str] = None)
        runner.generate(prompt: str, config: GenerationConfig,
                        token_callback: Optional[Callable[[str], None]] = None,
                        stats_callback: Optional[Callable[[Stats], None]] = None) -> None
        runner.reset()
        GenerationConfig(*, echo=True, max_new_tokens=-1, warming=False, seq_len=-1,
                         temperature=0.8, num_bos=0, num_eos=0)
        Stats: model_load_start_ms, model_load_end_ms, inference_start_ms,
               prompt_eval_end_ms, first_token_ms, inference_end_ms,
               num_prompt_tokens, num_generated_tokens, to_json_string()

    The runner owns tokenisation (``tokenizer.json`` via pytorch-tokenizers), prefill,
    the KV-cache decode loop and sampling (temperature 0 = greedy argmax). The ``.pte``
    must be exported with ``use_kv_cache`` / ``use_sdpa_with_kv_cache`` (see models/README.md).

``llama_main``
    The ExecuTorch C++ example runner, run as a subprocess (``--model_path``,
    ``--tokenizer_path``, ``--prompt``, ``--seq_len``, ``--temperature``). Stats are parsed
    from its ``PyTorchObserver {...}`` line when present. Alternative path only.

``template``
    No model at all. Every result has ``ok=False`` and ``backend='template'`` so a
    template-only run can never be reported as model inference.

``scripted`` (tests)
    Returns pre-defined outputs; used by the automated test suite. Never used for reports.
"""

from __future__ import annotations

import json
import logging
import re
try:  # POSIX only; Windows laptops have no 'resource' module
    import resource
except ImportError:  # pragma: no cover - exercised on Windows
    resource = None
import shutil
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Dict, List, Optional

log = logging.getLogger("level_bridge.model_runtime")


class RuntimeUnavailable(RuntimeError):
    """The configured backend cannot be used (missing package, file or binary)."""


@dataclass
class GenerationResult:
    """Outcome of one generation call. ``ok`` is True only for a real model output."""

    ok: bool
    text: str
    backend: str
    wall_time_s: float
    error: Optional[str] = None
    model_load_ms: Optional[float] = None
    ttft_ms: Optional[float] = None          # time to first token, from runner stats
    prompt_eval_ms: Optional[float] = None
    prompt_tokens: Optional[int] = None
    generated_tokens: Optional[int] = None
    raw_stats: Optional[Dict[str, object]] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def format_prompt(user: str, system: str, fmt: str) -> str:
    """Apply the Qwen2.5 chat template (ChatML) or return the raw prompt."""
    if fmt == "raw":
        return f"{system}\n\n{user}\n"
    return (f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n")


def clean_output(text: str) -> str:
    """Strip chat special tokens and trailing whitespace from model output."""
    t = re.split(r"<\|im_end\|>|<\|endoftext\|>", text)[0]
    t = re.sub(r"<\|[^|>]*\|>", "", t)
    return t.strip()


def peak_rss_mb() -> float:
    """Peak resident set size of this process (Linux reports ru_maxrss in KiB).

    On Windows (laptop development only) the peak working set is read through the Win32 API;
    if that is unavailable, 0.0 is returned. Pi measurements always use the Linux path.
    """
    if resource is not None:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    try:
        import ctypes
        from ctypes import wintypes

        class _PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        h = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
            return pmc.PeakWorkingSetSize / (1024.0 * 1024.0)
    except Exception:
        pass
    return 0.0


class ModelRuntime(ABC):
    """Interface used by the learning engine."""

    name: str = "abstract"
    is_llm: bool = False

    @abstractmethod
    def load(self) -> float:
        """Load the model; return load time in seconds."""

    @abstractmethod
    def generate(self, user_prompt: str, max_new_tokens: int) -> GenerationResult:
        """Generate a completion for ``user_prompt``."""

    def describe(self) -> Dict[str, object]:
        return {"backend": self.name, "is_llm": self.is_llm}

    def close(self) -> None:  # pragma: no cover - trivial
        pass


class TemplateRuntime(ModelRuntime):
    """No-LLM runtime: always reports ``ok=False`` so callers use deterministic templates."""

    name = "template"
    is_llm = False

    def load(self) -> float:
        return 0.0

    def generate(self, user_prompt: str, max_new_tokens: int) -> GenerationResult:
        return GenerationResult(False, "", self.name, 0.0, error="template backend: no model inference")


class ScriptedRuntime(ModelRuntime):
    """Test double returning queued outputs (or calling a function). Marked as a mock."""

    name = "scripted"

    def __init__(self, outputs: Optional[List[object]] = None,
                 fn: Optional[Callable[[str], object]] = None, is_llm: bool = True) -> None:
        self.outputs = list(outputs or [])
        self.fn = fn
        self.is_llm = is_llm
        self.prompts: List[str] = []

    def load(self) -> float:
        return 0.0

    def generate(self, user_prompt: str, max_new_tokens: int) -> GenerationResult:
        self.prompts.append(user_prompt)
        out = self.fn(user_prompt) if self.fn else (self.outputs.pop(0) if self.outputs else "")
        if isinstance(out, Exception):
            return GenerationResult(False, "", self.name, 0.0, error=f"{type(out).__name__}: {out}")
        text = clean_output(str(out))
        if not text:  # same contract as the real runners: empty output is a failed generation
            return GenerationResult(False, "", self.name, 0.0, error="empty model output")
        return GenerationResult(True, str(out), self.name, 0.0, generated_tokens=len(str(out).split()))


class ExecuTorchRunnerRuntime(ModelRuntime):
    """ExecuTorch ``TextLLMRunner`` (executorch==1.4.0 Python bindings)."""

    name = "executorch_runner"
    is_llm = True

    def __init__(self, pte_path: Path, tokenizer_path: Path, data_path: Optional[Path],
                 temperature: float, system_prompt: str, prompt_format: str, timeout_s: float) -> None:
        self.pte_path, self.tokenizer_path, self.data_path = pte_path, tokenizer_path, data_path
        self.temperature, self.system_prompt = temperature, system_prompt
        self.prompt_format, self.timeout_s = prompt_format, timeout_s
        self._runner = None
        self._GenerationConfig = None
        self.version: Optional[str] = None

    def load(self) -> float:
        if not self.pte_path.exists():
            raise RuntimeUnavailable(f"Model file not found: {self.pte_path}")
        if not self.tokenizer_path.exists():
            raise RuntimeUnavailable(f"Tokenizer file not found: {self.tokenizer_path}")
        t0 = time.perf_counter()
        try:
            import executorch  # noqa: F401
            from executorch.extension.llm.runner import TextLLMRunner, GenerationConfig
            try:
                from executorch import version as _v
                self.version = getattr(_v, "__version__", None)
            except Exception:  # pragma: no cover - informational only
                self.version = None
        except Exception as exc:  # ImportError or RuntimeError raised by the package
            raise RuntimeUnavailable(f"ExecuTorch LLM runner not importable: {exc}") from exc
        # A KV-cache/SDPA export (use_sdpa_with_kv_cache) uses llama::custom_sdpa / update_cache, and a
        # quantised export may use quantized kernels. These operators must be registered BEFORE the
        # runner loads the program, otherwise loading 'forward' fails with "Missing operator:
        # [..] llama::custom_sdpa.out". Verified with executorch 1.4.0 (x86-64) on an exported .pte.
        self.registered_op_libs: List[str] = []
        for mod in ("executorch.extension.pybindings.portable_lib",
                    "executorch.extension.llm.custom_ops.custom_ops",
                    "executorch.kernels.quantized"):
            try:
                __import__(mod)
                self.registered_op_libs.append(mod)
            except Exception as exc:  # pragma: no cover - depends on the installed wheel
                log.warning("could not import %s: %s", mod, exc)
        try:
            if self.data_path:
                self._runner = TextLLMRunner(str(self.pte_path), str(self.tokenizer_path), str(self.data_path))
            else:
                self._runner = TextLLMRunner(str(self.pte_path), str(self.tokenizer_path))
            # The constructor may defer loading; get_vocab_size() forces the program/tokenizer to load
            # so that load failures surface here (and model-load time is measured here).
            self.vocab_size = int(self._runner.get_vocab_size())
        except Exception as exc:
            raise RuntimeUnavailable(f"TextLLMRunner could not load the model: {exc}") from exc
        self._GenerationConfig = GenerationConfig
        return time.perf_counter() - t0

    def generate(self, user_prompt: str, max_new_tokens: int) -> GenerationResult:
        if self._runner is None:
            return GenerationResult(False, "", self.name, 0.0, error="runtime not loaded")
        prompt = format_prompt(user_prompt, self.system_prompt, self.prompt_format)
        pieces: List[str] = []
        stats_box: Dict[str, object] = {}

        def on_token(tok: str) -> None:
            pieces.append(tok)

        def on_stats(st) -> None:
            # Attributes are documented in _llm_runner.pyi; the JSON string is kept as raw evidence.
            for k in ("model_load_start_ms", "model_load_end_ms", "inference_start_ms", "prompt_eval_end_ms",
                      "first_token_ms", "inference_end_ms", "num_prompt_tokens", "num_generated_tokens",
                      "aggregate_sampling_time_ms", "SCALING_FACTOR_UNITS_PER_SECOND"):
                stats_box[k] = getattr(st, k, None)
            try:
                js = json.loads(st.to_json_string())
                stats_box["json"] = js
                for k, v in js.items():          # JSON uses prompt_tokens / generated_tokens
                    if stats_box.get(k) is None:
                        stats_box[k] = v
            except Exception:
                pass

        cfg = self._GenerationConfig(echo=False, max_new_tokens=int(max_new_tokens), temperature=float(self.temperature))
        error: List[str] = []

        native_out: List[str] = []

        def work() -> None:
            # The C++ runner echoes tokens and a 'PyTorchObserver {...}' line to file descriptor 1.
            # Capture it so the learner's terminal stays clean; it is kept as raw evidence.
            with _capture_fd1(native_out):
                try:
                    self._runner.reset()
                    self._runner.generate(prompt, cfg, on_token, on_stats)
                except Exception as exc:  # RuntimeError from the C++ runner
                    error.append(f"{type(exc).__name__}: {exc}")

        t0 = time.perf_counter()
        th = threading.Thread(target=work, daemon=True)
        th.start()
        th.join(self.timeout_s)
        wall = time.perf_counter() - t0
        if th.is_alive():
            try:
                self._runner.stop()
            except Exception:
                pass
            th.join(5)
            return GenerationResult(False, clean_output("".join(pieces)), self.name, wall,
                                    error=f"timeout after {self.timeout_s:g} s")
        text = clean_output("".join(pieces))
        m = re.search(r"PyTorchObserver\s+(\{.*\})", "".join(native_out))
        if m:
            stats_box.setdefault("observer_line", m.group(1))
        res = GenerationResult(not error and bool(text), text, self.name, wall,
                               error=error[0] if error else (None if text else "empty model output"),
                               raw_stats=stats_box or None)
        _fill_stats(res, stats_box)
        return res

    def describe(self) -> Dict[str, object]:
        return {"backend": self.name, "is_llm": True, "executorch_version": self.version,
                "registered_op_libs": getattr(self, "registered_op_libs", []),
                "vocab_size": getattr(self, "vocab_size", None),
                "pte_path": str(self.pte_path), "tokenizer_path": str(self.tokenizer_path),
                "temperature": self.temperature, "prompt_format": self.prompt_format}


class _capture_fd1:
    """Temporarily redirect OS-level stdout (fd 1) into a buffer list."""

    def __init__(self, sink: List[str]) -> None:
        self.sink = sink

    def __enter__(self):
        import os
        import sys
        import tempfile
        sys.stdout.flush()
        self._tmp = tempfile.TemporaryFile(mode="w+b")
        self._saved = os.dup(1)
        os.dup2(self._tmp.fileno(), 1)
        return self

    def __exit__(self, *exc) -> bool:
        import os
        import sys
        try:
            sys.stdout.flush()
        except Exception:
            pass
        os.dup2(self._saved, 1)
        os.close(self._saved)
        self._tmp.seek(0)
        self.sink.append(self._tmp.read().decode("utf-8", "replace"))
        self._tmp.close()
        return False


def _fill_stats(res: GenerationResult, st: Dict[str, object]) -> None:
    def g(k):
        v = st.get(k)
        return float(v) if isinstance(v, (int, float)) else None
    ls, le, i0, pe, ft = (g("model_load_start_ms"), g("model_load_end_ms"), g("inference_start_ms"),
                          g("prompt_eval_end_ms"), g("first_token_ms"))
    if ls is not None and le is not None and le >= ls:
        res.model_load_ms = le - ls
    if i0 is not None and ft is not None and ft >= i0:
        res.ttft_ms = ft - i0
    if i0 is not None and pe is not None and pe >= i0:
        res.prompt_eval_ms = pe - i0
    for key, attr in (("num_prompt_tokens", "prompt_tokens"), ("prompt_tokens", "prompt_tokens"),
                      ("num_generated_tokens", "generated_tokens"), ("generated_tokens", "generated_tokens")):
        v = st.get(key)
        if isinstance(v, (int, float)) and getattr(res, attr) is None:
            setattr(res, attr, int(v))


class LlamaMainRuntime(ModelRuntime):
    """ExecuTorch C++ example runner invoked per call (model is reloaded each call)."""

    name = "llama_main"
    is_llm = True

    def __init__(self, binary: Path, pte_path: Path, tokenizer_path: Path, temperature: float,
                 system_prompt: str, prompt_format: str, timeout_s: float, extra_args: List[str]) -> None:
        self.binary, self.pte_path, self.tokenizer_path = binary, pte_path, tokenizer_path
        self.temperature, self.system_prompt, self.prompt_format = temperature, system_prompt, prompt_format
        self.timeout_s, self.extra_args = timeout_s, extra_args

    def load(self) -> float:
        for p, what in ((self.binary, "llama_main binary"), (self.pte_path, "model"), (self.tokenizer_path, "tokenizer")):
            if not Path(p).exists():
                raise RuntimeUnavailable(f"{what} not found: {p}")
        return 0.0

    def generate(self, user_prompt: str, max_new_tokens: int) -> GenerationResult:
        prompt = format_prompt(user_prompt, self.system_prompt, self.prompt_format)
        cmd = [str(self.binary), "--model_path", str(self.pte_path), "--tokenizer_path", str(self.tokenizer_path),
               "--prompt", prompt, "--seq_len", str(1024), "--temperature", str(self.temperature), *self.extra_args]
        t0 = time.perf_counter()
        try:
            cp = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            return GenerationResult(False, "", self.name, time.perf_counter() - t0, error="timeout")
        wall = time.perf_counter() - t0
        out = cp.stdout
        stats = {}
        m = re.search(r"PyTorchObserver\s+(\{.*\})", out + cp.stderr)
        if m:
            try:
                stats = json.loads(m.group(1))
            except json.JSONDecodeError:
                stats = {}
        body = out.split(prompt, 1)[1] if prompt in out else out
        body = re.sub(r"PyTorchObserver.*", "", body)
        text = clean_output(body)
        res = GenerationResult(cp.returncode == 0 and bool(text), text, self.name, wall,
                               error=None if cp.returncode == 0 and text else (cp.stderr[-400:] or "empty output"),
                               raw_stats=stats or None)
        if stats:
            mapped = dict(stats)
            mapped.setdefault("num_prompt_tokens", stats.get("prompt_tokens"))
            mapped.setdefault("num_generated_tokens", stats.get("generated_tokens"))
            _fill_stats(res, mapped)
        return res

    def describe(self) -> Dict[str, object]:
        return {"backend": self.name, "is_llm": True, "binary": str(self.binary), "pte_path": str(self.pte_path)}


def create_runtime(model_cfg: Dict[str, object], resolve: Callable[[str], Path], backend: Optional[str] = None) -> ModelRuntime:
    """Factory from ``config/model_config.yaml``. Never silently substitutes another backend."""
    backend = backend or str(model_cfg.get("backend", "executorch_runner"))
    gen = model_cfg.get("generation", {}) or {}
    temp = float(gen.get("temperature", 0.0))
    sysp = str(gen.get("system_prompt", "")).strip()
    fmt = str(gen.get("prompt_format", "qwen_chat"))
    timeout = float(gen.get("timeout_s", 180))
    if backend == "executorch_runner":
        c = model_cfg["executorch_runner"]
        return ExecuTorchRunnerRuntime(resolve(c["pte_path"]), resolve(c["tokenizer_path"]),
                                       resolve(c["data_path"]) if c.get("data_path") else None, temp, sysp, fmt, timeout)
    if backend == "llama_main":
        c = model_cfg["llama_main"]
        return LlamaMainRuntime(resolve(c["binary_path"]), resolve(c["pte_path"]), resolve(c["tokenizer_path"]),
                                temp, sysp, fmt, timeout, list(c.get("extra_args") or []))
    if backend == "template":
        return TemplateRuntime()
    raise ValueError(f"Unknown backend '{backend}' (allowed: executorch_runner, llama_main, template)")


def which(binary: str) -> Optional[str]:
    return shutil.which(binary)
