"""IMPROVE: checksummed learner-profile bundles moved by USB (report Section 7.2-7.3).

A bundle is one JSON file::

    {"format": "level-bridge-profile-bundle/1", "created": ..., "sha256": <hex>, "payload": <profile>}

``sha256`` covers the canonical JSON of the payload (sorted keys, no whitespace), so any
change to the profile after export is detected on import. No network is involved.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Dict, List

from .learner_memory import check_learner_id, load_profile, merge_sessions, new_profile, save_profile

BUNDLE_FORMAT = "level-bridge-profile-bundle/1"


class BundleError(ValueError):
    """A bundle is malformed, tampered with, or not allowed to be exported."""


def canonical_sha256(obj) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def export_bundle(store: Path, learner_id: str, out_dir: Path) -> Path:
    """Write ``<out_dir>/<ID>_<timestamp>.lbprofile.json``. Refuses without consent."""
    prof = load_profile(store, learner_id)
    if prof is None:
        raise BundleError(f"no profile for {check_learner_id(learner_id)} in {store}")
    if not prof.get("consent"):
        raise BundleError(f"{prof['learner_id']}: consent flag is not set - the profile cannot leave this device "
                          f"(record consent with: session ... --learner {prof['learner_id']} --consent)")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = {"format": BUNDLE_FORMAT, "created": time.strftime("%Y-%m-%d %H:%M"),
              "learner_id": prof["learner_id"], "sessions": len(prof["sessions"]),
              "sha256": canonical_sha256(prof), "payload": prof}
    path = out_dir / f"{prof['learner_id']}_{time.strftime('%Y%m%d_%H%M%S')}.lbprofile.json"
    path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def read_bundle(path: Path) -> Dict[str, object]:
    """Load and verify a bundle. Raises :class:`BundleError` on any problem."""
    try:
        b = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError(f"{Path(path).name}: unreadable bundle ({exc})") from exc
    if b.get("format") != BUNDLE_FORMAT or "payload" not in b or "sha256" not in b:
        raise BundleError(f"{Path(path).name}: not a Level Bridge profile bundle")
    if canonical_sha256(b["payload"]) != b["sha256"]:
        raise BundleError(f"{Path(path).name}: checksum mismatch - the bundle was changed or damaged; not imported")
    check_learner_id(b["payload"].get("learner_id", ""))
    if not b["payload"].get("consent"):
        raise BundleError(f"{Path(path).name}: profile has no consent flag; not imported")
    return b


def import_bundles(paths: List[Path], hub_store: Path) -> List[Dict[str, object]]:
    """Verify and merge bundles into the hub's profile store. Duplicate sessions are skipped."""
    results = []
    for p in paths:
        try:
            b = read_bundle(p)
        except BundleError as exc:
            results.append({"file": str(p), "ok": False, "error": str(exc)})
            continue
        incoming = b["payload"]
        prof = load_profile(hub_store, incoming["learner_id"]) or new_profile(incoming["learner_id"], True)
        prof["consent"] = True
        added = merge_sessions(prof, incoming["sessions"])
        save_profile(hub_store, prof)
        results.append({"file": str(p), "ok": True, "learner_id": incoming["learner_id"],
                        "sessions_in_bundle": len(incoming["sessions"]), "sessions_added": added})
    return results
