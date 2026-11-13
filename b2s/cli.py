"""python -m b2s <command> — the commands Genie Code and the notebooks call.

The project folder comes from --project or the env B2S_PROJECT. Genie passes --via genie; notebooks set B2S_VIA=notebook.
Output is short text (or JSON with --json) so it fits in a chat.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import FRAMEWORK_VERSION, items, models, navigator, plugins, research, sttm, versions
from .approve import ApprovalError, record, request
from .columns import build_columns, draft_logical, set_scope
from .project import init_project, ontology, open_project, register_app
from .steps import OUTPUT_TO_STEP, ext_of, save_output
from .store import load_any


def _layout(a):
    root = a.project or os.environ.get("B2S_PROJECT")
    if not root:
        sys.exit("set --project or B2S_PROJECT to the project folder")
    return open_project(root)


def _out(a, obj, text=None):
    if a.json or text is None:
        print(json.dumps(obj, indent=2, default=str, ensure_ascii=False))
    else:
        print(text)


def _statement(a) -> str:
    """The worker's statement, verbatim: --statement-file <file> or --statement-file - (stdin); --statement as a fallback.
    Prefer stdin or a file: quotes and line breaks in a statement must not pass through shell quoting."""
    if a.statement_file == "-":
        return sys.stdin.read()
    if a.statement_file:
        return Path(a.statement_file).read_text(encoding="utf-8")
    if a.statement:
        return a.statement
    sys.exit("give the statement with --statement-file - (stdin) or --statement-file <file>")


def _load_json_arg(s: str):
    p = Path(s)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else json.loads(s)


# --------------------------------------------------------------------------- commands
def cmd_init(a):
    lay = init_project(a.root, a.name)
    print(f"project created: {lay.root} (framework {FRAMEWORK_VERSION})")


def cmd_register(a):
    lay = _layout(a)
    cfg = register_app(lay, a.app, a.name, a.schemas.split(","), a.lookups.split(",") if a.lookups else [])
    _out(a, cfg, f"registered {a.app}: schemas {cfg['schemas']}, lookups {cfg['lookup_schemas']}")


def cmd_status(a):
    lay = _layout(a)
    if a.brief:
        print(navigator.brief(lay, a.app))
        return
    st = navigator.status(lay, a.app)
    _out(a, st, navigator.render_text(st))


def cmd_doctor(a):
    from . import doctor
    from .install import refresh_project_agents
    lay = _layout(a)
    res = doctor.file_checks(lay)
    refresh_project_agents(lay)
    _out(a, res, doctor.render(res["results"]) + f"\ncapabilities: {res['capabilities']}")
    sys.exit(0 if all(r["ok"] is not False for k, r in res["results"].items() if k in ("K-01", "SHARED")) and
             res["capabilities"]["lock_mode"] != "none" else 1)


def cmd_install_skills(a):
    from .install import install_skills, refresh_project_agents
    lay = _layout(a) if (a.project or os.environ.get("B2S_PROJECT")) else None
    stamp = install_skills(a.target, lay)
    if lay:
        refresh_project_agents(lay)
    print(f"installed {len(stamp['skills'])} skills into {a.target} (framework {stamp['framework_version']})")


def cmd_save(a):
    """Save a file as the next version of a step output (Genie or the worker). Never edit a version file."""
    lay = _layout(a)
    if a.stem not in OUTPUT_TO_STEP:
        sys.exit(f"{a.stem} is not a step output; known: {', '.join(sorted(OUTPUT_TO_STEP))}")
    src = Path(a.file)
    ext = ext_of(a.stem)
    content = src.read_text(encoding="utf-8")
    if ext in ("yaml", "json"):
        content = load_any(src)
        if a.stem.startswith("models/"):
            kind = a.stem.split("/")[-1]
            errs = models.validate(kind, content, ontology(lay, "business"))
            if errs:
                sys.exit("not saved — model is not valid:\n- " + "\n- ".join(errs))
    v = save_output(lay, a.app, a.stem, content, reason=a.reason, via=a.via)
    if a.stem.startswith("models/"):
        from . import viewer
        viewer.write_views(v, a.stem.split("/")[-1], versions.read(v))
    print(f"{'saved' if v.created else 'unchanged'}: {v.label} ({lay.rel(v.path)})")


def cmd_diff(a):
    lay = _layout(a)
    d = versions.diff(lay.stem(a.app, a.stem), int(a.a.lstrip("v")), int(a.b.lstrip("v")), ext_of(a.stem))
    _out(a, d)


def cmd_view(a):
    from . import viewer
    lay = _layout(a)
    kinds = [a.model] if a.model else list(models.MODELS)
    for k in kinds:
        stem = lay.stem(a.app, f"models/{k}")
        v = versions.get(stem, int(a.version.lstrip("v")), "yaml") if a.version else versions.latest(stem, "yaml")
        if not v:
            print(f"{k}: no version yet")
            continue
        r = viewer.write_views(v, k, versions.read(v))
        status = "OK — HTML matches the Mermaid" if not r["errors"] else "DIFFERENT:\n  - " + "\n  - ".join(r["errors"])
        print(f"{v.label}: {lay.rel(r['html'])} {status}")


def cmd_columns(a):
    lay = _layout(a)
    cv, sv = build_columns(lay, a.app)
    data = versions.read(cv)
    unclear = sum(1 for t in data["tables"].values() for c in t["columns"].values() if c["status"] == "unclear")
    sc = versions.read(sv)
    review = [t for t, s in sc["tables"].items() if s["scope"] == "review"]
    print(f"{cv.label}, {sv.label}: {unclear} unclear columns; tables to decide: {', '.join(review) or 'none'}")


def cmd_scope(a):
    lay = _layout(a)
    v = set_scope(lay, a.app, a.target, scope=a.scope, handling=a.handling, reason=a.reason, via=a.via)
    print(f"saved {v.label}: {a.target} -> {a.scope or ''} {a.handling or ''}".rstrip())


def cmd_draft_logical(a):
    lay = _layout(a)
    v = draft_logical(lay, a.app)
    from . import viewer
    viewer.write_views(v, "logical", versions.read(v))
    print(f"{'saved' if v.created else 'unchanged'}: {v.label}")


def cmd_draft_sttm(a):
    lay = _layout(a)
    v = sttm.draft(lay, a.app)
    errs = sttm.validate(lay, a.app, versions.read(v))
    plugins.export_sttm(lay, a.app, v)
    c = sttm.counts(versions.read(v))
    print(f"{v.label}: {c['known']} known, {c['assumed']} assumed, {c['unknown']} unknown; "
          + ("valid" if not errs else "errors:\n- " + "\n- ".join(errs)))


def cmd_check(a):
    """All checks: model rules, views match Mermaid, version files untouched, STTM rules."""
    from . import viewer
    lay = _layout(a)
    problems = []
    for f in lay.app_dir(a.app).rglob("*.meta.json"):
        meta = json.loads(f.read_text(encoding="utf-8"))
        base = f.name[: -len(f".v{meta['n']:03d}.meta.json")]
        v = versions.get(f.parent / base, meta["n"], meta["ext"])
        if v and not versions.verify(v):
            problems.append(f"{v.label}: edited by hand after it was saved")
    for k in models.MODELS:
        v = versions.latest(lay.stem(a.app, f"models/{k}"), "yaml")
        if v:
            m = versions.read(v)
            problems += [f"{v.label}: {e}" for e in models.validate(k, m, ontology(lay, "business"))]
            problems += [f"{v.label}: refers to missing item {r}" for r in items.missing_refs(lay, a.app, m)]
            if v.companion("mmd").exists() and v.companion("html").exists():
                problems += [f"{v.label} views: {e}" for e in viewer.check_views(
                    k, m, v.companion("mmd").read_text(encoding="utf-8"), v.companion("html").read_text(encoding="utf-8"))]
    sv = versions.latest(lay.stem(a.app, "sttm/sttm"), "json")
    if sv:
        problems += [f"{sv.label}: {e}" for e in sttm.validate(lay, a.app, versions.read(sv))]
    print("CHECKS OK" if not problems else "PROBLEMS:\n- " + "\n- ".join(problems))
    sys.exit(1 if problems else 0)


def cmd_item(a):
    lay = _layout(a)
    if a.action == "new":
        it = items.create(lay, a.app, a.kind, _load_json_arg(a.data), via=a.via)
    elif a.action == "update":
        it = items.update(lay, a.app, a.kind, _load_json_arg(a.data), reason=a.reason or "update", via=a.via)
    elif a.action == "get":
        it = items.get(lay, a.app, a.kind)
    else:
        it = items.list_items(lay, a.app, a.kind)
    _out(a, it)


def cmd_research(a):
    lay = _layout(a)
    if a.action == "new":
        r = research.new_round(lay, a.app, a.arg, _load_json_arg(a.data), budget=a.budget, via=a.via)
        print(f"{r['id']} drafted. Send it:\n\n{research.request_text(lay, a.app, r['id'])}")
    elif a.action == "text":
        print(research.request_text(lay, a.app, a.arg))
    elif a.action == "sent":
        research.mark_sent(lay, a.app, a.arg, a.channel)
        print(f"{a.arg} sent via {a.channel}")
    elif a.action == "raw":
        raw = Path(a.data).read_text(encoding="utf-8") if a.data and Path(a.data).exists() else sys.stdin.read()
        research.record_raw(lay, a.app, a.arg, raw, channel=a.channel, via=a.via)
        print(f"{a.arg}: raw reply saved")
    elif a.action == "parse":
        _out(a, research.parse(lay, a.app, a.arg, _load_json_arg(a.data) if a.data else None))
    elif a.action == "integrate":
        print("evidence: " + ", ".join(research.integrate(lay, a.app, a.arg, _load_json_arg(a.data), via=a.via)))


def cmd_approve(a):
    lay = _layout(a)
    try:
        if a.action == "request":
            req = request(lay, a.app, a.arg)
            _out(a, req, req["chat_text"])
        else:
            stmt = _statement(a)
            res = record(lay, a.app, a.arg, stmt, how=a.how)
            msg = f"recorded {res['approval']['id']} ({res['approval']['point']}) for {res['approval']['name_in_statement']}"
            if res.get("decisions"):
                msg += "\nDecisions: " + ", ".join(f"{k}={v}" for k, v in res["decisions"].items())
            if "handoff" in res:
                msg += f"\nHandoff: {res['handoff']}" if res["handoff"] else \
                    f"\nHandoff waits for answers to: {', '.join(res['waiting_for'])}"
            _out(a, res, msg)
    except ApprovalError as e:
        sys.exit(f"NOT RECORDED: {e}")


def cmd_plugin(a):
    lay = _layout(a)
    if a.action == "install":
        _out(a, plugins.install(lay, a.arg))
    elif a.action == "activate":
        _out(a, plugins.activate(lay, a.arg, _statement(a)))
    elif a.action == "package":
        print(plugins.package(lay, a.arg, Path(a.note).read_text(encoding="utf-8") if Path(a.note).exists() else a.note))
    else:
        for slot in plugins.SLOTS:
            try:
                _, info = plugins.resolve(lay, slot)
                print(f"{slot:<20} {info['name']} {info['version']} ({info['origin']})")
            except plugins.PluginError:
                print(f"{slot:<20} -")


# --------------------------------------------------------------------------- P5 build, P6 release
def cmd_build(a):
    """P5.1 notebooks + P5.4 master builds from the CP4-approved STTM."""
    from .build import generate, generate_masters
    lay = _layout(a)
    res = generate(lay, a.app)
    mv = generate_masters(lay, a.app)
    print(f"{res['index'].label}: {len(res['notebooks'])} notebooks; {mv.label}")
    for name, rep in res["reports"].items():
        for k, v in rep.items():
            print(f"  {name}: {k}: {', '.join(v)}")
    for e, m in versions.read(mv)["masters"].items():
        print(f"  master {e}: {m['notebook']}")
        for prob in m["problems"]:
            print(f"    PROBLEM: {prob}")


def cmd_build_save(a):
    """Save a notebook whose TODO(genie) cells were completed, as a new version."""
    from .build import save_notebook
    lay = _layout(a)
    print(save_notebook(lay, a.app, a.file, reason=a.reason, via=a.via))


def cmd_qa_plan(a):
    from .build import make_plan
    lay = _layout(a)
    v = make_plan(lay, a.app)
    print(f"{v.label}: {len(versions.read(v)['tables'])} tables. Next: run notebook nb_p5_qa.")


def cmd_qa_record(a):
    """Fallback: record QA results from a JSON file (normally nb_p5_qa does this)."""
    from .build import record_results
    lay = _layout(a)
    v = record_results(lay, a.app, _load_json_arg(a.results), via=a.via)
    print(f"{v.label}: all_passed={versions.read(v)['all_passed']}")


def cmd_cp_auto(a):
    from .approve import run_automatic
    lay = _layout(a)
    res = run_automatic(lay, a.app, a.point)
    if not res["recorded"]:
        sys.exit(f"{a.point} NOT PASSED:" + "".join(f"\n- {p}" for p in res["problems"]))
    print(f"{a.point} passed: {res['approval']['id']}" + (f"; handoff {res['handoff']}" if res.get("handoff") else ""))


def cmd_release(a):
    from .release import readiness
    lay = _layout(a)
    v = readiness(lay, a.app)
    print(f"{v.label}: " + ("complete" if v.meta.get("complete") else
                            "NOT complete:" + "".join(f"\n- {p}" for p in v.meta.get("problems") or [])))


# --------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="b2s", description=f"Bronze-to-Silver framework {FRAMEWORK_VERSION}")
    p.add_argument("--project")
    p.add_argument("--via", default=os.environ.get("B2S_VIA", "tool"), choices=["genie", "notebook", "tool", "manual"])
    p.add_argument("--json", action="store_true")
    sp = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, *args):
        s = sp.add_parser(name)
        for spec in args:
            s.add_argument(*spec[0], **spec[1])
        s.set_defaults(fn=fn)
        return s

    APP = (["app"], {})
    add("init", cmd_init, (["root"], {}), (["name"], {}))
    add("register", cmd_register, APP, (["name"], {}), (["--schemas"], {"required": True}), (["--lookups"], {}))
    add("status", cmd_status, APP, (["--brief"], {"action": "store_true", "help": "handover text for a new chat"}))
    add("doctor", cmd_doctor)
    add("install-skills", cmd_install_skills, (["target"], {"help": "Genie skill folder, e.g. /Workspace/Users/<me>/.assistant/skills"}))
    add("save", cmd_save, APP, (["stem"], {}), (["file"], {}), (["--reason"], {"required": True}))
    add("diff", cmd_diff, APP, (["stem"], {}), (["a"], {}), (["b"], {}))
    add("view", cmd_view, APP, (["model"], {"nargs": "?"}), (["version"], {"nargs": "?"}))
    add("columns", cmd_columns, APP)
    add("scope", cmd_scope, APP, (["target"], {}), (["--scope"], {}), (["--handling"], {}), (["--reason"], {"required": True}))
    add("draft-logical", cmd_draft_logical, APP)
    add("draft-sttm", cmd_draft_sttm, APP)
    add("check", cmd_check, APP)
    add("build", cmd_build, APP)
    add("build-save", cmd_build_save, APP, (["file"], {}), (["--reason"], {"required": True}))
    add("qa-plan", cmd_qa_plan, APP)
    add("qa-record", cmd_qa_record, APP, (["results"], {"help": "JSON file or text with a list of check results"}))
    add("cp-auto", cmd_cp_auto, APP, (["point"], {"choices": ["CP5", "CP6"]}))
    add("release", cmd_release, APP)
    add("item", cmd_item, (["action"], {"choices": ["new", "update", "get", "list"]}), APP,
        (["kind"], {"help": "kind (new/list) or item id (update/get)"}), (["--data"], {}), (["--reason"], {}))
    add("research", cmd_research, (["action"], {"choices": ["new", "text", "sent", "raw", "parse", "integrate"]}), APP,
        (["arg"], {"help": "round type (new) or GR id"}), (["--data"], {}), (["--budget"], {"type": int, "default": 5}),
        (["--channel"], {"default": "paste", "choices": ["paste", "connector"]}))
    add("approve", cmd_approve, (["action"], {"choices": ["request", "record"]}), APP,
        (["arg"], {"help": "checkpoint CP1..CP4 (request) or AR id (record)"}), (["--statement"], {}),
        (["--statement-file"], {}), (["--how"], {"default": "chat", "choices": ["chat", "notebook"]}))
    pl = add("plugin", cmd_plugin, (["action"], {"choices": ["install", "activate", "package", "list"]}),
             (["arg"], {"nargs": "?"}), (["--statement"], {}), (["--statement-file"], {}), (["--note"], {}))
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):          # Windows consoles: show dashes and arrows correctly
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass
    a = build_parser().parse_args(argv)
    os.environ.setdefault("B2S_VIA", a.via)
    a.fn(a)


if __name__ == "__main__":  # pragma: no cover
    main()
