"""IMPROVE (report Section 7.5): session timeline -> learner profile -> error patterns.

A learner is identified only by a pseudonymous ID such as ``STU-7F3A``; names, ages,
schools and contact details are never stored. Every profile carries a consent flag,
and :mod:`profile_bundle` refuses to export a profile without it.

The profile records what the system *observed*. It is not a diagnosis of the student
and not evidence of learning.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

PROFILE_FORMAT = "level-bridge-learner-profile/1"
LEARNER_ID_RE = re.compile(r"^STU-[A-Z0-9]{4,8}$")

# error code -> error family (report Table 7.4 plus the MCQ distractor codes)
ERROR_FAMILY = {
    "wrong_operation_multiply": "wrong_operation",
    "wrong_operation_add": "wrong_operation",
    "inverted_formula": "inverted_ratio",
    "ignored_variable": "ignored_variable",
    "missing_variable": "ignored_variable",
    "unit_not_converted": "unit_conversion",
    "unit_error": "unit_conversion",
    "dimension_confusion": "unit_conversion",
    "reversed_relation": "relationship_direction",
    "no_change": "relationship_direction",
    "term_confusion": "term_confusion",
}

# error family -> the prerequisite skill to revise (report Section 7.5)
PREREQUISITE = {
    "wrong_operation": "formula direction: which quantity is divided by which",
    "inverted_ratio": "the meaning of 'per' (output per unit of the second quantity)",
    "ignored_variable": "using every quantity the question gives",
    "unit_conversion": "converting units before substituting",
    "relationship_direction": "what happens to the output when one input changes and the other is fixed",
    "term_confusion": "telling apart similar terms (reread the definition sentence)",
    "incorrect": "rereading the source sentence",
}


class LearnerIdError(ValueError):
    """The learner ID is not a pseudonymous ID (e.g. it looks like a name)."""


def check_learner_id(learner_id: str) -> str:
    lid = (learner_id or "").strip().upper()
    if not LEARNER_ID_RE.match(lid):
        raise LearnerIdError(f"'{learner_id}' is not a pseudonymous learner ID. Use the form STU-7F3A "
                             f"(4-8 letters/digits); never a student's name.")
    return lid


def family(code: Optional[str]) -> Optional[str]:
    if not code or code == "invalid_response":
        return None
    return ERROR_FAMILY.get(code, "incorrect")


def passage_label(km) -> str:
    """Short label for a passage: the primary formula's output, else the first concept."""
    f = km.primary_formula()
    if f is not None:
        return f.output
    return km.concepts[0].label if km.concepts else "passage"


# ------------------------------------------------------------------ session record
def session_record(session_id: str, art, result, report: Dict[str, object]) -> Dict[str, object]:
    """Ordered timeline of one session plus the facts the profile needs (report Section 7.3)."""
    sentences = {s.sid: s.text for s in art.passage.sentences}
    timeline: List[Dict[str, object]] = []
    errors: List[Dict[str, object]] = []
    for n, ev in enumerate(result.events, start=1):
        t = ev["type"]
        if t in ("item", "second_chance"):
            item = art.bank.by_id(ev["item"])
            rec = {"n": n, "type": t, "item": ev["item"], "concept": item.concept_id,
                   "level": item.cognitive_level, "answer": ev["answer"], "certainty": ev["certainty"],
                   "correct": ev["correct"], "error_code": ev.get("error_code"), "state": ev["state"],
                   "source_sids": item.source_sids}
            if t == "item":
                rec.update(credits=ev["credits"], cbm=ev["cbm"])
            else:
                rec.update(recovery=ev["recovery"], cbm=ev["cbm"])
            timeline.append(rec)
            fam = family(ev.get("error_code"))
            if not ev["correct"] and fam:
                errors.append({"item": ev["item"], "phase": t, "concept": item.concept_id, "code": ev.get("error_code"),
                               "family": fam, "certainty": ev["certainty"], "source_sids": item.source_sids,
                               "source_text": [sentences.get(s, "") for s in item.source_sids][:1]})
        elif t == "placement_result":
            timeline.append({"n": n, "type": t, "score": ev["score"], "out_of": ev["out_of"], "start_rung": ev["start_rung"]})
        elif t == "repair":
            timeline.append({"n": n, "type": t, "item": ev["item"], "error_code": ev.get("error_code"), "source": ev["source"]})
        elif t == "route":
            timeline.append({"n": n, "type": t, "rule": ev["rule"], "decision": ev["decision"], "to_rung": ev.get("to_rung")})
        elif t == "bridge" and ev.get("available"):
            timeline.append({"n": n, "type": t, "sids": ev["extract_sids"], "verbatim": ev["verbatim"]})
        elif t == "safety_net":
            timeline.append({"n": n, "type": t, "concept": ev["concept"]})
    f = art.km.primary_formula()
    fsid = art.km.formulas[0].sid if art.km.formulas else None
    return {
        "session_id": session_id,
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "passage_sha256": art.passage.sha256,
        "passage_label": passage_label(art.km),
        "formula": f.text if f else None,
        "formula_sid": fsid,
        "formula_sentence": sentences.get(fsid) if fsid else None,
        "start_rung": result.placement.get("start_rung"),
        "rung_path": [f"L{r}" for r in result.rung_path],
        "end_reason": result.end_reason,
        "bridge_reached": result.bridge_reached,
        "scores": report["scores"],
        "concepts": [{"cid": c["cid"], "label": c["label"], "state": c["state"], "assessed": c["assessed"]}
                     for c in report["concepts"]],
        "errors": errors,
        "timeline": timeline,
    }


# ------------------------------------------------------------------ profile store
def new_profile(learner_id: str, consent: bool) -> Dict[str, object]:
    now = time.strftime("%Y-%m-%d %H:%M")
    return {"format": PROFILE_FORMAT, "learner_id": check_learner_id(learner_id), "consent": bool(consent),
            "created": now, "updated": now, "sessions": []}


def profile_path(store: Path, learner_id: str) -> Path:
    return Path(store) / f"{check_learner_id(learner_id)}.json"


def load_profile(store: Path, learner_id: str) -> Optional[Dict[str, object]]:
    p = profile_path(store, learner_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save_profile(store: Path, profile: Dict[str, object]) -> Path:
    store = Path(store)
    store.mkdir(parents=True, exist_ok=True)
    p = profile_path(store, profile["learner_id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)   # atomic on the same filesystem: a power cut never leaves half a profile
    return p


def merge_sessions(profile: Dict[str, object], sessions: List[Dict[str, object]]) -> int:
    """Add sessions not already present (by session_id). Returns the number added."""
    have = {s["session_id"] for s in profile["sessions"]}
    added = 0
    for s in sessions:
        if s["session_id"] not in have:
            profile["sessions"].append(s)
            have.add(s["session_id"])
            added += 1
    profile["sessions"].sort(key=lambda s: (s.get("date", ""), s["session_id"]))
    profile["updated"] = time.strftime("%Y-%m-%d %H:%M")
    return added


def record_session(store: Path, learner_id: str, record: Dict[str, object], consent: Optional[bool] = None) -> Dict[str, object]:
    """Append one session to the learner's profile (created on first use) and save it."""
    prof = load_profile(store, learner_id) or new_profile(learner_id, bool(consent))
    if consent is not None:
        prof["consent"] = bool(consent)
    merge_sessions(prof, [record])
    save_profile(store, prof)
    return prof


# ------------------------------------------------------------------ patterns
def patterns(profile: Dict[str, object]) -> Dict[str, object]:
    """Recurring error families, confidence pattern and latest concept states (report Section 7.5)."""
    by_family: Dict[str, set] = defaultdict(set)
    counts: Counter = Counter()
    confident_errors = 0
    errors_total = 0
    for s in profile["sessions"]:
        for e in s["errors"]:
            by_family[e["family"]].add(s["passage_label"])
            counts[e["family"]] += 1
            errors_total += 1
            if int(e.get("certainty", 0)) == 3:
                confident_errors += 1
    passages = sorted({s["passage_label"] for s in profile["sessions"]})
    recurring = []
    for fam, ps in sorted(by_family.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if len(ps) >= 2:
            recurring.append({"family": fam, "passages": sorted(ps), "count": counts[fam],
                              "revise": PREREQUISITE.get(fam, PREREQUISITE["incorrect"])})
    latest: Dict[str, Dict[str, str]] = {}
    for s in profile["sessions"]:
        for c in s["concepts"]:
            if c["assessed"]:
                latest[f"{s['passage_label']}:{c['label']}"] = {"passage": s["passage_label"], "concept": c["label"],
                                                                 "state": c["state"]}
    totals = Counter()
    for s in profile["sessions"]:
        sc = s["scores"]
        totals["assessment"] += sc["assessment_credits"]
        totals["assessment_max"] += sc["assessment_max"]
        totals["recovery"] += sc["recovery_credits"]
        totals["cbm"] += sc["cbm_total"]
        totals["cbm_max"] += sc["cbm_max"]
    return {"learner_id": profile["learner_id"], "sessions": len(profile["sessions"]), "passages": passages,
            "recurring": recurring, "error_families": dict(counts), "errors_total": errors_total,
            "confident_errors": confident_errors, "latest_states": list(latest.values()), "totals": dict(totals)}


def render_patterns(p: Dict[str, object]) -> str:
    lines = [f"LEARNER MEMORY  {p['learner_id']}   sessions {p['sessions']}   passages: {', '.join(p['passages']) or '-'}",
             f"   credits (all sessions): assessment {p['totals'].get('assessment', 0)} / {p['totals'].get('assessment_max', 0)}"
             f" | recovery +{p['totals'].get('recovery', 0)} | CBM {p['totals'].get('cbm', 0):+d} / {p['totals'].get('cbm_max', 0)}",
             f"   errors: {p['errors_total']} (confident errors at certainty 3: {p['confident_errors']})"]
    if p["recurring"]:
        for r in p["recurring"]:
            lines.append(f"   RECURRING PATTERN: {r['family']} on {len(r['passages'])} passages ({', '.join(r['passages'])})"
                         f" -> revise {r['revise']}")
    else:
        lines.append("   no recurring pattern yet (a pattern needs the same error family on two different passages)")
    lines.append("   (observed behaviour only - not a diagnosis and not evidence of learning)")
    return "\n".join(lines)
