"""Plug-in slots (design §15). A slot is a named point where a deterministic asset plugs in with a fixed contract.

Two kinds of plug-in:
  python    entry adapter.py:<function> implements the slot contract directly.
  notebook  the client's notebook is kept unchanged (`notebook:`); the agent runs it with the widgets in
            `parameters` (run_plan), and the adapter's `convert(run_dir)` turns its output files into the slot
            contract (collect). The contract test runs `convert` on the plug-in's `sample_output/`.
First use of the framework: the client's own notebooks and templates come in this way (@fw-integrate).

Core plug-ins live in <framework>/plugins/, project plug-ins in <project>/plugins/. A project plug-in overrides a
core plug-in of the same slot only after the worker approves it in the chat (PLUGIN). Every run records which
plug-in version ran. Workers send good plug-ins to maintainers as a contribution package (@fw-integrate).
"""
from __future__ import annotations

import importlib.util
import shutil
import tempfile
import zipfile
from pathlib import Path

import yaml

from . import FRAMEWORK_ROOT, identity, versions
from .layout import Layout, guard_write
from .store import atomic_write, dump_json, emit_event, now_iso, sha256_file

SLOTS = {
    "profiler": "convert(run_dir) -> {table: [column profiles]}  (column, family, null_pct, approx_distinct, ...)",
    "sttm_export_excel": "export(sttm: dict, out_path: str) -> None  (writes the client Excel template)",
    "sttm_export_json": "export(sttm: dict, out_path: str) -> None  (writes the client JSON template)",
    "sttm_import_excel": "import_(path: str) -> dict  (client Excel template -> canonical STTM)",
    "doc_extractor": "extract(path: str) -> {'text': str, 'sections': list, 'figures': list}",
    "key_rules": "normalise(value, rule: dict) -> str | None",
}
REQUIRED = {"name", "slot", "version", "entry", "description"}


class PluginError(ValueError):
    pass


def read_manifest(folder: str | Path) -> dict:
    p = Path(folder) / "plugin.yaml"
    if not p.exists():
        raise PluginError(f"no plugin.yaml in {folder}")
    m = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    missing = REQUIRED - m.keys()
    if missing:
        raise PluginError(f"plugin.yaml misses: {', '.join(sorted(missing))}")
    if m["slot"] not in SLOTS:
        raise PluginError(f"unknown slot {m['slot']}; slots: {', '.join(SLOTS)}. A new slot is a maintainer decision.")
    m.setdefault("kind", "python")
    if m["kind"] not in ("python", "notebook"):
        raise PluginError("kind must be python or notebook")
    if m["kind"] == "notebook":
        for k in ("notebook", "parameters"):
            if k not in m:
                raise PluginError(f"a notebook plug-in needs '{k}' in plugin.yaml")
        if not (Path(folder) / m["notebook"]).exists():
            raise PluginError(f"notebook {m['notebook']} is not in the plug-in folder")
    return m


def load_entry(folder: str | Path, manifest: dict):
    file, func = manifest["entry"].split(":")
    spec = importlib.util.spec_from_file_location(f"b2s_plugin_{manifest['name']}", Path(folder) / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, func)


def _all(layout: Layout | None) -> list[tuple[Path, dict, str]]:
    out = []
    for origin, root in (("core", FRAMEWORK_ROOT / "plugins"), ("project", layout.plugins_dir if layout else None)):
        if root and root.exists():
            for d in sorted(root.iterdir()):
                if (d / "plugin.yaml").exists():
                    out.append((d, read_manifest(d), origin))
    return out


def is_active(layout: Layout, name: str, version: str) -> bool:
    v = versions.latest(layout.plugins_dir / name / "activation", "json")
    return bool(v and versions.read(v).get("version") == version)


def resolve(layout: Layout | None, slot: str) -> tuple:
    """(callable, info). An approved project plug-in wins over the core one."""
    cands = [(d, m, o) for d, m, o in _all(layout) if m["slot"] == slot]
    proj = [c for c in cands if c[2] == "project" and is_active(layout, c[1]["name"], str(c[1]["version"]))]
    pick = proj[-1] if proj else next((c for c in cands if c[2] == "core"), None)
    if not pick:
        raise PluginError(f"no plug-in for slot {slot}")
    d, m, o = pick
    return load_entry(d, m), {"name": m["name"], "version": str(m["version"]), "origin": o, "overrides_core": o == "project"}


# --------------------------------------------------------------------------- contract tests
def contract_test(folder: str | Path) -> list[str]:
    """Run the slot contract on a small fixture. Empty list = pass."""
    m = read_manifest(folder)
    try:
        fn = load_entry(folder, m)
    except Exception as e:  # noqa: BLE001
        return [f"entry {m['entry']} cannot be loaded: {e}"]
    errs = []
    if m["kind"] == "notebook":
        sample = Path(folder) / m.get("sample_output", "sample_output")
        if not sample.exists():
            return ["a notebook plug-in needs sample_output/ (real output of one run, without personal data) for its contract test"]
        try:
            out = fn(str(sample))
        except Exception as e:  # noqa: BLE001
            return [f"convert(sample_output) raised {type(e).__name__}: {e}"]
        return _check_slot_output(m["slot"], out)
    if m["slot"] in ("sttm_export_excel", "sttm_export_json"):
        fixture = {"app": "S90_test", "logical_version": "v001", "tables": [{
            "target_table": "slv_x", "business_object": "X", "data_class": "event", "grain": "one row per x",
            "primary_key": ["x_sk"], "business_key": ["x_no"], "sources": ["s.x"],
            "columns": [{"target_column": "x_sk", "rule": "surrogate_key", "status": "known"},
                        {"target_column": "x_no", "rule": "normalised_key", "source": {"table": "s.x", "columns": ["x_no"]},
                         "status": "assumed", "assumption": "A-0001"}]}]}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / ("out.xlsx" if m["slot"] == "sttm_export_excel" else "out.json")
            try:
                fn(fixture, str(out))
            except Exception as e:  # noqa: BLE001
                return [f"export raised {type(e).__name__}: {e}"]
            if not out.exists() or out.stat().st_size == 0:
                errs.append("export wrote no file")
            elif m["slot"] == "sttm_export_excel":
                from openpyxl import load_workbook
                text = " ".join(str(c.value) for ws in load_workbook(out).worksheets for row in ws.iter_rows() for c in row)
                for must in ("slv_x", "x_no", "A-0001"):
                    if must not in text:
                        errs.append(f"export lost '{must}' (every table, column and open item must reach the file)")
    elif not callable(fn):
        errs.append("entry is not callable")
    return errs


# --------------------------------------------------------------------------- @fw-integrate worker mode
def install(layout: Layout, src: str | Path) -> dict:
    """Install a plug-in into the project. It runs only after PLUGIN (activate)."""
    m = read_manifest(src)
    errs = contract_test(src)
    if errs:
        raise PluginError("contract test failed:\n- " + "\n- ".join(errs))
    dest = guard_write(layout.plugins_dir / m["name"])
    if dest.exists():
        shutil.rmtree(dest / "_code", ignore_errors=True)
    for f in Path(src).rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts:
            target = guard_write(dest / f.relative_to(src))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, target)
    emit_event(layout, "plugin_installed", note=f"{m['name']} {m['version']} slot {m['slot']}")
    return {"name": m["name"], "version": str(m["version"]), "slot": m["slot"], "contract_test": "passed",
            "active": False, "next": f"approve in the chat: I, <your name>, approve PLUGIN {m['name']}.v{m['version']}."}


def activate(layout: Layout, name: str, statement: str) -> dict:
    """PLUGIN: the worker's chat statement, verbatim, e.g. 'I, Jane Doe, approve PLUGIN my_export.v1.0.0.'"""
    from .approve import ApprovalError, parse_statement
    m = read_manifest(layout.plugins_dir / name)
    st = parse_statement(statement)
    if "plugin" not in st["rest"].lower() or f"{name}.v{m['version']}".lower() not in st["rest"].lower():
        raise ApprovalError(f"the statement must name PLUGIN and {name}.v{m['version']}")
    v = versions.save(layout, layout.plugins_dir / name / "activation", "json",
                      {"name": name, "version": str(m["version"]), "slot": m["slot"], "statement": statement,
                       "name_in_statement": st["name"], "account": identity.account()["email"], "at": now_iso()},
                      reason="PLUGIN")
    emit_event(layout, "approval_recorded", via="chat", note=f"PLUGIN {name}",
               extra={"statement": statement, "point": "PLUGIN", "approval_mode": "self"})
    return {"active": True, "activation": v.label}


def package(layout: Layout, name: str, change_note: str) -> Path:
    """Contribution package for maintainers: plug-in files + CHANGE_NOTE.md + contract test result."""
    src = layout.plugins_dir / name
    m = read_manifest(src)
    errs = contract_test(src)
    stamp = now_iso()[:10]
    out = guard_write(layout.contrib_dir / f"{name}-{m['version']}-{stamp}.zip")
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in src.rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts and not f.name.startswith("activation"):
                z.write(f, f"{name}/{f.relative_to(src).as_posix()}")
        z.writestr(f"{name}/CHANGE_NOTE.md", change_note)
        z.writestr(f"{name}/contract_test.json", dump_json({"passed": not errs, "errors": errs, "at": now_iso()}))
    emit_event(layout, "contribution_packaged", note=out.name)
    return out


# --------------------------------------------------------------------------- use: STTM export
def export_sttm(layout: Layout, app: str, v: versions.Version) -> dict:
    """Write the Excel export of an STTM version as its companion (sttm.vNNN.xlsx) with the resolved plug-in."""
    fn, info = resolve(layout, "sttm_export_excel")
    out = v.companion("xlsx")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / out.name
        fn(versions.read(v), str(tmp))
        atomic_write(out, tmp.read_bytes())
    emit_event(layout, "sttm_exported", app=app, outputs={layout.rel(out): sha256_file(out)}, extra={"plugin": info})
    return {"path": out, "plugin": info}


def _check_slot_output(slot: str, out) -> list[str]:
    if slot == "profiler":
        if not isinstance(out, dict) or not out:
            return ["profiler convert() must return {table: [column profiles]} with at least one table"]
        errs = []
        for t, cols in out.items():
            if not isinstance(cols, list) or not cols:
                errs.append(f"{t}: no column profiles")
                continue
            for c in cols:
                miss = {"column", "family", "null_pct", "approx_distinct"} - set(c)
                if miss:
                    errs.append(f"{t}.{c.get('column')}: missing {', '.join(sorted(miss))}")
                    break
        return errs
    return [] if out is not None else ["convert() returned nothing"]


# --------------------------------------------------------------------------- notebook plug-ins: run and collect
def run_plan(layout: Layout, app: str, slot: str, values: dict) -> dict:
    """What the agent runs: the plug-in notebook, its widgets (placeholders {app}, {project_root}, {run_dir} and the
    given values filled in), and the folder where the notebook must write its output."""
    cands = [(d, m, o) for d, m, o in _all(layout) if m["slot"] == slot and m["kind"] == "notebook"
             and (o == "core" or is_active(layout, m["name"], str(m["version"])))]
    if not cands:
        raise PluginError(f"no active notebook plug-in for slot {slot}")
    d, m, o = cands[-1]
    run_id = now_iso().replace(":", "").replace("-", "")
    run_dir = guard_write(layout.app_dir(app) / "work" / "plugin_runs" / m["name"] / run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    ctx = {"app": app, "project_root": str(layout.root), "run_dir": str(run_dir), **values}
    widgets = {k: str(v).format(**ctx) for k, v in (m.get("parameters") or {}).items()}
    plan = {"plugin": m["name"], "version": str(m["version"]), "notebook": str(d / m["notebook"]),
            "widgets": widgets, "run_dir": str(run_dir), "run_id": run_id}
    atomic_write(run_dir / "plan.json", dump_json(plan))
    emit_event(layout, "plugin_run_planned", app=app, note=f"{m['name']} {m['version']}", extra={"plan": plan})
    return plan


def collect(layout: Layout, app: str, plan: dict) -> dict:
    """Convert the notebook's output with the plug-in adapter and check it against the slot contract."""
    d = next(d for d, m, o in _all(layout) if m["name"] == plan["plugin"])
    m = read_manifest(d)
    out = load_entry(d, m)(plan["run_dir"])
    errs = _check_slot_output(m["slot"], out)
    if errs:
        raise PluginError("plug-in output breaks the slot contract:\n- " + "\n- ".join(errs))
    emit_event(layout, "plugin_run_collected", app=app, note=f"{m['name']} {m['version']}",
               extra={"run_id": plan["run_id"], "tables": len(out) if isinstance(out, dict) else None})
    return out
