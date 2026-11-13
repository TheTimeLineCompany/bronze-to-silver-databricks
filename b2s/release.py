"""P6.1 Readiness package and H2 (handoff to the deployment team) after the automatic checkpoint CP6.

readiness(): completeness checks + release/readiness.vNNN.md (needs CP5 for the versions it reads).
build_h2():  handoff/H2-nnn/ with the notebooks, master builds, QA results, STTM and the readiness report.
"""
from __future__ import annotations

import shutil

from . import items, versions
from .approve import approvals
from .build.codegen import build_settings
from .layout import Layout, guard_write
from .steps import save_output
from .store import atomic_write, dump_json, emit_event, next_id, now_iso, sha256_file


def _latest(layout, app, stem, ext):
    v = versions.latest(layout.stem(app, stem), ext)
    return v, (versions.read(v) if v else None)


def readiness(layout: Layout, app: str) -> versions.Version:
    """Check completeness and write the readiness report. Problems are listed in the report and in its sidecar."""
    b = build_settings(layout)
    iv, idx = _latest(layout, app, "build/index", "json")
    mv, mast = _latest(layout, app, "build/masters", "json")
    qv, qa = _latest(layout, app, "qa/results", "json")
    rv, review = _latest(layout, app, "build/code_review", "md")
    cp4 = [a for a in approvals(layout, app, "CP4")]
    cp5 = [a for a in approvals(layout, app, "CP5")]
    problems = []
    if not cp5:
        problems.append("CP5 is not passed")
    if not qa or not qa.get("all_passed"):
        problems.append("QA did not pass")
    for e, m in (mast or {}).get("masters", {}).items():
        problems += [f"master {e}: {p}" for p in m["problems"]]
    must = [qid for a in cp4[-1:] for qid, d in (a.get("decisions") or {}).items() if d == "must_answer"]
    open_must = [q for q in must if (items.get(layout, app, q) or {}).get("status") != "answered"]
    if open_must:
        problems.append("questions marked 'must answer' at CP4 are still open: " + ", ".join(open_must))
    accepted = [(i, items.get(layout, app, i)) for a in cp4[-1:] for i, d in (a.get("decisions") or {}).items()
                if d == "accept_assumption"]
    order = (idx or {}).get("run_order", {})
    lines = [f"# Readiness — {app}", "", f"Generated {now_iso()}. Target: `{b['dev_catalog']}.{b['dev_silver_schema']}` "
             "(dev). Promotion to test and prod is done by the deployment team.", "",
             "## Status", "", ("**Complete.**" if not problems else "**Not complete:**")]
    lines += [f"- {p}" for p in problems]
    lines += ["", "## Inputs", "",
              f"- STTM `{(idx or {}).get('sttm_version')}` approved at CP4" + (f" by {cp4[-1]['name_in_statement']}" if cp4 else ""),
              f"- Notebooks: `{iv.label if iv else '-'}`, masters: `{mv.label if mv else '-'}`",
              f"- QA: `{qv.label if qv else '-'}` ({'pass' if qa and qa.get('all_passed') else 'not passing'})",
              f"- Code review: `{rv.label if rv else '-'}`", "", "## Run order", ""]
    for k, v in order.items():
        lines.append(f"{k.split('_', 1)[0]}. {k.split('_', 1)[1].replace('_', ' ')}: {', '.join(v) or '—'}")
    lines += ["", "## Accepted assumptions (CP4)", ""]
    lines += [f"- {i}: {(it or {}).get('statement') or (it or {}).get('text')}" for i, it in accepted] or ["- none"]
    lines += ["", "## Notebooks", ""]
    lines += [f"- `{n['notebook']}.{n['version']}` → {t} ({n['kind']})" for t, n in (idx or {}).get("notebooks", {}).items()]
    return save_output(layout, app, "release/readiness", "\n".join(lines) + "\n", reason="readiness (P6.1)",
                       extra_meta={"complete": not problems, "problems": problems})


def build_h2(layout: Layout, app: str, apr: dict) -> str:
    """handoff/H2-nnn/ for the deployment team (after CP6)."""
    hid = next_id(layout, "H2", 3)
    dest = guard_write(layout.sub(app, "handoff", hid))
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {}

    def put(src, name=None):
        if src and src.exists():
            t = guard_write(dest / (name or src.name))
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, t)
            manifest[t.relative_to(dest).as_posix()] = sha256_file(t)

    _, idx = _latest(layout, app, "build/index", "json")
    for n in idx["notebooks"].values():
        v = versions.get(layout.stem(app, f"build/notebooks/{n['notebook']}"), int(n["version"][1:]), "py")
        put(v.path, f"notebooks/{n['notebook']}.py")
    _, mast = _latest(layout, app, "build/masters", "json")
    for m in mast["masters"].values():
        put(layout.root / m["notebook"], f"masters/{m['table']}.py")
    for stem, ext in (("qa/results", "json"), ("release/readiness", "md"), ("build/code_review", "md"), ("build/index", "json")):
        v = versions.latest(layout.stem(app, stem), ext)
        put(v.path if v else None)
    sv = versions.get(layout.stem(app, "sttm/sttm"), int(idx["sttm_version"][1:]), "json")
    put(sv.path)
    atomic_write(dest / "approvals.json", dump_json([a for a in approvals(layout, app) if a["point"] in ("CP4", "CP5", "CP6")]))
    manifest["approvals.json"] = sha256_file(dest / "approvals.json")
    atomic_write(dest / "README.md", (
        f"# Handoff {hid} — {app} (H2, to deployment)\n\nCP5 and CP6 passed their automatic checks ({apr['created']['at']}).\n"
        "Notebooks write to the dev silver schema; promotion to test and prod is the deployment team's job.\n"
        "Read `" + next(k for k in manifest if k.startswith("readiness")) + "` first (run order, assumptions).\n").encode("utf-8"))
    atomic_write(dest / "manifest.json", dump_json({"handoff": hid, "approval": apr["id"], "files": manifest}))
    emit_event(layout, "handoff_built", app=app, items=[apr["id"]], note=hid)
    return layout.rel(dest)
