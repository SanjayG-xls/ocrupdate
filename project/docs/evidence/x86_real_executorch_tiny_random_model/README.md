# Evidence: real ExecuTorch 1.4.0 runtime on x86-64 (tiny random-weight model)

**What this is:** the project's `executorch_runner` adapter running against the real
`executorch==1.4.0` `TextLLMRunner`, with torch 2.15.0 and transformers 4.57.1 on Python 3.13
and x86-64 Linux (a cloud dev container). The `.pte` is a 2-layer, dim-64 Llama-architecture model
with **random weights**, exported locally with `export_llm` (KV cache, custom SDPA, XNNPACK). It was
built by `scripts/export_tiny_test_model.sh`.

**What it proves:**

* the runtime imports
* the custom operators register
* the `.pte` loads
* generation runs and the runner reports its stats (prompt tokens, generated tokens, TTFT)
* greedy decoding is deterministic
* timeout, `stop()` and recovery work
* the full pipeline handles real model output, rejecting noise and falling back to templates labelled `source: template`
* scores are unchanged (25/36, +3, 28, +6/18)

**What it does NOT prove:** anything about Qwen2.5-0.5B-Instruct, explanation quality, or Raspberry
Pi 5 latency, memory or thermals. Those need sequences B and P on the Pi. The timings in these
files come from a fast x86 server running a 64 MB toy model. **Do not quote them as project performance.**

| File | Content |
|---|---|
| check_env.txt | versions, runner importable |
| infer.txt, inference.json | 3 repeated generations with runner stats |
| session_terminal.txt, learning_report.json | full Priya session on the real runtime |
| stage4_explanations.json, stage_build_log.json | every attempt, with why validation rejected it |
| pytest_real_runtime.txt | 6 real-runtime tests passed |
| pip_freeze.txt | exact environment |
