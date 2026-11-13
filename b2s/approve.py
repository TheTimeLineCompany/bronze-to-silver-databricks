"""Approvals in the chat (design §12).

Genie runs `request(...)`, shows `chat_text` (it ends with the statement template), and passes the worker's reply
VERBATIM to `record(...)`. The worker types only their name; the template already names the point and the file
versions:   I, <your name>, approve CP3 logical.v004.
The request keeps the exact file versions and hashes; `record` refuses when a file changed after the request.
"""
from __future__ import annotations

import html
import re

from . import items, versions
from .layout import Layout
from .project import approval_points, config as _config
from .steps import OUTPUT_TO_STEP, ext_of
from .store import atomic_write, dump_json, emit_event, load_any, next_id, now_iso, sha256_file, write_once

DECISION_VALUES = {
    "open_points": {"accept": "accepted", "change": "changed", "question": "question", "defer": "deferred"},
    "questions_assumptions": {"accept": "accept_assumption", "accept assumption": "accept_assumption",
                              "accept_assumption": "accept_assumption", "must answer": "must_answer",
                              "must_answer": "must_answer"},
}


class ApprovalError(ValueError):
    """The approval cannot be requested or recorded. The message says why, in plain words."""


# =========================================================================== reading approvals
def approvals(layout: Layout, app: str, point: str | None = None) -> list[dict]:
    return [a for a in items.list_items(layout, app, "approval") if point is None or a["point"] == point]


def approved_versions(layout: Layout, app: str, point: str) -> dict:
    """{stem: {'v003', 'v004'}} — every version of the point's main files that has an approval."""
    out: dict = {}
    for a in approvals(layout, app, point):
        for stem, f in a["files"].items():
            out.setdefault(stem, set()).add(f["version"])
    return out


# =========================================================================== readiness
def _main_versions(layout: Layout, app: str, point: str) -> dict:
    cfg = approval_points(layout)[point]
    out = {}
    for stem in cfg["main"]:
        v = versions.latest(layout.stem(app, stem), ext_of(stem))
        if not v:
            raise ApprovalError(f"{point} cannot be asked yet: {stem} does not exist")
        out[stem] = v
    return out


def _supporting(v: versions.Version) -> dict:
    out = {}
    for ext in ("mmd", "html", "xlsx"):
        p = v.companion(ext)
        if p.exists():
            out[p.name] = sha256_file(p)
    return out


def readiness(layout: Layout, app: str, point: str) -> list[str]:
    """Reasons why the point cannot be approved now (empty = ready)."""
    from .navigator import step_status
    pts = approval_points(layout)
    if point not in pts:
        return [f"unknown approval point {point}; known: {', '.join(pts)}"]
    cfg = pts[point]
    try:
        mains = _main_versions(layout, app, point)
    except ApprovalError as e:
        return [str(e)]
    reasons = []
    for stem, v in mains.items():
        if not versions.verify(v):
            reasons.append(f"{v.label} was edited by hand after it was saved (hash differs); save it as a new version")
        st = step_status(layout, app, OUTPUT_TO_STEP[stem])
        if st["status"] in ("stale", "blocked"):
            reasons.append(f"{v.label} is {st['status']}: " + "; ".join(st["why"]))
    # chain rule
    for req in cfg.get("requires") or []:
        ok = approved_versions(layout, app, req)
        for stem, v in mains.items():
            for rstem in pts[req]["main"]:
                used = v.meta.get("inputs", {}).get(rstem)
                if used and used not in ok.get(rstem, set()):
                    reasons.append(f"chain: {v.label} was made from {rstem.split('/')[-1]}.{used}, which needs {req} first")
    # content checks
    for stem, v in mains.items():
        missing = items.missing_refs(layout, app, versions.read(v)) if v.ext in ("json", "yaml") else []
        if missing:
            reasons.append(f"{v.label} refers to items that do not exist: {', '.join(missing)}")
        if stem.startswith("models/"):
            reasons += _model_checks(layout, stem, v)
    if "scope/scope" in mains:
        reasons += _scope_ready(versions.read(mains["scope/scope"]))
    if "sttm/sttm" in mains:
        from . import sttm
        reasons += [f"STTM: {e}" for e in sttm.validate(layout, app, versions.read(mains["sttm/sttm"]))]
    return reasons


def _model_checks(layout, stem, v) -> list[str]:
    from . import models
    from .project import ontology
    kind = stem.split("/")[-1]
    errs = [f"{v.label}: {e}" for e in models.validate(kind, versions.read(v), ontology(layout, "business"))]
    try:
        from . import viewer
    except ImportError:          # viewer not installed yet
        return errs
    mmd, htm = v.companion("mmd"), v.companion("html")
    if not (mmd.exists() and htm.exists()):
        viewer.write_views(v, kind, versions.read(v))
    errs += [f"{v.label} views: {e}" for e in viewer.check_views(kind, versions.read(v), mmd.read_text(encoding="utf-8"),
                                                                   htm.read_text(encoding="utf-8"))]
    return errs


def _scope_ready(scope: dict) -> list[str]:
    out = []
    for t, s in (scope.get("tables") or {}).items():
        if s.get("scope") == "review":
            out.append(f"scope: table {t} is still 'review' — decide in_scope or out_of_scope (tell Genie; it saves a new scope version)")
    tables = scope.get("tables") or {}
    for c, s in (scope.get("columns") or {}).items():
        if (tables.get(c.rsplit(".", 1)[0]) or {}).get("scope") not in ("in_scope", None):
            continue                     # the whole table is out of scope: its columns need no decision
        if s.get("scope") == "review":
            out.append(f"scope: column {c} is still 'review'")
        pv = s.get("privacy")
        if pv and s.get("scope") == "in_scope" and pv.get("handling") not in ("keep_tagged", "mask", "hash"):
            out.append(f"privacy: column {c} holds personal data — choose keep_tagged, mask or hash")
    return out


# =========================================================================== open decisions
def open_decisions(layout: Layout, app: str, point: str) -> list[dict]:
    """Open items to decide, pre-filled with the worker's previous decision for the same item, else a safe default."""
    prev = {}
    for a in sorted(approvals(layout, app, point), key=lambda a: a["created"]["at"]):
        prev.update(a.get("decisions") or {})
    back = {"accept_assumption": "accept", "must_answer": "must answer", "accepted": "accept", "changed": "change",
            "question": "question", "deferred": "defer"}
    out = _open_decisions(layout, app, point)
    for d in out:
        if d["id"] in prev:
            d["default"] = back.get(prev[d["id"]], d["default"])
    return out


def _open_decisions(layout: Layout, app: str, point: str) -> list[dict]:
    kind = approval_points(layout)[point].get("decisions")
    if kind == "open_points":
        return [{"id": op["id"], "about": f"{op.get('point')}: {', '.join(op.get('tables', []))}", "default": "accept",
                 "allowed": sorted(DECISION_VALUES[kind])} for op in items.list_items(layout, app, "open_point", status="open")]
    if kind == "questions_assumptions":
        out = [{"id": a["id"], "about": a["statement"], "default": "accept", "allowed": ["accept", "must answer"]}
               for a in items.list_items(layout, app, "assumption", status="active")]
        for q in items.list_items(layout, app, "question"):
            if q["status"] in ("open", "assumed"):
                out.append({"id": q["id"], "about": q["text"], "default": "accept" if q["status"] == "assumed" else "must answer",
                            "allowed": ["accept", "must answer"]})
        return out
    return []


# =========================================================================== request
def request(layout: Layout, app: str, point: str) -> dict:
    """Create an approval request. Raises ApprovalError with all reasons when the point is not ready."""
    _no_chat_for_automatic(layout, point)
    reasons = readiness(layout, app, point)
    if reasons:
        raise ApprovalError(f"{point} is not ready:\n- " + "\n- ".join(reasons))
    cfg = approval_points(layout)[point]
    mains = _main_versions(layout, app, point)
    rid = next_id(layout, "AR")
    files = {stem: {"version": v.tag, "label": v.label, "hash": v.meta["content_hash"], "supporting": _supporting(v),
                    "folder": v.path.parent.relative_to(layout.app_dir(app)).as_posix()}
             for stem, v in mains.items()}
    changes = {}
    prev = approved_versions(layout, app, point)
    for stem, v in mains.items():
        done = sorted(prev.get(stem, set()))
        if done and done[-1] != v.tag:
            try:
                changes[stem] = versions.diff(layout.stem(app, stem), int(done[-1][1:]), v.n, ext_of(stem))
            except Exception:  # pragma: no cover - diff is informative only
                pass
    decisions = open_decisions(layout, app, point)
    req = {"id": rid, "app": app, "point": point, "name": cfg["name"], "files": files, "decisions": decisions,
           "changes_since_last_approval": changes, "created": now_iso()}
    req["template"] = template(point, [f["label"] for f in files.values()], decisions)
    write_once(layout.review_dir(app) / f"{rid}.json", dump_json(req))
    atomic_write(layout.review_dir(app) / f"{rid}.html", _page(req).encode("utf-8"))
    emit_event(layout, "approval_requested", app=app, items=[rid], note=point)
    # the chat text is made for display only; request files hold data, never text addressed to an agent (I-17 §4)
    return {**req, "chat_text": chat_text(req, layout)}


def template(point: str, labels: list[str], decisions: list[dict]) -> str:
    lines = [f"I, <your name>, approve {point} {', '.join(labels)}."]
    lines += [f"{d['id']}: {d['default']}" for d in decisions]
    return "\n".join(lines)


def chat_text(req: dict, layout: Layout) -> str:
    files = "\n".join(f"> Files: `{stem}` — **{f['label']}**" for stem, f in req["files"].items())
    ch = ""
    for stem, d in (req.get("changes_since_last_approval") or {}).items():
        parts = [f"{len(d.get(k, []))} {k}" for k in ("added", "removed", "changed") if d.get(k)]
        ch += f"\n> Changed since {d['from']}: " + (", ".join(parts) or "text changes")
    dec = ""
    if req["decisions"]:
        dec = f"\n> Open: {len(req['decisions'])} item(s) to decide — pre-filled below, change any you disagree with."
    page = f"review/approvals/{req['id']}.html"
    return (f"> **Approval {req['point']} — {req['name']}, {req['app']}**\n{files}{ch}{dec}\n> Page: `{page}`\n>\n"
            f"> To approve, copy and complete:\n\n```\n{req['template']}\n```\n\nOr reply with changes, or \"later\".")


def _page(req: dict) -> str:
    e = html.escape
    rows = "".join(f"<tr><td>{e(s)}</td><td><b>{e(f['label'])}</b></td><td>"
                   + " ".join(f"<a href='../../{e(f['folder'])}/{e(n)}'>{e(n)}</a>" for n in f["supporting"])
                   + "</td></tr>" for s, f in req["files"].items())
    dec = "".join(f"<tr><td>{e(d['id'])}</td><td>{e(str(d['about']))}</td><td>{e(d['default'])}</td></tr>" for d in req["decisions"])
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{e(req['id'])} {e(req['point'])}</title>"
            "<style>body{font:15px/1.5 system-ui,sans-serif;color:#111827;background:#fff;margin:24px;max-width:960px}"
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #d1d5db;padding:6px 8px;text-align:left}"
            "pre{background:#f3f4f6;color:#111827;padding:12px}@media(prefers-color-scheme:dark){body{background:#111827;color:#f9fafb}"
            "td,th{border-color:#4b5563}pre{background:#1f2937;color:#f9fafb}a{color:#93c5fd}}</style></head><body>"
            f"<h1>Approval {e(req['point'])} — {e(req['name'])}</h1><p>Application <b>{e(req['app'])}</b>, request {e(req['id'])}</p>"
            f"<h2>Files</h2><table><tr><th>File</th><th>Version</th><th>Views</th></tr>{rows}</table>"
            + (f"<h2>Open decisions</h2><table><tr><th>Item</th><th>About</th><th>Pre-filled</th></tr>{dec}</table>" if dec else "")
            + f"<h2>Statement to copy</h2><pre>{e(req['template'])}</pre></body></html>")


# =========================================================================== record
AGENT_NAMES = {"genie", "genie code", "claude", "assistant", "the assistant", "agent", "the agent", "ai", "copilot",
               "databricks assistant", "framework", "framework checks", "system"}
_STMT = re.compile(r"^\s*I\s*,\s*(?P<name>[^,\n]+?)\s*,\s*approve[sd]?\b(?P<rest>.*)$", re.I)
_STMT_LOOSE = re.compile(r"^\s*I\s+(?P<name>[^\n]+?)\s+approve[sd]?\b(?P<rest>.*)$", re.I)
_LABEL = re.compile(r"\b([A-Za-z0-9_]+)\.v(\d{3})\b")
_DEC = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*[:=]\s*(.+?)\s*\.?\s*$")


def parse_statement(text: str) -> dict:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if not lines:
        raise ApprovalError("the reply is empty")
    m = _STMT.match(lines[0]) or _STMT_LOOSE.match(lines[0])
    if not m:
        raise ApprovalError("the reply is not an approval statement. Copy the template: I, <your name>, approve <point> <files>.")
    name = m["name"].strip()
    if "<" in name or not re.search(r"[A-Za-z]", name):
        raise ApprovalError("the statement needs your name in place of <your name>")
    if name.lower().strip(" .") in AGENT_NAMES:
        raise ApprovalError(f"'{name}' is an agent, not a person: the worker approves with their own name")
    decisions = {}
    for l in lines[1:]:
        d = _DEC.match(l)
        if d:
            decisions[d[1]] = d[2].strip().lower()
    return {"name": name, "rest": m["rest"], "labels": {f"{a}.v{b}" for a, b in _LABEL.findall(m["rest"])},
            "decisions": decisions}


def record(layout: Layout, app: str, request_id: str, statement: str, *, how: str = "chat") -> dict:
    """Record the worker's statement VERBATIM against a request. Raises ApprovalError with the reason."""
    path = layout.review_dir(app) / f"{request_id}.json"
    if not path.exists():
        raise ApprovalError(f"no approval request {request_id}")
    req = load_any(path)
    point, cfg = req["point"], approval_points(layout)[req["point"]]
    _no_chat_for_automatic(layout, point)
    if approvals_for_request(layout, app, request_id):
        raise ApprovalError(f"request {request_id} was already approved")
    st = parse_statement(statement)
    allowed = [a.lower() for a in (_config(layout).get("approvers") or [])]
    if allowed and st["name"].lower() not in allowed:
        raise ApprovalError(f"'{st['name']}' is not an approver of this project (project.yaml approvers)")
    rest = st["rest"].lower()
    if not (re.search(rf"\b{re.escape(point.lower())}\b", rest) or cfg["name"].lower() in rest):
        raise ApprovalError(f"the statement must name the approval point ({point} or '{cfg['name']}')")
    want = {f["label"] for f in req["files"].values()}
    missing = want - st["labels"]
    if missing:
        raise ApprovalError(f"the statement must name the file version(s): {', '.join(sorted(missing))}")
    wrong = {l for l in st["labels"] - want if l.rsplit('.v', 1)[0] in {w.rsplit('.v', 1)[0] for w in want}}
    if wrong:
        raise ApprovalError(f"version in the statement is not the version shown: {', '.join(sorted(wrong))} "
                            f"(request is for {', '.join(sorted(want))})")
    # freshness: nothing changed since the request was shown
    for stem, f in req["files"].items():
        v = versions.latest(layout.stem(app, stem), ext_of(stem))
        if v.tag != f["version"] or v.meta["content_hash"] != f["hash"] or not versions.verify(v):
            raise ApprovalError(f"{f['label']} changed after the request was shown (latest is {v.label}). "
                                f"Ask again: a new request shows the new version.")
        for name, h in f["supporting"].items():
            p = v.companion(name.rsplit(".", 1)[-1])
            if not p.exists() or sha256_file(p) != h:
                raise ApprovalError(f"{name} changed after the request was shown. Ask again.")
    # decisions
    decided = {}
    kind = cfg.get("decisions")
    if req["decisions"]:
        allowed = DECISION_VALUES[kind]
        for d in req["decisions"]:
            val = st["decisions"].get(d["id"])
            if val is None:
                raise ApprovalError(f"no decision for {d['id']} ({d['about']}). Keep the pre-filled line or change it.")
            if val not in allowed:
                raise ApprovalError(f"decision for {d['id']} is unclear: {val!r}. Use one of: {', '.join(d['allowed'])}")
            decided[d["id"]] = allowed[val]
    apr = items.create(layout, app, "approval", {
        "point": point, "request": request_id, "statement": statement, "name_in_statement": st["name"], "how": how,
        "approval_mode": "self", "files": {s: {"version": f["version"], "hash": f["hash"], "supporting": f["supporting"]}
                                            for s, f in req["files"].items()},
        "decisions": decided}, via="chat" if how == "chat" else "notebook", step=point)
    emit_event(layout, "approval_recorded", app=app, items=[apr["id"], request_id], note=point,
               via="chat" if how == "chat" else "notebook",
               extra={"statement": statement, "name_in_statement": st["name"], "how": how, "approval_mode": "self",
                      "files": {s: f["label"] for s, f in req["files"].items()}})
    _apply_decisions(layout, app, kind, decided, apr["id"])
    result = {"approval": apr, "decisions": decided}
    if cfg.get("blocks") == "handoff":
        from .handoff import build_handoff, pending_must_answer
        pend = pending_must_answer(layout, app, apr)
        result["handoff"] = None if pend else build_handoff(layout, app, apr)
        result["waiting_for"] = pend
    return result


def approvals_for_request(layout: Layout, app: str, request_id: str) -> list[dict]:
    return [a for a in approvals(layout, app) if a.get("request") == request_id]


def _apply_decisions(layout, app, kind, decided, apr_id):
    if kind == "open_points":
        for oid, status in decided.items():
            items.update(layout, app, oid, {"status": status, "decision_by": apr_id}, reason=f"decided in {apr_id}")


# =========================================================================== automatic checkpoints (CP5, CP6)
def _no_chat_for_automatic(layout: Layout, point: str) -> None:
    cfg = approval_points(layout).get(point) or {}
    if cfg.get("mode") == "automatic":
        raise ApprovalError(f"{point} is an automatic checkpoint: no person approves it. "
                            f"Run: python -m b2s cp-auto <app> {point}")


def automatic_checks(layout: Layout, app: str, point: str) -> list[str]:
    """Problems that stop an automatic checkpoint (empty list = pass)."""
    reasons = readiness(layout, app, point)
    if reasons and any("does not exist" in r for r in reasons):
        return reasons
    if point == "CP5":
        from .build.codegen import build_settings, notebook_problems
        from .build.qa import qa_problems
        b = build_settings(layout)
        idx = versions.read(versions.latest(layout.stem(app, "build/index"), "json"))
        for table, n in idx["notebooks"].items():
            v = versions.get(layout.stem(app, f"build/notebooks/{n['notebook']}"), int(n["version"][1:]), "py")
            reasons += [f"{n['notebook']}.{n['version']}: {p}" for p in notebook_problems(v.path.read_text(encoding="utf-8"), b)]
        for entity, m in versions.read(versions.latest(layout.stem(app, "build/masters"), "json"))["masters"].items():
            reasons += [f"master {entity}: {p}" for p in m["problems"]]
        reasons += qa_problems(layout, app)
        review = versions.read(versions.latest(layout.stem(app, "build/code_review"), "md"))
        if not re.search(r"^Verdict:\s*pass\b", review, re.M | re.I):
            reasons.append("code review (P5.3) has no 'Verdict: pass'")
    if point == "CP6":
        v = versions.latest(layout.stem(app, "release/readiness"), "md")
        if not v.meta.get("complete"):
            reasons += [f"readiness: {p}" for p in v.meta.get("problems") or ["not complete"]]
    return reasons


def run_automatic(layout: Layout, app: str, point: str) -> dict:
    """Evaluate an automatic checkpoint. When every check passes, record an approval item (how=automatic).
    CP6 also builds the H2 package for deployment."""
    cfg = approval_points(layout).get(point) or {}
    if cfg.get("mode") != "automatic":
        raise ApprovalError(f"{point} is approved by the worker in the chat, not automatically")
    problems = automatic_checks(layout, app, point)
    if problems:
        emit_event(layout, "automatic_checkpoint_failed", app=app, note=point, extra={"problems": problems})
        return {"point": point, "recorded": False, "problems": problems}
    mains = _main_versions(layout, app, point)
    labels = ", ".join(v.label for v in mains.values())
    apr = items.create(layout, app, "approval", {
        "point": point, "request": None, "how": "automatic", "approval_mode": "automatic",
        "name_in_statement": "framework checks",
        "statement": f"{point} passed all automatic checks for {labels}.",
        "files": {s: {"version": v.tag, "hash": v.meta["content_hash"], "supporting": {}} for s, v in mains.items()},
        "decisions": {}}, via="tool", step=point)
    emit_event(layout, "approval_recorded", app=app, items=[apr["id"]], note=point, via="tool",
               extra={"approval_mode": "automatic", "files": {s: v.label for s, v in mains.items()}})
    res = {"point": point, "recorded": True, "approval": apr}
    if point == "CP6":
        from .release import build_h2
        res["handoff"] = build_h2(layout, app, apr)
    return res
