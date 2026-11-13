"""P0 project setup and P1 application registration."""
from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from . import FRAMEWORK_ROOT, FRAMEWORK_VERSION
from .layout import APP_ID, Layout, guard_write
from .store import atomic_write, dump_yaml, emit_event, load_any, now_iso

DEFAULT_SETTINGS = {
    "redact_values": True,              # R-01: never off without a logged reason
    "time_budget_minutes": 25,          # notebook runs resume after this
    "max_tables": 1000,
    "clarify_max_questions": 5,
    "build": {"dev_catalog": "dev", "dev_silver_schema": "silver_dev", "prod_markers": ["prod", "prd"]},
    "baseline": {"sample_rows": 5_000_000, "seed": 42, "max_key_size": 4, "key_pool_size": 8, "max_key_checks": 25,
                 "low_cardinality_max": 50, "topk": 20, "near_key_max_duplicates": 10},
}

# Checkpoints, approved in the chat (V1.3 checkpoints kept; design §12.1).
#   main:      the files named (with version) in the approval statement
#   blocks:    what an approval of this point gates
#   requires:  chain rule — points that must be approved for the input versions the main files were made from
#   decisions: open items the worker decides in the statement
DEFAULT_APPROVAL_POINTS = {
    "CP1": {"name": "bronze baseline", "mode": "chat", "main": ["baseline/summary"], "blocks": None, "requires": [],
            "decisions": "open_points"},
    "CP2": {"name": "documents, application understanding and scope", "mode": "chat",
            "main": ["understanding/app_brief", "models/dependencies", "models/process", "models/conceptual",
                     "scope/scope"],
            "blocks": None, "requires": [], "decisions": None},
    "CP3": {"name": "central model", "mode": "chat", "main": ["models/logical"], "blocks": "P4.1", "requires": ["CP2"],
            "decisions": None},
    "CP4": {"name": "sttm", "mode": "chat", "main": ["sttm/sttm"], "blocks": "handoff", "requires": ["CP3"],
            "decisions": "questions_assumptions"},
    # Automatic checkpoints (V1.3 C-37): framework checks replace the person's approval.
    "CP5": {"name": "code and QA", "mode": "automatic",
            "main": ["build/index", "build/masters", "qa/results", "build/code_review"],
            "blocks": "P6.1", "requires": ["CP4"], "decisions": None},
    "CP6": {"name": "deployment readiness", "mode": "automatic", "main": ["release/readiness"],
            "blocks": "handoff H2", "requires": ["CP5"], "decisions": None},
}
REQUIRED_POINTS = {"CP3", "CP4", "CP5", "CP6"}


def init_project(root: str | Path, name: str, workers: list | None = None) -> Layout:
    """Create a project folder: project.yaml (framework pin), ontology copy, folders. Refuses /Workspace/Shared (DB-12)."""
    layout = Layout(root)
    if "/Workspace/Shared" in layout.root.as_posix():
        raise ValueError("project folder must not be under /Workspace/Shared (readable by all users; R-01, DB-12)")
    if layout.project_yaml.exists():
        raise FileExistsError(f"project exists: {layout.project_yaml}")
    cfg = {"name": name, "framework_version": FRAMEWORK_VERSION, "created": now_iso(), "workers": workers or [],
           "settings": DEFAULT_SETTINGS, "approval_points": DEFAULT_APPROVAL_POINTS}
    atomic_write(layout.project_yaml, dump_yaml(cfg))
    src = FRAMEWORK_ROOT / "registry_template"
    for f in sorted(src.iterdir()):
        if f.is_file():
            atomic_write(layout.ontology_dir / f.name, f.read_bytes())
    for d in (layout.events_dir, layout.ids_dir, layout.plugins_dir, layout.contrib_dir, layout.root / "apps"):
        guard_write(d).mkdir(parents=True, exist_ok=True)
    atomic_write(layout.root / "AGENTS.md", (
        "# Project folder\n\nThis folder holds project state for the Bronze-to-Silver framework "
        f"{FRAMEWORK_VERSION}.\nRules for agents: see AGENTS.md and rules/ in the framework folder.\n"
        "Never edit a file whose name has .vNNN.; save changes as a new version (`python -m b2s save`).\n").encode())
    emit_event(layout, "project_created", note=name)
    return layout


def open_project(root: str | Path) -> Layout:
    layout = Layout(root)
    if not layout.project_yaml.exists():
        raise FileNotFoundError(f"not a project folder (no project.yaml): {layout.root}")
    return layout


def config(layout: Layout) -> dict:
    return yaml.safe_load(layout.project_yaml.read_text(encoding="utf-8"))


def settings(layout: Layout) -> dict:
    """Project settings over the defaults, merged per nested key (a partial `baseline:` keeps the other defaults)."""
    return _deep_merge(DEFAULT_SETTINGS, config(layout).get("settings") or {})


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def approval_points(layout: Layout) -> dict:
    pts = config(layout).get("approval_points") or DEFAULT_APPROVAL_POINTS
    for p in REQUIRED_POINTS:
        pts.setdefault(p, DEFAULT_APPROVAL_POINTS[p])
    return pts


def ontology(layout: Layout, name: str) -> dict:
    """business | data | information | entities | key_normalisation"""
    return load_any(layout.ontology_dir / f"{name}.yaml") or {}


def register_app(layout: Layout, app: str, name: str, schemas: list[str], lookup_schemas: list | None = None,
                 bronze: dict | None = None, description: str = "") -> dict:
    """P1: one application = one source, with one or more schemas and lookup schemas (QA-09)."""
    if not APP_ID.match(app):
        raise ValueError(f"application id must look like S01_name: {app!r}")
    path = layout.app_yaml(app)
    if path.exists():
        raise FileExistsError(f"application already registered: {app}")
    cfg = {"app": app, "name": name, "description": description, "schemas": schemas,
           "lookup_schemas": lookup_schemas or [], "bronze": bronze or {"connector": "spark"}, "registered": now_iso()}
    atomic_write(path, dump_yaml(cfg))
    for d in ("inbox", "uploads"):
        guard_write(layout.sub(app, d)).mkdir(parents=True, exist_ok=True)
    emit_event(layout, "app_registered", app=app, step="P1", outputs={layout.rel(path): None})
    return cfg


def app_config(layout: Layout, app: str) -> dict:
    return yaml.safe_load(layout.app_yaml(app).read_text(encoding="utf-8"))


def copy_into_inbox(layout: Layout, app: str, files: list[str | Path], base: str | Path | None = None) -> list[Path]:
    """Put documents into the inbox (read-only after registration: P3 never edits them).
    With `base`, sub-folders below it are kept, so archive/notes.md does not overwrite notes.md."""
    out = []
    for f in files:
        rel = Path(f).relative_to(base) if base else Path(Path(f).name)
        dst = guard_write(layout.sub(app, "inbox", *rel.parts))
        if dst.exists():
            raise FileExistsError(f"inbox already has {rel.as_posix()}; inbox files are never overwritten")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, dst)
        out.append(dst)
    emit_event(layout, "inbox_files_added", app=app, step="P2.1", outputs={layout.rel(p): None for p in out})
    return out
