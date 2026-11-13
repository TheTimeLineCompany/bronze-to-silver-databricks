"""Status of an application and the next steps (design §8.2, §8.3).

For each step: todo (no output yet) | waiting (inputs missing) | blocked (needs an approval) | stale (inputs or
config changed since the output was made) | current. For each approval point: latest version vs approved version.
"""
from __future__ import annotations

from . import versions
from .layout import Layout
from .steps import STEPS, current_inputs, ext_of, fingerprint


def step_status(layout: Layout, app: str, step_id: str) -> dict:
    step = STEPS[step_id]
    outs = {o: versions.latest(layout.stem(app, o), ext_of(o)) for o in step.outputs}
    have_inputs = current_inputs(layout, app, step)
    missing = [i for i in step.inputs if i not in have_inputs]
    if step.optional_inputs and not step.inputs and not have_inputs:
        missing = list(step.optional_inputs)
    res = {"step": step.id, "name": step.name, "runs_as": step.runs_as, "how": step.how,
           "outputs": {o: (v.label if v else None) for o, v in outs.items()}, "why": []}
    if missing:
        res["status"] = "waiting"
        res["why"].append("needs " + ", ".join(missing))
        return res
    if step.needs_approval:
        from .approve import approved_versions
        from .project import approval_points
        for point in step.needs_approval:
            ok = approved_versions(layout, app, point)
            for main in approval_points(layout)[point]["main"]:
                if main in have_inputs and have_inputs[main] not in ok.get(main, set()):
                    res["status"] = "blocked"
                    res["why"].append(f"{point}: approve {main.split('/')[-1]}.{have_inputs[main]} first")
        if res.get("status") == "blocked":
            return res
    if any(v is None for v in outs.values()):
        res["status"] = "todo"
        res["why"].append("no output yet: " + ", ".join(o for o, v in outs.items() if v is None))
        return res
    if step.inputs or step.optional_inputs or step.config_keys:
        fp = fingerprint(layout, app, step, have_inputs)
        for o, v in outs.items():
            if v.meta.get("fingerprint") != fp:
                changed = [f"{i} {v.meta.get('inputs', {}).get(i, '-')} -> {t}" for i, t in have_inputs.items()
                           if v.meta.get("inputs", {}).get(i) != t]
                res["why"].append(f"{o} is stale" + (": " + "; ".join(changed) if changed else " (config or step changed)"))
        if res["why"]:
            res["status"] = "stale"
            return res
    res["status"] = "current"
    return res


def approval_status(layout: Layout, app: str) -> list[dict]:
    from .approve import approved_versions
    from .project import approval_points
    out = []
    for point, cfg in approval_points(layout).items():
        ok = approved_versions(layout, app, point)
        files = []
        for main in cfg["main"]:
            v = versions.latest(layout.stem(app, main), ext_of(main))
            appr = sorted(ok.get(main, set()))
            files.append({"file": main, "latest": v.tag if v else None, "approved": appr,
                          "latest_approved": bool(v and v.tag in ok.get(main, set()))})
        exists = all(f["latest"] for f in files)
        state = "n/a" if not exists else ("approved" if all(f["latest_approved"] for f in files) else
                                          ("re-approval needed" if any(f["approved"] for f in files) else "not approved"))
        out.append({"point": point, "name": cfg["name"], "mode": cfg.get("mode", "chat"), "blocks": cfg.get("blocks"),
                    "state": state, "files": files})
    return out


def status(layout: Layout, app: str) -> dict:
    steps = [step_status(layout, app, s) for s in STEPS]
    order = {"stale": 0, "blocked": 1, "todo": 2}
    nxt = sorted([s for s in steps if s["status"] in order], key=lambda s: (order[s["status"]], list(STEPS).index(s["step"])))
    return {"app": app, "steps": steps, "approvals": approval_status(layout, app),
            "next": [{"step": s["step"], "status": s["status"], "do": s["how"], "why": s["why"]} for s in nxt]}


def rerun_plan(layout: Layout, app: str) -> list[dict]:
    """Stale and todo steps in graph order; a step listed after one it depends on."""
    st = {s["step"]: s for s in (step_status(layout, app, x) for x in STEPS)}
    return [{"step": k, "status": v["status"], "do": v["how"], "why": v["why"]}
            for k, v in st.items() if v["status"] in ("stale", "todo")]


def render_text(st: dict) -> str:
    """Short text for the chat or the notebook."""
    lines = [f"Application {st['app']}", ""]
    for s in st["steps"]:
        outs = ", ".join(t if t else f"{o.split('/')[-1]} -" for o, t in s["outputs"].items())
        lines.append(f"  {s['step']:<6} {s['name']:<44} {s['status']:<8} {outs}")
        for w in s["why"]:
            lines.append(f"        - {w}")
    lines.append("")
    lines.append("Approvals:")
    for a in st["approvals"]:
        files = ", ".join(f"{f['file'].split('/')[-1]}.{f['latest']}" + (f" (approved {', '.join(f['approved'])})" if f["approved"] else "")
                          for f in a["files"] if f["latest"])
        name = a["name"] + (" (automatic)" if a.get("mode") == "automatic" else "")
        lines.append(f"  {a['point']:<5} {name:<48} {a['state']:<20} {files}")
    if st["next"]:
        lines.append("")
        lines.append("Next:")
        for n in st["next"][:5]:
            lines.append(f"  {n['step']}: {n['do']}  [{n['status']}]")
    return "\n".join(lines)
