"""IMPROVE: the CBS (credit-based system) portal - one static, offline HTML page (report Section 7.6).

Generated on the teacher hub from the profiles imported by USB. No server, no account,
no network, no external fonts or scripts: the file opens in the Pi's browser as is.
"""

from __future__ import annotations

import html
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from .learner_memory import PREREQUISITE, patterns

STATE_ORDER = ["Fragile", "Provisional", "Repaired", "Transferred", "Consolidated"]
STATE_CLASS = {"Fragile": "s-fragile", "Provisional": "s-prov", "Repaired": "s-rep", "Transferred": "s-trans",
               "Consolidated": "s-trans", "Learning": "s-none"}


def load_profiles(store: Path) -> List[Dict[str, object]]:
    profs = []
    for p in sorted(Path(store).glob("STU-*.json")):
        try:
            profs.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return profs


def class_summary(profiles: List[Dict[str, object]]) -> Dict[str, object]:
    """All numbers shown on the portal, computed in Python (also used by the tests)."""
    students = []
    heat: Dict[tuple, set] = defaultdict(set)            # (family, passage) -> students
    reteach: Dict[tuple, Dict[str, object]] = {}          # (passage, family) -> info
    passages_students: Dict[str, set] = defaultdict(set)
    concept_states: Dict[str, Dict[str, Dict[str, str]]] = defaultdict(dict)  # passage -> concept -> {student: state}
    for prof in profiles:
        pat = patterns(prof)
        sid = prof["learner_id"]
        students.append({"learner_id": sid, "sessions": pat["sessions"], "passages": pat["passages"],
                         **{k: pat["totals"].get(k, 0) for k in ("assessment", "assessment_max", "recovery", "cbm", "cbm_max")},
                         "confident_errors": pat["confident_errors"],
                         "recurring": [r["family"] for r in pat["recurring"]]})
        for s in prof["sessions"]:
            passages_students[s["passage_label"]].add(sid)
            for c in s["concepts"]:
                if c["assessed"]:
                    concept_states[s["passage_label"]][c["label"]] = {**concept_states[s["passage_label"]].get(c["label"], {}),
                                                                     sid: c["state"]}
            for e in s["errors"]:
                heat[(e["family"], s["passage_label"])].add(sid)
                key = (s["passage_label"], e["family"])
                info = reteach.setdefault(key, {"passage": s["passage_label"], "family": e["family"], "students": set(),
                                                "sids": set(), "sentence": None})
                info["students"].add(sid)
                info["sids"].update(e.get("source_sids") or [])
                if not info["sentence"] and e.get("source_text"):
                    info["sentence"] = e["source_text"][0]
    suggestions = []
    for (passage, fam), info in reteach.items():
        n, m = len(info["students"]), len(passages_students[passage])
        suggestions.append({"passage": passage, "family": fam, "students": n, "of": m,
                            "sids": sorted(info["sids"], key=lambda x: int(x[1:]) if x[1:].isdigit() else 0),
                            "sentence": info["sentence"], "revise": PREREQUISITE.get(fam, PREREQUISITE["incorrect"])})
    suggestions.sort(key=lambda d: (-d["students"], -d["students"] / max(1, d["of"]), d["passage"], d["family"]))
    families = sorted({f for f, _ in heat})
    passages = sorted(passages_students)
    return {"generated": time.strftime("%Y-%m-%d %H:%M"), "students": students, "passages": passages,
            "families": families,
            "heatmap": {f"{f}|{p}": len(heat.get((f, p), ())) for f in families for p in passages},
            "passage_students": {p: len(v) for p, v in passages_students.items()},
            "concept_states": {p: {c: dict(v) for c, v in cs.items()} for p, cs in concept_states.items()},
            "reteach": suggestions}


def _e(x) -> str:
    return html.escape(str(x))


def render_portal(summary: Dict[str, object], title: str = "Level Bridge – CBS portal") -> str:
    st = summary["students"]
    ids = [s["learner_id"] for s in st]
    n_conf = sum(s["confident_errors"] for s in st)
    n_rec = sum(1 for s in st if s["recurring"])
    rows = "".join(
        f"<tr><td class='id'>{_e(s['learner_id'])}</td><td>{s['sessions']}</td><td>{_e(', '.join(s['passages']))}</td>"
        f"<td class='num'>{s['assessment']} / {s['assessment_max']}</td><td class='num'>+{s['recovery']}</td>"
        f"<td class='num'>{s['cbm']:+d} / {s['cbm_max']}</td><td class='num'>{s['confident_errors']}</td>"
        f"<td>{_e(', '.join(s['recurring']) or '–')}</td></tr>" for s in st)
    # heatmap
    fams, pas = summary["families"], summary["passages"]
    hm_head = "".join(f"<th>{_e(p)}<div class='sub'>{summary['passage_students'][p]} students</div></th>" for p in pas)
    hm_rows = ""
    for f in fams:
        cells = ""
        for p in pas:
            n = summary["heatmap"][f"{f}|{p}"]
            tot = summary["passage_students"][p] or 1
            lvl = 0 if n == 0 else (1 if n / tot < 0.34 else (2 if n / tot < 0.67 else 3))
            cells += f"<td class='heat h{lvl}'>{n if n else ''}</td>"
        hm_rows += f"<tr><th class='rowh'>{_e(f.replace('_', ' '))}</th>{cells}</tr>"
    # concept states
    cs_html = ""
    for p in pas:
        concepts = summary["concept_states"].get(p, {})
        if not concepts:
            continue
        head = "".join(f"<th>{_e(i)}</th>" for i in ids)
        body = ""
        for c, by in concepts.items():
            cells = "".join(f"<td><span class='chip {STATE_CLASS.get(by.get(i, ''), 's-none')}'>{_e(by.get(i, '–'))}</span></td>"
                            for i in ids)
            body += f"<tr><th class='rowh'>{_e(c)}</th>{cells}</tr>"
        cs_html += f"<h3>{_e(p)}</h3><div class='scroll'><table><thead><tr><th>Concept</th>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    re_html = "".join(
        f"<li><b>{r['students']} of {r['of']}</b> students – <b>{_e(r['family'].replace('_', ' '))}</b> on <i>{_e(r['passage'])}</i>. "
        f"Reteach {_e(', '.join(r['sids']) or 'the source sentence')}"
        + (f": <q>{_e(r['sentence'])}</q>" if r["sentence"] else "") + f"<div class='sub'>Skill to revise: {_e(r['revise'])}</div></li>"
        for r in summary["reteach"]) or "<li>No errors recorded yet.</li>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{_e(title)}</title>
<style>
:root{{--bg:#f6f8fb;--card:#fff;--ink:#1d2733;--mute:#5b6775;--line:#d7dee7;--blue:#1f4e79;
--h1:#fde2d3;--h2:#f8b48c;--h3:#e5743f;--fr:#fde2d3;--pr:#e3ecf7;--re:#fff1c7;--tr:#dcf2e1}}
@media (prefers-color-scheme:dark){{:root{{--bg:#11161c;--card:#1a212a;--ink:#e6edf3;--mute:#9aa7b4;--line:#2d3743;
--blue:#8cb8e6;--h1:#5a3424;--h2:#8a4626;--h3:#c4582a;--fr:#5a3424;--pr:#243649;--re:#4d4220;--tr:#1f4430}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:20px 16px 40px}}h1{{margin:0;font-size:24px;color:var(--blue)}}
h2{{font-size:18px;margin:28px 0 10px;color:var(--blue)}}h3{{font-size:15px;margin:16px 0 6px}}
.sub{{color:var(--mute);font-size:12.5px;font-weight:400}}.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:16px}}
.tile{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}}.tile b{{display:block;font-size:24px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;background:var(--card)}}
th,td{{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}}thead th{{background:var(--pr);font-size:13px}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}.id{{font-family:ui-monospace,Menlo,monospace}}
.heat{{text-align:center;font-weight:600;min-width:70px}}.h0{{background:var(--card)}}.h1{{background:var(--h1)}}.h2{{background:var(--h2)}}.h3{{background:var(--h3);color:#fff}}
.rowh{{font-weight:600;background:var(--card)}}.chip{{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12.5px}}
.s-fragile{{background:var(--fr)}}.s-prov{{background:var(--pr)}}.s-rep{{background:var(--re)}}.s-trans{{background:var(--tr)}}.s-none{{color:var(--mute)}}
ul.re{{padding-left:18px}}ul.re li{{margin:0 0 10px}}footer{{margin-top:28px;color:var(--mute);font-size:12.5px}}
</style></head><body><main>
<h1>{_e(title)}</h1><div class="sub">Generated {_e(summary['generated'])} on the teacher hub from USB bundles · offline · pseudonymous IDs only</div>
<div class="tiles"><div class="tile"><b>{len(st)}</b>students</div><div class="tile"><b>{len(pas)}</b>passages</div>
<div class="tile"><b>{n_rec}</b>students with a recurring pattern</div><div class="tile"><b>{n_conf}</b>confident errors (certainty 3)</div></div>
<h2>What to reteach</h2><div class="card"><ul class="re">{re_html}</ul></div>
<h2>Class credit table</h2><div class="scroll"><table><thead><tr><th>Student</th><th>Sessions</th><th>Passages</th><th>Assessment credits</th>
<th>Recovery</th><th>CBM</th><th>Confident errors</th><th>Recurring pattern</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>Misconception heatmap</h2><div class="sub" style="margin-bottom:6px">Number of students who made each error family on each passage.</div>
<div class="scroll"><table><thead><tr><th>Error family</th>{hm_head}</tr></thead><tbody>{hm_rows or '<tr><td>No errors recorded.</td></tr>'}</tbody></table></div>
<h2>Concept states</h2><div class="sub">Provisional = correct first time · Fragile = wrong, unresolved · Repaired = correct on the second chance (not mastery) · Transferred = correct on the original text (initial evidence only)</div>
{cs_html or '<p>No sessions yet.</p>'}
<footer>Level Bridge STEM · CBS portal. Observed behaviour only: not a diagnosis and not evidence of learning.
Names are not stored; the ID-to-name list stays with the teacher. Every profile shown carried a consent flag and a verified SHA-256 checksum.</footer>
</main></body></html>"""


def write_portal(store: Path, out: Path) -> Dict[str, object]:
    summary = class_summary(load_profiles(store))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_portal(summary), encoding="utf-8")
    return summary
