"""Final learning report (JSON) and the human-readable terminal rendering."""

from __future__ import annotations

import json
import textwrap
from typing import Dict, List, Optional

from .adaptive_router import SessionResult
from .concept_states import ConceptTracker, State
from .knowledge_map import KnowledgeMap
from .scoring import ScoreLedger

W = 100


def build_report(km: KnowledgeMap, tracker: ConceptTracker, ledger: ScoreLedger, session: SessionResult,
                 run_info: Dict[str, object]) -> Dict[str, object]:
    """Machine-readable learning report."""
    concepts = []
    for c in km.concepts:
        st = tracker.states[c.cid]
        concepts.append({"cid": c.cid, "label": c.label, "knowledge_type": c.knowledge_type, "sids": c.sids,
                         "state": st.value, "assessed": st != State.LEARNING, "history": tracker.history[c.cid],
                         "flags": tracker.flags[c.cid]})
    return {
        "run": run_info,
        "placement": session.placement,
        "rung_path": [f"L{r}" for r in session.rung_path],
        "end_reason": session.end_reason,
        "bridge_reached": session.bridge_reached,
        "concepts": concepts,
        "scores": ledger.summary(),
        "teacher_notes": session.teacher_notes,
        "state_model_note": "Provisional = one correct assessment; Repaired is not mastery; Transferred is initial "
                            "evidence only; Consolidated (multiple independent assessments) is proposed, not implemented.",
    }


def _wrap(text: str, indent: str = "    ") -> List[str]:
    return textwrap.wrap(text, W, initial_indent=indent, subsequent_indent=indent) or [indent]


def render_event(ev: Dict[str, object], tagger=None) -> List[str]:
    """Render one session event (used live in interactive mode and for the transcript)."""
    tmp = SessionResult({}, [ev], [], "", False, [], [], [])
    return render_session(tmp, [], tagger).splitlines()


def render_session(session: SessionResult, header: List[str], tagger=None) -> str:
    """Render the session events like the report's demonstration output.

    ``tagger`` (optional) adds source tags such as [S3] to L1/L2 explanation sentences.
    """
    out: List[str] = list(header)
    for ev in session.events:
        t = ev["type"]
        if t == "placement_item":
            out.append(f"  {ev['item']} [{ev['probe']}] {ev['stem']}  -> {ev['answer']} {'✓' if ev['correct'] else '✗'}")
        elif t == "placement_result":
            out.append(f"PLACEMENT  {ev['score']}/{ev['out_of']} -> R1: start at L{ev['start_rung']}")
        elif t == "explain":
            out.append(f"--- L{ev['rung']} explanation ({ev['source']}) ---")
            text = tagger(ev["text"]) if (tagger and ev["source"] != "original") else ev["text"]
            for line in text.splitlines():
                out.extend(_wrap(line, "    "))
        elif t in ("item", "second_chance"):
            tag = "2ND CHANCE" if t == "second_chance" else ev["item"]
            lvl = ev.get("level") or ""
            if t == "item":
                out.append(f"{tag} [L{ev['rung']} · {lvl.upper()} · {ev['ktype']} · {ev['concept']}] {ev['stem']}")
            else:
                out.append(f"   {tag} {ev['item']}: {ev['stem']}")
            if ev.get("options"):
                out.append("      " + "   ".join(f"{k}) {v}" for k, v in ev["options"]))
            mark = "✓" if ev["correct"] else "✗"
            extra = (f"credits +{ev['credits']}" if t == "item" else f"recovery +{ev['recovery']}") + f"  CBM {ev['cbm']:+d}"
            code = f" [{ev['error_code']}]" if ev.get("error_code") else ""
            out.append(f"      answer {ev['answer']} · certainty {ev['certainty']} -> {mark} {ev['state'].upper()}{code}   {extra}")
        elif t == "repair":
            out.append(f"   REPAIR ({ev['source']}, {ev['latency_s']*1000:.1f} ms)")
            for line in ev["lines"]:
                out.extend(_wrap(line, "      "))
        elif t == "safety_net":
            out.append(f"   SAFETY NET for {ev['concept']}")
            if ev.get("word_card"):
                wc = ev["word_card"]
                out.extend(_wrap(f"word card: {wc['term']} – {wc['meaning']} ({wc['source']})", "      "))
            for line in ev.get("worked_example") or []:
                out.append(f"      {line}")
            out.append(f"      {ev['teacher_note']}")
        elif t == "route":
            if ev["decision"] == "climb":
                out.append(f"{ev['rule']}  {ev['reason']} -> climb to L{ev['to_rung']}")
            elif ev["decision"] == "step_down":
                out.append(f"{ev['rule']}  {ev['reason']} -> step down to L{ev['to_rung']}")
            else:
                out.append(f"{ev['rule']}  {ev['decision']}: {ev['reason']}")
        elif t == "bridge":
            if ev.get("available"):
                out.append(f"BRIDGE  {', '.join(ev['extract_sids'])} exactly as printed (verbatim={ev['verbatim']}):")
                out.extend(_wrap(f"\"{ev['extract']}\"", "    "))
    return "\n".join(out)


def render_report(report: Dict[str, object]) -> str:
    s = report["scores"]
    run = report.get("run", {})
    lines = ["LEARNING REPORT",
             f"   backend: {run.get('backend', {}).get('backend', '?')}   LLM inference: "
             f"{'yes' if run.get('is_llm_inference') else 'NO (templates)'}   "
             f"LLM outputs accepted: {run.get('llm_outputs_accepted', 0)}",
             f"   path: {' -> '.join(report['rung_path'])}   end: {report['end_reason']}"]
    for c in report["concepts"]:
        st = c["state"] if c["assessed"] else "not assessed"
        fl = f"  ({'; '.join(c['flags'])})" if c["flags"] else ""
        label = c["label"] if len(c["label"]) <= 46 else c["label"][:45] + "…"
        lines.append(f"   {c['cid']:<3} {label:<46} {st}{fl}")
    lines.append(f"   Assessment {s['assessment_credits']} / {s['assessment_max']} | Recovery +{s['recovery_credits']} "
                 f"(outside maximum) | Total earned {s['total_earned']} | CBM {s['cbm_total']:+d} / {s['cbm_max']}")
    for n in report["teacher_notes"]:
        lines.append(f"   {n}")
    return "\n".join(lines)


def dump_json(obj, path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=str)
