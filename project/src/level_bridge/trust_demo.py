"""Live-round demo: make the trust story visible (docs/PRODUCT_DEMO.md).

``gate-report``  shows each model draft, whether the validation gate accepted it, and why not.
``compare``      asks the same on-device model to answer the quiz and summarise the passage ON ITS OWN
                 (the way a plain "summary + quiz" app uses it), then puts the result next to
                 Level Bridge's Python-computed answers and the gate's checks.

Nothing here changes the learning loop. Every verdict is computed by the same Python code as the
session; the model's raw output is shown exactly as returned.
"""

from __future__ import annotations

import re
import sys
from typing import Dict, List, Optional

from .misconception_detector import evaluate
from .quantity_parser import normalise_unit

_TTY = sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def red(t: str) -> str:
    return _c(t, "31;1")


def green(t: str) -> str:
    return _c(t, "32;1")


def dim(t: str) -> str:
    return _c(t, "2")


def _short(text: str, n: int = 320) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


# ------------------------------------------------------------------ gate report
def gate_report(explanations: Dict[str, Dict[str, object]], backend: str) -> List[str]:
    """``explanations`` as written to stage4_explanations.json (dicts)."""
    out = [f"VALIDATION GATE REPORT   backend: {backend}",
           "Every model draft is checked: key terms, formula, only the passage's numbers and units, "
           "relationship direction."]
    for kind in ("summary", "l1", "l2"):
        e = explanations.get(kind)
        if not e:
            continue
        out.append("")
        out.append(f"=== {kind.upper()} ===")
        attempts = e.get("attempts") or []
        if not attempts:
            out.append(dim("   no model drafts (template backend - no LLM inference)"))
        for a in attempts:
            v = a.get("validation") or {}
            if not a.get("generation_ok"):
                out.append(red(f"   attempt {a['number']}: GENERATION FAILED") + f"  ({a.get('error')})")
                continue
            passed = bool(v.get("passed"))
            head = green(f"   attempt {a['number']}: ACCEPTED") if passed else red(f"   attempt {a['number']}: REJECTED")
            out.append(f"{head}   ({a.get('wall_time_s', 0):.1f} s, {a.get('generated_tokens') or '?'} tokens)")
            if a.get("draft"):
                out.append(dim(f"      model draft: \"{_short(a['draft'])}\""))
            for c in v.get("checks", []):
                if not c.get("passed") and c.get("severity", "error") == "error":
                    out.append(red(f"      ✗ {c['name']}: {c.get('details', '')}"))
        src = e.get("source")
        if src == "template" and not attempts:
            src = "template_no_model"
        final = {"template_no_model": "validated template (no model in this run)","llm": green("model text, accepted on the first draft"),
                 "llm_retry": green("model text, accepted after one retry"),
                 "template": "validated template (the model's drafts did not pass)",
                 "teacher_edited": green("teacher-edited text that passed the gate")}.get(src, src)
        out.append(f"   -> reached the student: {final}   validated={e.get('validated')}")
    return out


# ------------------------------------------------------------------ AI alone vs Level Bridge
_NUM_UNIT = re.compile(r"(-?\d+(?:\.\d+)?)\s*([A-Za-zΩµ][A-Za-z0-9Ωµ²³/·]*(?:\s*per\s*[a-z]+)?)?")


def extract_answer(text: str) -> Optional[str]:
    """Final number (with unit if recognisable) from free model text, e.g. 'speed = 180 ÷ 3 = 60 km/h.' -> '60 km/h'."""
    t = (text or "").replace(",", "")
    hits = list(_NUM_UNIT.finditer(t))
    if not hits:
        return None
    eq = [h for h in hits if "=" in t[max(0, h.start() - 3):h.start()]]
    h = eq[-1] if eq else hits[-1]
    num, unit = h.group(1), (h.group(2) or "").strip().rstrip(".")
    u = normalise_unit(unit) if unit else None
    return f"{num} {u}" if u else num


def _letter(text: str, valid: List[str]) -> Optional[str]:
    m = re.search(r"\b([A-D])\b", text or "")
    return m.group(1) if m and m.group(1) in valid else None


def ai_alone(art, runtime, max_new_tokens: int = 64) -> Dict[str, object]:
    items = []
    for it in art.bank.items:
        if it.response_type == "numeric" and it.kind in ("assessment", "second_chance", "transfer"):
            stem = it.stem.replace("(type a number)", "").strip()
            prompt = f"Solve this problem. Reply with only the final answer as a number and unit.\n{stem}"
            res = runtime.generate(prompt, max_new_tokens)
            raw = res.text if res.ok else f"(no output: {res.error})"
            ans = extract_answer(raw) if res.ok else None
            ev = evaluate(it, ans) if ans else None
            items.append({"item": it.item_id, "question": stem, "ai_raw": raw.strip(), "ai_answer": ans,
                          "ai_correct": bool(ev and ev.correct),
                          "ai_error": (ev.error_code if ev and not ev.correct else None),
                          "level_bridge": it.numeric["solution"]["answer_text"],
                          "wall_time_s": round(res.wall_time_s, 2)})
        elif it.response_type == "mcq" and it.kind == "assessment" and it.knowledge_type == "quantitative":
            opts = "\n".join(f"{o.key}) {o.text}" for o in it.options)
            prompt = f"Answer with only the letter of the correct option.\n{it.stem}\n{opts}"
            res = runtime.generate(prompt, 16)
            raw = res.text if res.ok else f"(no output: {res.error})"
            letter = _letter(raw, [o.key for o in it.options]) if res.ok else None
            ok = letter == it.answer_key
            correct_text = it.correct_option().text
            items.append({"item": it.item_id, "question": it.stem, "ai_raw": raw.strip(), "ai_answer": letter,
                          "ai_correct": ok, "ai_error": None if ok else "wrong option",
                          "level_bridge": f"{it.answer_key}) {correct_text}", "wall_time_s": round(res.wall_time_s, 2)})
    sres = runtime.generate("Summarise this passage in three short sentences for a Class 7 student.\n\n"
                            + art.passage.text, 160)
    summary = {"ai_raw": sres.text.strip() if sres.ok else f"(no output: {sres.error})", "checks": []}
    if sres.ok:
        rep = art.validator.validate(sres.text, "summary")
        summary["passed_gate"] = rep.passed
        summary["checks"] = [{"name": c.name, "details": c.details} for c in rep.failures()]
    return {"items": items, "summary": summary,
            "ai_correct": sum(1 for i in items if i["ai_correct"]), "total": len(items)}


def render_compare(r: Dict[str, object], backend: str) -> List[str]:
    out = [f"AI ALONE vs LEVEL BRIDGE   (same on-device model: {backend})",
           "Left: the model answers on its own, like a plain summary-and-quiz app. "
           "Right: Level Bridge computes the answer in Python, with units.", ""]
    for i in r["items"]:
        mark = green("✓") if i["ai_correct"] else red("✗")
        why = f"  [{i['ai_error']}]" if i.get("ai_error") else ""
        out.append(f"{i['item']:<4} {_short(i['question'], 110)}")
        out.append(f"     AI alone:      {i['ai_answer'] or '(no answer found)'} {mark}{why}"
                   + dim(f"   raw: \"{_short(i['ai_raw'], 70)}\""))
        out.append(f"     Level Bridge:  {i['level_bridge']} {green('✓')}  (computed by Python; same result on every run)")
    out.append("")
    out.append(f"AI alone: {r['ai_correct']} / {r['total']} correct.   Level Bridge: {r['total']} / {r['total']} "
               f"(answers are computed, not generated).")
    s = r["summary"]
    out.append("")
    out.append("AI-alone summary, put through our validation gate:")
    out.append(dim(f"   \"{_short(s['ai_raw'], 400)}\""))
    if s.get("checks"):
        for c in s["checks"]:
            out.append(red(f"   ✗ {c['name']}: {c['details']}"))
        out.append("   -> Level Bridge would NOT show this to a student (retry, then a validated template).")
    elif "passed_gate" in s:
        out.append(green("   ✓ passed the gate this time") + " - but only the gate tells you that; a plain app cannot.")
    return out
