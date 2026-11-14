"""TEACH: lesson packs and teacher review (report Section 7.2).

A lesson pack is built once on the teacher hub (where the LLM runs) and copied by USB
to student devices. It holds the passage, the validated explanations (with where each
came from), the accepted question wording and the teacher's review decisions, signed
with SHA-256.

On a student device the pack is *replayed*: the knowledge map, registry, item bank,
answer keys and error models are rebuilt by the same deterministic Python (no model
call), the passage hash and item IDs are checked against the pack, and the pack's
explanation and stem texts are laid over the rebuilt artefacts. So the student session
needs no model and every answer is still computed by Python.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from .config import AppConfig
from .model_runtime import TemplateRuntime
from .pipeline import BuildArtifacts, build
from .profile_bundle import canonical_sha256

PACK_FORMAT = "level-bridge-lesson-pack/1"
REVIEWABLE = ("summary", "l1", "l2")


class PackError(ValueError):
    """Malformed, tampered or inconsistent lesson pack, or a refused review edit."""


def make_pack(art: BuildArtifacts, backend_info: Dict[str, object], template_art: BuildArtifacts) -> Dict[str, object]:
    payload = {
        "created": time.strftime("%Y-%m-%d %H:%M"),
        "passage": {"text": art.passage.text, "sha256": art.passage.sha256, "source": art.passage.source,
                    "word_count": art.passage.word_count},
        "built_with": {"backend": backend_info.get("backend") or backend_info.get("requested_backend"),
                       "is_llm": bool(backend_info.get("is_llm", False)), "timings": art.timings},
        "explanations": {k: {"text": e.text, "source": e.source, "validated": e.validated}
                         for k, e in art.explanations.items()},
        "templates": {k: template_art.explanations[k].text for k in REVIEWABLE},
        "stems": {it.item_id: it.stem for it in art.bank.items if it.stem_source == "llm"},
        "item_ids": [it.item_id for it in art.bank.items],
        "registry": [e.canonical for e in art.registry.required()],
        "formula": art.km.formulas[0].text if art.km.formulas else None,
        "review": {k: {"status": "pending"} for k in REVIEWABLE},
    }
    return {"format": PACK_FORMAT, "sha256": canonical_sha256(payload), "payload": payload}


def write_pack(pack: Dict[str, object], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def read_pack(path: Path) -> Dict[str, object]:
    try:
        pack = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackError(f"{Path(path).name}: unreadable lesson pack ({exc})") from exc
    if pack.get("format") != PACK_FORMAT or "payload" not in pack:
        raise PackError(f"{Path(path).name}: not a Level Bridge lesson pack")
    if canonical_sha256(pack["payload"]) != pack.get("sha256"):
        raise PackError(f"{Path(path).name}: checksum mismatch - the pack was changed outside pack-review; not loaded")
    return pack


def reseal(pack: Dict[str, object]) -> Dict[str, object]:
    pack["sha256"] = canonical_sha256(pack["payload"])
    return pack


def approved(pack: Dict[str, object]) -> bool:
    return all(pack["payload"]["review"][k]["status"] != "pending" for k in REVIEWABLE)


def _passage_file(cfg: AppConfig, payload: Dict[str, object]) -> Path:
    p = cfg.outputs_dir / f"pack_passage_{payload['passage']['sha256'][:12]}.txt"
    p.write_text(payload["passage"]["text"], encoding="utf-8")
    return p


def replay(cfg: AppConfig, pack: Dict[str, object]) -> BuildArtifacts:
    """Rebuild the deterministic artefacts without a model and apply the pack's texts."""
    payload = pack["payload"]
    if payload.get('ocr_verification') and not approved(pack):
        raise PackError('OCR lesson requires teacher approval before replay.')
    art = build(cfg, _passage_file(cfg, payload), TemplateRuntime())
    if art.passage.sha256 != payload["passage"]["sha256"]:
        raise PackError("passage hash differs from the pack - not the same passage")
    ids = [it.item_id for it in art.bank.items]
    if ids != payload["item_ids"]:
        raise PackError("item bank differs from the pack (different code or configuration version on this device)")
    for k, e in payload["explanations"].items():
        if k in art.explanations:
            art.explanations[k].text = e["text"]
            art.explanations[k].source = e["source"]
            art.explanations[k].validated = e["validated"]
    for iid, stem in payload["stems"].items():
        it = art.bank.by_id(iid)
        it.stem, it.stem_source = stem, "llm"
    art.timings = {**payload["built_with"]["timings"], "replayed_from_pack": True}
    art.stem_rewording = {"attempted": bool(payload["stems"]), "accepted": len(payload["stems"]), "from_pack": True}
    return art


def apply_review(cfg: AppConfig, pack: Dict[str, object], kind: str, action: str,
                 text: Optional[str] = None) -> Dict[str, object]:
    """Teacher decision for one explanation: approve | edit | template.

    An edited text must pass the same validation gate as model output; if it fails, the
    edit is refused and the explanation stays as it was.
    """
    if kind not in REVIEWABLE:
        raise PackError(f"'{kind}' cannot be reviewed (choose from {', '.join(REVIEWABLE)})")
    payload = pack["payload"]
    rev = payload["review"][kind]
    if action == "approve":
        rev.update(status="approved", at=time.strftime("%Y-%m-%d %H:%M"))
    elif action == "template":
        payload["explanations"][kind] = {"text": payload["templates"][kind], "source": "template", "validated": True}
        rev.update(status="template", at=time.strftime("%Y-%m-%d %H:%M"))
    elif action == "edit":
        if not text or not text.strip():
            raise PackError("empty edit")
        art = build(cfg, _passage_file(cfg, payload), TemplateRuntime())
        rep = art.validator.validate(text.strip(), kind)
        if not rep.passed:
            reasons = "; ".join(f"{c.name}: {c.details}" for c in rep.failures())
            raise PackError(f"edit refused - it fails the validation gate ({reasons})")
        payload["explanations"][kind] = {"text": text.strip(), "source": "teacher_edited", "validated": True}
        rev.update(status="edited", at=time.strftime("%Y-%m-%d %H:%M"))
    else:
        raise PackError(f"unknown review action '{action}'")
    return reseal(pack)


def review_lines(pack: Dict[str, object]) -> List[str]:
    p = pack["payload"]
    out = [f"LESSON PACK  passage sha256 {p['passage']['sha256'][:12]}…  ({p['passage']['word_count']} words)  "
           f"built with {p['built_with']['backend']} (LLM: {'yes' if p['built_with']['is_llm'] else 'no'})",
           f"   formula: {p['formula'] or '-'}   registry: {', '.join(p['registry'])}",
           f"   items: {len(p['item_ids'])}   LLM-worded stems: {len(p['stems'])}"]
    for k in REVIEWABLE:
        e = p["explanations"][k]
        out.append(f"   {k:<8} source={e['source']:<15} review={p['review'][k]['status']}")
    out.append(f"   status: {'APPROVED - ready to export' if approved(pack) else 'NOT YET APPROVED'}")
    return out
