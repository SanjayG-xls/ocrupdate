"""Command-line interface: ``python -m level_bridge.main <command>`` (or ``level-bridge <command>``).

Commands
--------
check-env      dependency / version report (sequence A)
check-model    model + tokenizer presence, size, sha256, load test (sequence B)
infer          single or repeated inference with runner stats (sequence B)
process        passage -> sentences -> knowledge map -> registry, stage JSON (C, D)
build          explanations + item bank with validation records (E, F)
session        a learning session, scripted (--answers) or interactive (G-M)
offline-check  network state + backend locality (O)
benchmark      warm-up + measured build runs, CSV/JSON (P)
demo           end-to-end: build, scripted or interactive session, report, logs (Q)

Teach · Learn · Improve (report Section 7)
pack-build     TEACH: build a lesson pack once on the hub (LLM build phase) -> signed JSON
pack-review    TEACH: teacher approves / edits / replaces L1, L2 and summary (edits must pass the gate)
session --pack LEARN: model-free session replayed from a lesson pack
session --learner STU-xxxx [--consent]   IMPROVE: update the learner profile and show patterns
profile-show   IMPROVE: learner memory and recurring error patterns
profile-export IMPROVE: checksummed bundle to USB (refused without consent)
hub-import     IMPROVE: verify and merge bundles on the teacher hub
portal         IMPROVE: write the offline CBS portal page (HTML)

Live-round demo (trust made visible)
gate-report    each model draft, ACCEPTED / REJECTED by the validation gate, and why
compare        AI alone (same model answers the quiz + summarises) vs Level Bridge (Python-computed)

Exit codes: 0 ok, 2 configuration / input error, 3 model unavailable, 4 session error.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import logging
import platform
import sys
import time
import traceback
from pathlib import Path
from typing import Dict, List, Optional

_PROCESS_START = time.perf_counter()

from . import __version__  # noqa: E402
from .adaptive_router import Session  # noqa: E402
from .answer_providers import interactive_provider, load_script, scripted_provider  # noqa: E402
from .benchmark import repair_latency_stats, run_benchmark  # noqa: E402
from .cbm import CBM  # noqa: E402
from .concept_states import ConceptTracker  # noqa: E402
from .config import AppConfig, load_config, setup_logging  # noqa: E402
from .learning_report import build_report, dump_json, render_report, render_session  # noqa: E402
from .model_runtime import ModelRuntime, RuntimeUnavailable, TemplateRuntime, create_runtime, peak_rss_mb  # noqa: E402
from .offline_checker import check_offline  # noqa: E402
from .passage_processor import PassageError  # noqa: E402
from .pipeline import BuildArtifacts, analyse, build, resolve_input  # noqa: E402
from .repair_engine import RepairEngine  # noqa: E402
from .scoring import ScoreLedger  # noqa: E402
from . import learner_memory as lm  # noqa: E402
from .cbs_portal import write_portal  # noqa: E402
from .learning_report import render_event  # noqa: E402
from .lesson_pack import PackError, REVIEWABLE, apply_review, approved, make_pack, read_pack, replay, review_lines, write_pack  # noqa: E402
from .profile_bundle import BundleError, export_bundle, import_bundles  # noqa: E402
from .source_tags import tag_text  # noqa: E402
from . import trust_demo  # noqa: E402

log = logging.getLogger("level_bridge.main")
DEFAULT_PASSAGE = "data/passages/speed_passage.txt"


# ---------------------------------------------------------------------------- helpers
def _run_id() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _runtime(cfg: AppConfig, backend: Optional[str], allow_fallback: bool) -> (ModelRuntime, Dict[str, object]):
    """Create and load the runtime. A failed LLM load is an error unless --allow-template-fallback."""
    rt = create_runtime(cfg.model, lambda p: cfg.path(p), backend)
    info: Dict[str, object] = {"requested_backend": rt.name, "fallback_used": False}
    try:
        info["model_load_s"] = round(rt.load(), 3)
    except RuntimeUnavailable as exc:
        info["load_error"] = str(exc)
        if not allow_fallback:
            raise
        log.warning("model unavailable, using TEMPLATE backend (no LLM)", extra={"data": {"error": str(exc)}})
        rt = TemplateRuntime()
        rt.load()
        info["fallback_used"] = True
    info.update(rt.describe())
    return rt, info


def _print(s: str = "") -> None:
    print(s, flush=True)


def _llm_status_lines(art: BuildArtifacts, rt: ModelRuntime, info: Dict[str, object]) -> List[str]:
    lines = [f"Backend: {rt.name}  (LLM inference: {'yes' if rt.is_llm else 'NO - deterministic templates only'})"]
    if info.get("fallback_used"):
        lines.append(f"   WARNING: requested '{info['requested_backend']}' unavailable -> template fallback. "
                     f"Reason: {info.get('load_error')}")
    for k in ("summary", "l1", "l2", "l3"):
        e = art.explanations[k]
        lines.append(f"   {k:<8} source={e.source:<10} validated={e.validated}  attempts={len(e.attempts)}")
    sr = art.stem_rewording
    lines.append(f"   question stems: {'LLM reworded ' + str(sr.get('accepted', 0)) + ' accepted' if sr.get('attempted') and rt.is_llm else 'templates'}")
    lines.append(f"   LLM outputs accepted after validation: {art.llm_outputs_accepted}")
    return lines


# ---------------------------------------------------------------------------- commands
def cmd_check_env(cfg: AppConfig, args) -> int:
    rep: Dict[str, object] = {"python": platform.python_version(), "machine": platform.machine(),
                              "system": platform.system(), "level_bridge": __version__, "packages": {}}
    # distribution name -> import name. executorch is a namespace package (no __init__.py), so the
    # version comes from package metadata / executorch.version, never from executorch.__version__.
    for dist, mod in (("PyYAML", "yaml"), ("pytest", "pytest"), ("torch", "torch"), ("torchao", "torchao"),
                      ("pytorch-tokenizers", "pytorch_tokenizers"), ("transformers", "transformers"),
                      ("executorch", "executorch.version")):
        try:
            importlib.import_module(mod)
            rep["packages"][dist] = importlib.metadata.version(dist)
        except Exception as exc:
            rep["packages"][dist] = f"NOT AVAILABLE ({type(exc).__name__}: {str(exc)[:120]})"
    try:
        from executorch.extension.llm.runner import TextLLMRunner, GenerationConfig  # noqa: F401
        rep["executorch_llm_runner_importable"] = True
    except Exception as exc:
        rep["executorch_llm_runner_importable"] = f"NO ({type(exc).__name__}: {str(exc)[:160]})"
    exp = cfg.model.get("executorch_runner", {}).get("expected_executorch_version")
    et = rep["packages"].get("executorch", "")
    rep["executorch_version_matches_pin"] = (str(et).startswith(str(exp))) if exp else None
    rep["required_ok"] = not str(rep["packages"]["PyYAML"]).startswith("NOT")
    out = cfg.outputs_dir / "environment_report.json"
    dump_json(rep, out)
    _print(json.dumps(rep, indent=2))
    _print(f"\nwritten: {out}")
    return 0 if rep["required_ok"] else 2


def cmd_check_model(cfg: AppConfig, args) -> int:
    c = cfg.model.get(cfg.model.get("backend"), {}) if not args.backend else cfg.model.get(args.backend, {})
    rep: Dict[str, object] = {"backend": args.backend or cfg.model.get("backend")}
    for key in ("pte_path", "tokenizer_path", "binary_path", "data_path"):
        if c.get(key):
            p = cfg.path(c[key])
            entry = {"path": str(p), "exists": p.exists()}
            if p.exists() and p.is_file():
                entry["size_mb"] = round(p.stat().st_size / 1e6, 2)
                if key == "pte_path":
                    entry["sha256"] = _sha256(p)
                    exp = cfg.model.get("artifact", {}).get("sha256")
                    entry["sha256_matches_config"] = (entry["sha256"] == exp) if exp else "no checksum recorded"
            rep[key] = entry
    try:
        rt, info = _runtime(cfg, args.backend, allow_fallback=False)
        rep["load"] = {"ok": True, **info}
        rep["peak_rss_mb_after_load"] = round(peak_rss_mb(), 1)
        code = 0
    except RuntimeUnavailable as exc:
        rep["load"] = {"ok": False, "error": str(exc)}
        code = 3
    dump_json(rep, cfg.outputs_dir / "model_check.json")
    _print(json.dumps(rep, indent=2))
    return code


def cmd_infer(cfg: AppConfig, args) -> int:
    try:
        rt, info = _runtime(cfg, args.backend, allow_fallback=False)
    except RuntimeUnavailable as exc:
        _print(f"MODEL UNAVAILABLE: {exc}")
        return 3
    results = []
    for i in range(args.repeat):
        r = rt.generate(args.prompt, args.max_new_tokens)
        d = r.to_dict()
        d["run"] = i
        results.append(d)
        _print(f"--- run {i}  ok={r.ok}  wall={r.wall_time_s:.3f}s  ttft_ms={r.ttft_ms}  "
               f"prompt_tokens={r.prompt_tokens}  generated_tokens={r.generated_tokens}")
        _print(r.text if r.ok else f"ERROR: {r.error}")
    rep = {"backend": info, "prompt": args.prompt, "max_new_tokens": args.max_new_tokens, "runs": results,
           "peak_rss_mb": round(peak_rss_mb(), 1), "is_llm_inference": rt.is_llm}
    out = cfg.outputs_dir / f"inference_{_run_id()}.json"
    dump_json(rep, out)
    _print(f"written: {out}")
    return 0 if all(r["ok"] for r in results) else 3


def cmd_process(cfg: AppConfig, args) -> int:
    passage, km, registry, validator = analyse(cfg, Path(args.passage))
    out = cfg.outputs_dir
    dump_json(passage.to_dict(), out / "stage1_passage.json")
    dump_json(km.to_dict(), out / "stage2_knowledge_map.json")
    dump_json(registry.to_dict(), out / "stage3_key_term_registry.json")
    _print(f"Passage: {passage.word_count} words, {len(passage.sentences)} sentences, sha256 {passage.sha256[:12]}…")
    for w in passage.warnings:
        _print(f"   warning: {w}")
    _print(f"Knowledge map core types: {km.type_counts()}")
    _print(f"Concepts: {', '.join(c.cid + ' ' + c.label for c in km.concepts)}")
    _print(f"Key-term registry ({len(registry.required())} required): "
           + ", ".join(f"{e.canonical} ({e.category}, {e.sid})" for e in registry.required()))
    _print(f"written: {out}/stage1_passage.json, stage2_knowledge_map.json, stage3_key_term_registry.json")
    return 0


def cmd_build(cfg: AppConfig, args) -> int:
    try:
        rt, info = _runtime(cfg, args.backend, args.allow_template_fallback)
    except RuntimeUnavailable as exc:
        _print(f"MODEL UNAVAILABLE: {exc}\nUse --backend template for a no-LLM build, or "
               f"--allow-template-fallback (the report will say so).")
        return 3
    art = build(cfg, Path(args.passage), rt)
    out = cfg.outputs_dir
    dump_json({k: v.to_dict() for k, v in art.explanations.items()}, out / "stage4_explanations.json")
    dump_json(art.bank.to_dict(), out / "stage5_item_bank.json")
    dump_json({"backend": info, "timings": art.timings, "generation_calls": art.generation_calls,
               "stem_rewording": art.stem_rewording}, out / "stage_build_log.json")
    for line in _llm_status_lines(art, rt, info):
        _print(line)
    _print(f"Item bank: {art.bank.composition()}")
    _print(f"T_build {art.timings['t_build_s']} s  (preprocessing {art.timings['t_preprocessing_s']} s, "
           f"model {art.timings['t_model_generation_s']} s)")
    return 0


def _product(cfg: AppConfig) -> Dict[str, object]:
    return cfg.app.get("product", {}) or {}


def _run_session(cfg: AppConfig, art: BuildArtifacts, rt: ModelRuntime, provider, on_event=None):
    r = cfg.app["routing"]
    tracker = ConceptTracker([c.cid for c in art.km.concepts], r.get("enable_consolidated_state", False))
    ledger = ScoreLedger(cfg.app["scoring"]["bloom_weights"], CBM(cfg.app["scoring"]["cbm"]))
    repair = RepairEngine(art.km, art.registry, art.validator, rt, cfg.app["repair"].get("llm_wording", False))
    rule = {int(k): int(v) for k, v in r["placement_to_rung"].items()}
    sess = Session(art.passage, art.bank, art.explanations, tracker, ledger, repair, art.registry, rule,
                   int(r["step_down_unresolved_errors"]), cfg.app["safety_net"].get("enabled", True))
    sess.on_event = on_event
    result = sess.run(provider)
    return result, tracker, ledger


def cmd_session(cfg: AppConfig, args, end_to_end: bool = False) -> int:
    run_id = args.run_id or _run_id()
    prod = _product(cfg)
    learner = None
    if getattr(args, "learner", None):
        try:
            learner = lm.check_learner_id(args.learner)
        except lm.LearnerIdError as exc:
            _print(f"LEARNER ID ERROR: {exc}")
            return 2
    if getattr(args, "pack", None):
        # LEARN: model-free session replayed from a teacher-built lesson pack
        try:
            pack = read_pack(resolve_input(cfg, args.pack))
            if pack['payload'].get('ocr_verification') and not approved(pack):
                raise PackError('OCR lesson requires teacher approval. Run pack-review before a student session.')
            art = replay(cfg, pack)
        except PackError as exc:
            _print(f"LESSON PACK ERROR: {exc}")
            return 2
        rt = TemplateRuntime()
        rt.load()
        info = {"requested_backend": "lesson_pack", "backend": "lesson_pack (no model in session)", "fallback_used": False,
                "pack": str(args.pack), "pack_built_with": pack["payload"]["built_with"]["backend"],
                "pack_review": {k: pack["payload"]["review"][k]["status"] for k in REVIEWABLE}}
        if prod.get("warn_unapproved_pack", True) and not approved(pack):
            _print("WARNING: this lesson pack has not been reviewed by a teacher (run pack-review on the hub).")
    else:
        try:
            rt, info = _runtime(cfg, args.backend, args.allow_template_fallback)
        except RuntimeUnavailable as exc:
            _print(f"MODEL UNAVAILABLE: {exc}\nUse --backend template for a no-LLM run (clearly labelled), "
                   f"or --allow-template-fallback.")
            return 3
        art = build(cfg, Path(args.passage), rt)
    tagger = (lambda t: tag_text(t, art.passage, art.km)) if prod.get("source_tags", False) else None
    if args.answers:
        provider = scripted_provider(load_script(resolve_input(cfg, args.answers)))
        mode = f"scripted answers ({Path(args.answers).name})"
    else:
        provider = interactive_provider()
        mode = "interactive learner"
    if learner:
        mode += f" · learner {learner}"
    header = ["=" * 78, f"LEVEL BRIDGE STEM  run {run_id}   learner: {mode}", *_llm_status_lines(art, rt, info),
              f"Passage: {art.passage.word_count} words · registry {len(art.registry.required())} terms · "
              f"core types {art.km.type_counts()}", "=" * 78]
    on_event = None
    if not args.answers:
        for h in header:
            _print(h)
        _print("\nSUMMARY:\n" + art.explanations["summary"].text)

        def on_event(ev):  # live display for a real student: explanations, repairs and routing as they happen
            if ev["type"] in ("explain", "repair", "route", "bridge", "safety_net", "placement_result"):
                for line in render_event(ev, tagger):
                    _print(line)
    t0 = time.perf_counter()
    result, tracker, ledger = _run_session(cfg, art, rt, provider, on_event)
    t_session = time.perf_counter() - t0
    run_info = {"run_id": run_id, "learner": mode, "backend": info, "is_llm_inference": rt.is_llm,
                "llm_outputs_accepted": art.llm_outputs_accepted,
                "explanation_sources": {k: v.source for k, v in art.explanations.items()},
                "timings": {**art.timings, "t_session_s": round(t_session, 4),
                            "repair_latency": repair_latency_stats(result.repair_latencies_s)},
                "peak_rss_mb": round(peak_rss_mb(), 1), "passage_sha256": art.passage.sha256}
    report = build_report(art.km, tracker, ledger, result, run_info)
    out = cfg.outputs_dir
    dump_json(report, out / f"learning_report_{run_id}.json")
    dump_json(art.km.to_dict(), out / f"knowledge_map_{run_id}.json")
    dump_json(result.to_dict(), out / f"session_events_{run_id}.json")
    text = render_session(result, header if args.answers else [], tagger) + "\n\n" + render_report(report)
    written = [f"learning_report_{run_id}.json", f"knowledge_map_{run_id}.json", f"session_events_{run_id}.json",
               f"session_transcript_{run_id}.txt"]
    if learner and prod.get("learner_memory", True):
        record = lm.session_record(run_id, art, result, report)
        prof = lm.record_session(cfg.path(prod.get("learners_dir", "data/learners")), learner, record,
                                 consent=True if getattr(args, "consent", False) else None)
        pats = lm.patterns(prof)
        dump_json(pats, out / f"learner_patterns_{run_id}.json")
        written.append(f"learner_patterns_{run_id}.json")
        text += "\n\n" + lm.render_patterns(pats)
        if not prof.get("consent"):
            text += f"\n   consent flag NOT set: this profile stays on the device (add --consent to allow USB export)"
    (out / f"session_transcript_{run_id}.txt").write_text(text, encoding="utf-8")
    _print(text if args.answers else "\n" + text.split("\n\n", 1)[-1])
    _print(f"\nwritten: {out}/" + f", ".join(written))
    return 0


# ---------------------------------------------------------------------------- Teach · Learn · Improve
def cmd_pack_build(cfg: AppConfig, args) -> int:
    try:
        rt, info = _runtime(cfg, args.backend, args.allow_template_fallback)
    except RuntimeUnavailable as exc:
        _print(f"MODEL UNAVAILABLE: {exc}\nUse --backend template for a no-LLM pack (labelled), or --allow-template-fallback.")
        return 3
    info = {**info, "is_llm": rt.is_llm}
    art = build(cfg, Path(args.passage), rt)
    template_art = build(cfg, Path(args.passage), TemplateRuntime()) if rt.is_llm else art
    pack = make_pack(art, info, template_art)
    dump_json({k: v.to_dict() for k, v in art.explanations.items()}, cfg.outputs_dir / "stage4_explanations.json")
    dump_json({"backend": info, "timings": art.timings, "generation_calls": art.generation_calls,
               "stem_rewording": art.stem_rewording}, cfg.outputs_dir / "stage_build_log.json")
    label = lm.passage_label(art.km).replace(" ", "_")
    path = Path(args.out) if args.out else cfg.path(_product(cfg).get("packs_dir", "data/packs")) / \
        f"{label}_{art.passage.sha256[:8]}.lbpack.json"
    write_pack(pack, path)
    for line in _llm_status_lines(art, rt, info):
        _print(line)
    for line in review_lines(pack):
        _print(line)
    _print(f"T_build {art.timings['t_build_s']} s\nwritten: {path}\nnext: pack-review --pack {path}")
    return 0


def _read_multiline(prompt: str) -> str:
    _print(prompt + " (finish with an empty line)")
    lines = []
    while True:
        ln = input()
        if not ln.strip():
            break
        lines.append(ln)
    return "\n".join(lines)


def cmd_pack_review(cfg: AppConfig, args) -> int:
    path = resolve_input(cfg, args.pack)
    try:
        pack = read_pack(path)
    except PackError as exc:
        _print(f"LESSON PACK ERROR: {exc}")
        return 2
    decisions = []
    for kv in args.edit or []:
        kind, _, f = kv.partition("=")
        decisions.append((kind, "edit", resolve_input(cfg, f).read_text(encoding="utf-8")))
    decisions += [(k, "template", None) for k in (args.use_template or [])]
    decisions += [(k, "approve", None) for k in (args.approve or [])]
    if args.approve_all:
        decided = {d[0] for d in decisions}
        decisions += [(k, "approve", None) for k in REVIEWABLE if k not in decided]
    code = 0
    if decisions:
        for kind, action, text in decisions:
            try:
                apply_review(cfg, pack, kind, action, text)
                _print(f"   {kind}: {action} -> {pack['payload']['review'][kind]['status']}")
            except PackError as exc:
                _print(f"   {kind}: {exc}")
                code = 2
    else:  # interactive teacher review in the terminal
        for kind in REVIEWABLE:
            e = pack["payload"]["explanations"][kind]
            _print(f"\n=== {kind.upper()}  (source: {e['source']}) ===\n{e['text']}")
            while True:
                a = input("[a]pprove  [e]dit  [t]emplate  [s]kip: ").strip().lower()[:1]
                try:
                    if a == "a":
                        apply_review(cfg, pack, kind, "approve")
                    elif a == "t":
                        apply_review(cfg, pack, kind, "template")
                    elif a == "e":
                        apply_review(cfg, pack, kind, "edit", _read_multiline("Type the new text"))
                    elif a != "s":
                        continue
                    break
                except PackError as exc:
                    _print(f"   {exc}")
    write_pack(pack, path)
    for line in review_lines(pack):
        _print(line)
    _print(f"written: {path}")
    return code


def cmd_profile_show(cfg: AppConfig, args) -> int:
    store = cfg.path(args.store) if args.store else cfg.path(_product(cfg).get("learners_dir", "data/learners"))
    try:
        prof = lm.load_profile(store, args.learner)
    except lm.LearnerIdError as exc:
        _print(f"LEARNER ID ERROR: {exc}")
        return 2
    if prof is None:
        _print(f"no profile for {args.learner} in {store}")
        return 2
    _print(lm.render_patterns(lm.patterns(prof)))
    for s in prof["sessions"]:
        sc = s["scores"]
        _print(f"   {s['date']}  {s['session_id']:<22} {s['passage_label']:<12} start L{s['start_rung']}  "
               f"{' -> '.join(s['rung_path'])}  assessment {sc['assessment_credits']}/{sc['assessment_max']}  "
               f"errors: {', '.join(e['code'] for e in s['errors']) or '-'}")
    _print(f"   consent: {'yes' if prof.get('consent') else 'NO (export disabled)'}")
    return 0


def cmd_profile_export(cfg: AppConfig, args) -> int:
    prod = _product(cfg)
    out_dir = Path(args.out) if args.out else cfg.path(prod.get("usb_dir", "usb_export"))
    try:
        path = export_bundle(cfg.path(prod.get("learners_dir", "data/learners")), args.learner, out_dir)
    except (BundleError, lm.LearnerIdError) as exc:
        _print(f"EXPORT REFUSED: {exc}")
        return 2
    _print(f"written: {path}")
    return 0


def cmd_hub_import(cfg: AppConfig, args) -> int:
    prod = _product(cfg)
    files: List[Path] = [resolve_input(cfg, b) for b in (args.bundles or [])]
    if args.dir:
        files += sorted(resolve_input(cfg, args.dir).glob("*.lbprofile.json"))
    if not files:
        _print("no bundles given (pass files or --dir <usb folder>)")
        return 2
    hub = cfg.path(args.hub) if args.hub else cfg.path(prod.get("hub_dir", "data/hub"))
    res = import_bundles(files, hub)
    for r in res:
        _print(f"   {'OK  ' if r['ok'] else 'FAIL'} {Path(r['file']).name}: " +
               (f"{r['learner_id']} +{r['sessions_added']} new of {r['sessions_in_bundle']} sessions" if r["ok"] else r["error"]))
    dump_json(res, cfg.outputs_dir / f"hub_import_{_run_id()}.json")
    return 0 if all(r["ok"] for r in res) else 2


def cmd_gate_report(cfg: AppConfig, args) -> int:
    f = cfg.outputs_dir / "stage4_explanations.json"
    lf = cfg.outputs_dir / "stage_build_log.json"
    if args.rebuild or not f.exists():
        try:
            rt, info = _runtime(cfg, args.backend, args.allow_template_fallback)
        except RuntimeUnavailable as exc:
            _print(f"MODEL UNAVAILABLE: {exc}")
            return 3
        art = build(cfg, Path(args.passage), rt)
        dump_json({k: v.to_dict() for k, v in art.explanations.items()}, f)
        dump_json({"backend": info, "timings": art.timings}, lf)
        _print(f"(built now: {art.passage.source})")
    else:
        _print(f"(from the last build / pack-build: {f}; use --rebuild to build again)")
    exps = json.loads(f.read_text(encoding="utf-8"))
    backend = "?"
    if lf.exists():
        b = json.loads(lf.read_text(encoding="utf-8")).get("backend", {})
        backend = b.get("backend") or b.get("requested_backend") or "?"
    for line in trust_demo.gate_report(exps, backend):
        _print(line)
    return 0


def cmd_compare(cfg: AppConfig, args) -> int:
    try:
        rt, info = _runtime(cfg, args.backend, allow_fallback=False)
    except RuntimeUnavailable as exc:
        _print(f"MODEL UNAVAILABLE: {exc}\n'compare' needs the real model (it shows what the model does on its own).")
        return 3
    if not rt.is_llm:
        _print("'compare' needs the real model: the template backend has no AI to compare against.")
        return 2
    art = build(cfg, Path(args.passage), TemplateRuntime())   # Level Bridge side: deterministic, no model needed
    r = trust_demo.ai_alone(art, rt)
    for line in trust_demo.render_compare(r, rt.name):
        _print(line)
    out = cfg.outputs_dir / f"compare_{_run_id()}.json"
    dump_json({"backend": info, "passage": art.passage.source, **r}, out)
    _print(f"\nwritten: {out}")
    return 0


def cmd_portal(cfg: AppConfig, args) -> int:
    prod = _product(cfg)
    hub = cfg.path(args.hub) if args.hub else cfg.path(prod.get("hub_dir", "data/hub"))
    out = Path(args.out) if args.out else cfg.path(prod.get("portal_path", "outputs/cbs_portal.html"))
    summary = write_portal(hub, out)
    _print(f"CBS portal: {len(summary['students'])} students, {len(summary['passages'])} passages, "
           f"{len(summary['reteach'])} reteach suggestions")
    for r in summary["reteach"][:5]:
        _print(f"   {r['students']} of {r['of']}: {r['family']} on {r['passage']} -> reteach {', '.join(r['sids'])}")
    _print(f"written: {out}   (open it in the Pi's browser; no network needed)")
    return 0


def cmd_offline(cfg: AppConfig, args) -> int:
    rep = check_offline(args.backend or str(cfg.model.get("backend")), probe_network=not args.no_probe)
    dump_json(rep, cfg.outputs_dir / "offline_check.json")
    _print(json.dumps(rep, indent=2))
    if args.require_offline and not rep["offline"]:
        _print("FAIL: network is reachable; disable it first (see scripts/test_offline_mode.sh).")
        return 2
    return 0


def cmd_benchmark(cfg: AppConfig, args) -> int:
    run_id = args.run_id or _run_id()
    rt = create_runtime(cfg.model, lambda p: cfg.path(p), args.backend)
    b = cfg.app["benchmark"]
    try:
        summary = run_benchmark(cfg, Path(args.passage), rt, args.warmup if args.warmup is not None else b["warmup_runs"],
                                args.runs or b["measured_runs"], _PROCESS_START, cfg.outputs_dir, run_id)
    except RuntimeUnavailable as exc:
        _print(f"MODEL UNAVAILABLE: {exc}  (no benchmark numbers produced)")
        return 3
    _print(json.dumps({k: v for k, v in summary.items() if k != "runs"}, indent=2, default=str))
    _print(f"written: {cfg.outputs_dir}/benchmark_{run_id}.json and .csv")
    return 0


# ---------------------------------------------------------------------------- parser
def cmd_ocr_ui(cfg, args):
    if not cfg.app.get('ocr', {}).get('enabled', False):
        _print('OCR disabled: enable ocr.enabled in config/config.yaml.')
        return 2
    if args.host not in ('127.0.0.1', 'localhost', '::1') and not args.allow_lan:
        _print('LAN binding requires --allow-lan. Use only a trusted local network.')
        return 2
    from .ocr.web import create_app
    create_app(cfg).run(host=args.host, port=args.port, debug=False, threaded=True, use_reloader=False)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="level-bridge", description="Level Bridge STEM – offline adaptive learning assistant")
    p.add_argument("--root", help="project root (default: auto-detect / $LB_ROOT)")
    p.add_argument("--model-config", help="alternative model_config.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser('ocr-ui', help='offline textbook capture and human OCR review')
    sp.add_argument('--host', default='127.0.0.1')
    sp.add_argument('--port', type=int, default=5000)
    sp.add_argument('--allow-lan', action='store_true', help='explicitly enable LAN binding on a trusted network')

    def common(sp, backend=True, passage=True):
        if backend:
            sp.add_argument("--backend", choices=["executorch_runner", "llama_main", "template"],
                            help="override config backend")
        if passage:
            sp.add_argument("--passage", default=DEFAULT_PASSAGE)
        return sp

    common(sub.add_parser("check-env", help="dependency/version report"), backend=False, passage=False)
    common(sub.add_parser("check-model", help="model presence, checksum and load test"), passage=False)
    sp = common(sub.add_parser("infer", help="raw inference test"), passage=False)
    sp.add_argument("--prompt", default="In one sentence, what is speed?")
    sp.add_argument("--repeat", type=int, default=1)
    sp.add_argument("--max-new-tokens", type=int, default=64)
    common(sub.add_parser("process", help="passage analysis stages"), backend=False)
    sp = common(sub.add_parser("build", help="explanations + item bank"))
    sp.add_argument("--allow-template-fallback", action="store_true")
    for name in ("session", "demo"):
        sp = common(sub.add_parser(name, help="learning session" if name == "session" else "end-to-end run"))
        sp.add_argument("--answers", help="scripted answers JSON (omit for interactive)")
        sp.add_argument("--allow-template-fallback", action="store_true")
        sp.add_argument("--run-id")
        sp.add_argument("--pack", help="LEARN: run from a lesson pack (no model call)")
        sp.add_argument("--learner", help="IMPROVE: pseudonymous learner ID, e.g. STU-7F3A (never a name)")
        sp.add_argument("--consent", action="store_true", help="record that parental consent was given (allows USB export)")
    sp = common(sub.add_parser("pack-build", help="TEACH: build a lesson pack on the hub"))
    sp.add_argument("--allow-template-fallback", action="store_true")
    sp.add_argument("--out")
    sp = sub.add_parser("pack-review", help="TEACH: teacher review of a lesson pack")
    sp.add_argument("--pack", required=True)
    sp.add_argument("--approve-all", action="store_true")
    sp.add_argument("--approve", nargs="*", choices=list(REVIEWABLE))
    sp.add_argument("--use-template", nargs="*", choices=list(REVIEWABLE))
    sp.add_argument("--edit", nargs="*", help="KIND=FILE, e.g. l1=my_l1.txt")
    sp = sub.add_parser("profile-show", help="IMPROVE: learner memory and patterns")
    sp.add_argument("--learner", required=True)
    sp.add_argument("--store", help="profile folder (default: product.learners_dir)")
    sp = sub.add_parser("profile-export", help="IMPROVE: checksummed bundle for USB")
    sp.add_argument("--learner", required=True)
    sp.add_argument("--out", help="folder, e.g. the mounted USB drive")
    sp = sub.add_parser("hub-import", help="IMPROVE: verify and merge bundles on the hub")
    sp.add_argument("bundles", nargs="*")
    sp.add_argument("--dir", help="import every *.lbprofile.json in this folder")
    sp.add_argument("--hub")
    sp = common(sub.add_parser("gate-report", help="DEMO: model drafts accepted / rejected by the gate"))
    sp.add_argument("--rebuild", action="store_true")
    sp.add_argument("--allow-template-fallback", action="store_true")
    common(sub.add_parser("compare", help="DEMO: AI alone vs Level Bridge on the same passage"))
    sp = sub.add_parser("portal", help="IMPROVE: write the offline CBS portal page")
    sp.add_argument("--hub")
    sp.add_argument("--out")
    sp = common(sub.add_parser("offline-check", help="verify offline operation"), passage=False)
    sp.add_argument("--require-offline", action="store_true")
    sp.add_argument("--no-probe", action="store_true", help="skip DNS/TCP probes")
    sp = common(sub.add_parser("benchmark", help="warm-up + measured runs"))
    sp.add_argument("--warmup", type=int)
    sp.add_argument("--runs", type=int)
    sp.add_argument("--run-id")
    return p


COMMANDS = {"check-env": cmd_check_env, "check-model": cmd_check_model, "infer": cmd_infer, "process": cmd_process,
            "build": cmd_build, "session": cmd_session, "demo": cmd_session, "offline-check": cmd_offline,
            "benchmark": cmd_benchmark, "pack-build": cmd_pack_build, "pack-review": cmd_pack_review,
            "profile-show": cmd_profile_show, "profile-export": cmd_profile_export, "hub-import": cmd_hub_import,
            "portal": cmd_portal, "gate-report": cmd_gate_report, "compare": cmd_compare}


def main(argv: Optional[List[str]] = None) -> int:
    COMMANDS['ocr-ui'] = cmd_ocr_ui
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(Path(args.root) if args.root else None, args.model_config)
    except FileNotFoundError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2
    run_id = getattr(args, "run_id", None) or _run_id()
    log_path = setup_logging(cfg.logs_dir, f"{args.cmd}_{run_id}", args.verbose)
    log.info("start", extra={"data": {"cmd": args.cmd, "argv": argv or sys.argv[1:]}})
    try:
        code = COMMANDS[args.cmd](cfg, args)
    except PassageError as exc:
        print(f"PASSAGE ERROR: {exc}", file=sys.stderr)
        code = 2
    except Exception as exc:  # unexpected – record full traceback in the error log
        err = cfg.logs_dir / f"error_{run_id}.log"
        err.write_text(traceback.format_exc(), encoding="utf-8")
        print(f"ERROR: {type(exc).__name__}: {exc}\n(traceback: {err})", file=sys.stderr)
        code = 4
    log.info("end", extra={"data": {"cmd": args.cmd, "exit_code": code, "log": str(log_path)}})
    return code


if __name__ == "__main__":
    sys.exit(main())
