"""Configuration loading and structured logging."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def find_project_root(start: Optional[Path] = None) -> Path:
    """Return the project root (directory containing ``config/config.yaml``).

    Order: ``$LB_ROOT``; walking up from ``start``/cwd; the package's own location.
    """
    env = os.environ.get("LB_ROOT")
    if env and (Path(env) / "config" / "config.yaml").exists():
        return Path(env).resolve()
    candidates = []
    here = (start or Path.cwd()).resolve()
    candidates.extend([here, *here.parents])
    pkg = Path(__file__).resolve()
    candidates.extend(pkg.parents)
    for c in candidates:
        if (c / "config" / "config.yaml").exists():
            return c
    raise FileNotFoundError("Could not find config/config.yaml. Run from the project root or set LB_ROOT.")


@dataclass
class AppConfig:
    """Loaded configuration with helpers for resolving project-relative paths."""

    root: Path
    app: Dict[str, Any]
    model: Dict[str, Any]
    synonyms: Dict[str, list]
    item_contexts: Dict[str, Any]
    overrides: Dict[str, Any] = field(default_factory=dict)

    def path(self, p: Optional[str]) -> Optional[Path]:
        """Resolve a project-relative path (absolute paths are returned unchanged)."""
        if p is None:
            return None
        pp = Path(p)
        return pp if pp.is_absolute() else (self.root / pp)

    @property
    def outputs_dir(self) -> Path:
        d = self.path(self.app["paths"]["outputs_dir"])
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def logs_dir(self) -> Path:
        d = self.path(self.app["paths"]["logs_dir"])
        d.mkdir(parents=True, exist_ok=True)
        return d


def _load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def load_config(root: Optional[Path] = None, model_config: Optional[str] = None) -> AppConfig:
    """Load ``config/config.yaml`` and the files it references."""
    root = Path(root).resolve() if root else find_project_root()
    app = _load_yaml(root / "config" / "config.yaml")
    paths = app["paths"]
    model_path = Path(model_config) if model_config else root / paths["model_config"]
    if not model_path.is_absolute():
        model_path = root / model_path
    model = _load_yaml(model_path)
    syn_raw = _load_yaml(root / paths["synonyms"])
    synonyms = {str(k).lower(): [str(s) for s in (v or [])] for k, v in syn_raw.items()}
    contexts = _load_yaml(root / paths["item_contexts"])
    return AppConfig(root=root, app=app, model=model, synonyms=synonyms, item_contexts=contexts)


class JsonFormatter(logging.Formatter):
    """One JSON object per line – machine-readable structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "data", None)
        if extra:
            payload["data"] = extra
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(logs_dir: Path, run_id: str, verbose: bool = False) -> Path:
    """Configure a JSON-lines file log plus a concise console log. Returns the log path."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{run_id}.jsonl"
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    ch.setLevel(logging.DEBUG if verbose else logging.WARNING)
    root.addHandler(fh)
    root.addHandler(ch)
    return log_path


def log_event(logger: logging.Logger, level: int, msg: str, **data: Any) -> None:
    """Log a message with structured data attached."""
    logger.log(level, msg, extra={"data": data} if data else None)
