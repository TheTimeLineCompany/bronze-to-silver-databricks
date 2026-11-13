"""Install the skills where Genie Code loads them, and keep the project pointer to the framework current.

Genie loads skills from the user's skill folder (for example /Workspace/Users/<me>/.assistant/skills), not from the
framework's skills/ folder, and reads AGENTS.md from the parent folders of the open file (feedback I-17 §4).
- install_skills(target): copies skills/ there with a version stamp; the project remembers the folder.
- skills_problem(layout): a warning when the installed skills do not match this framework version.
- refresh_project_agents(layout): the project's own short AGENTS.md, pointing to the framework folder found at run
  time (the project pins the framework VERSION, not its path, so moving the framework folder is safe).
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml

from . import FRAMEWORK_ROOT, FRAMEWORK_VERSION
from .layout import Layout, guard_write, workspace_path
from .store import atomic_write, dump_json, dump_yaml, emit_event, now_iso

STAMP = ".b2s_skills_version.json"


def skills_hash(folder: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(folder.rglob("SKILL.md")):
        h.update(f.relative_to(folder).as_posix().encode())
        h.update(f.read_bytes())
    return "sha256:" + h.hexdigest()[:16]


def install_skills(target: str | Path, layout: Layout | None = None) -> dict:
    src, dst = FRAMEWORK_ROOT / "skills", Path(target)
    names = sorted(d.name for d in src.iterdir() if (d / "SKILL.md").exists())
    for n in names:
        out = guard_write(dst / n)
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(src / n, out, ignore=shutil.ignore_patterns("__pycache__"))
    stamp = {"framework_version": FRAMEWORK_VERSION, "skills_hash": skills_hash(src), "skills": names,
             "installed_at": now_iso(), "from": workspace_path(FRAMEWORK_ROOT)}
    atomic_write(dst / STAMP, dump_json(stamp))
    if layout and layout.project_yaml.exists():
        cfg = yaml.safe_load(layout.project_yaml.read_text(encoding="utf-8"))
        cfg["skills_dir"] = str(dst)
        atomic_write(layout.project_yaml, dump_yaml(cfg))
        emit_event(layout, "skills_installed", note=str(dst), extra={"stamp": stamp})
    return stamp


def skills_problem(layout: Layout) -> str | None:
    cfg = yaml.safe_load(layout.project_yaml.read_text(encoding="utf-8")) or {}
    target = cfg.get("skills_dir")
    if not target:
        return "skills are not installed for Genie yet: python -m b2s --project <p> install-skills <skill folder>"
    stamp = Path(target) / STAMP
    if not stamp.exists():
        return f"no skill version stamp in {target}: install the skills again"
    s = json.loads(stamp.read_text(encoding="utf-8"))
    if s.get("skills_hash") != skills_hash(FRAMEWORK_ROOT / "skills"):
        return (f"installed skills ({s.get('framework_version')}) differ from this framework ({FRAMEWORK_VERSION}): "
                "install them again")
    return None


def refresh_project_agents(layout: Layout) -> Path:
    """A pointer (data only): where the framework is and which version the project pins."""
    cfg = yaml.safe_load(layout.project_yaml.read_text(encoding="utf-8")) or {}
    text = (f"# Project {cfg.get('name', '')}\n\n"
            f"Framework folder: `{workspace_path(FRAMEWORK_ROOT)}` (version {FRAMEWORK_VERSION}; "
            f"this project pins {cfg.get('framework_version')}).\n"
            f"Rules: `{workspace_path(FRAMEWORK_ROOT / 'AGENTS.md')}` and its `rules/` folder.\n")
    return atomic_write(layout.root / "AGENTS.md", text.encode("utf-8"))
