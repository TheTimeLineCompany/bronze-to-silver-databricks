"""Handoff package H1 after CP4 (design §12.4). Team 2 is the first second pair of eyes, so the readme opens with
the self-approval statement, the counts of known / assumed / unknown mappings, and the Genie-made items."""
from __future__ import annotations

import csv
import io
import shutil

from . import items, sttm as sttm_mod, versions
from .layout import Layout, guard_write
from .steps import ext_of
from .store import atomic_write, dump_json, emit_event, next_id, now_iso, sha256_file


def pending_must_answer(layout: Layout, app: str, apr: dict) -> list[str]:
    """Questions marked must_answer at CP4 that are still not answered."""
    out = []
    for qid, dec in (apr.get("decisions") or {}).items():
        if dec == "must_answer" and qid.startswith("Q-"):
            q = items.get(layout, app, qid)
            if q and q["status"] != "answered":
                out.append(qid)
    return out


def _genie_untouched(layout: Layout, app: str) -> list[dict]:
    out = []
    for kind in ("evidence", "assumption", "question"):
        for it in items.list_items(layout, app, kind):
            if it["created"].get("via") == "genie" and (it.get("updated") or {}).get("via", "genie") == "genie":
                out.append({"id": it["id"], "text": it.get("statement") or it.get("text")})
    return out


def build_handoff(layout: Layout, app: str, apr: dict) -> str:
    """Write handoff/H-nnn/ with the approved STTM and everything team 2 needs. Returns the folder (relative)."""
    hid = next_id(layout, "H", 3)
    dest = guard_write(layout.sub(app, "handoff", hid))
    dest.mkdir(parents=True, exist_ok=True)
    sv = versions.get(layout.stem(app, "sttm/sttm"), int(apr["files"]["sttm/sttm"]["version"][1:]), "json")
    st = versions.read(sv)
    lv = versions.get(layout.stem(app, "models/logical"), int(st["logical_version"][1:]), "yaml")
    manifest = {}

    def put(src, name=None):
        if src and src.exists():
            target = dest / (name or src.name)
            shutil.copyfile(src, guard_write(target))
            manifest[target.name] = sha256_file(target)

    for v in (sv, lv):
        put(v.path)
        for ext in ("mmd", "html", "xlsx"):
            put(v.companion(ext))
    mv = versions.latest(layout.stem(app, "models/mapping"), "yaml")
    if mv:
        put(mv.path)
        for ext in ("mmd", "html"):
            put(mv.companion(ext))
    # assumptions, questions and decisions
    dec = apr.get("decisions") or {}
    assumptions = [{"id": a["id"], "statement": a["statement"], "decision": dec.get(a["id"])}
                   for a in items.list_items(layout, app, "assumption")]
    questions = [{"id": q["id"], "text": q["text"], "status": q["status"], "decision": dec.get(q["id"])}
                 for q in items.list_items(layout, app, "question")]
    atomic_write(dest / "assumptions_and_questions.json", dump_json({"assumptions": assumptions, "questions": questions}))
    # evidence register
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "statement", "status", "confidence", "origin", "root_source", "via"])
    for e in items.list_items(layout, app, "evidence"):
        w.writerow([e["id"], e["statement"], e["status"], e["confidence"], (e.get("origin") or {}).get("type"),
                    e["root_source"], e["created"].get("via")])
    atomic_write(dest / "evidence_register.csv", buf.getvalue().encode("utf-8"))
    atomic_write(dest / "approvals.json", dump_json(items.list_items(layout, app, "approval")))
    for f in ("assumptions_and_questions.json", "evidence_register.csv", "approvals.json"):
        manifest[f] = sha256_file(dest / f)
    c = sttm_mod.counts(st)
    genie = _genie_untouched(layout, app)
    accepted = [a for a in assumptions if a["decision"] == "accept_assumption"]
    readme = [
        f"# Handoff {hid} — {app}",
        "",
        "## Handoff statement",
        "",
        f"**Self-approved**, signed '{apr['name_in_statement']}' from the account `{(apr.get('account') or {}).get('email') or apr['created']['by']}`"
        f"{'' if apr.get('signature_matches_account', True) else ' (the signature is not the account name)'} on {apr['created']['at']}, "
        f"in the {apr['how']}. There is no maker-checker in team 1: team 2 is the first second pair of eyes.",
        "",
        f"> {apr['statement'].strip().splitlines()[0]}",
        "",
        f"- STTM: `{sv.label}` (from logical model `{lv.label}`)",
        f"- Mappings: {c['known']} known, {c['assumed']} assumed, {c['unknown']} unknown",
        f"- Accepted assumptions: {len(accepted)}" + "".join(f"\n  - {a['id']}: {a['statement']}" for a in accepted),
        f"- Items made by Genie and not changed by the worker since: {len(genie)}"
        + "".join(f"\n  - {g['id']}: {g['text']}" for g in genie[:30]),
        "",
        "Send findings back as input to team 1; they reopen the work and lead to a new STTM version and a new CP4.",
        "",
        "## Files",
        "",
    ] + [f"- `{n}` {h}" for n, h in sorted(manifest.items())]
    atomic_write(dest / "README.md", ("\n".join(readme) + "\n").encode("utf-8"))
    atomic_write(dest / "manifest.json", dump_json({"handoff": hid, "approval": apr["id"], "created": now_iso(),
                                                    "files": manifest}))
    emit_event(layout, "handoff_built", app=app, items=[apr["id"]], note=hid,
               outputs={layout.rel(dest / "manifest.json"): sha256_file(dest / "manifest.json")})
    return layout.rel(dest)
