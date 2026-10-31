#!/usr/bin/env python3
"""Human feedback at any checkpoint, and the rerun it causes.

A person can give feedback in many forms. Each feedback item is ONE YAML file:
    sources/<id>/<phase folder>/feedback/<checkpoint>/FB-S07-k2q9.yaml   (or registry/feedback/<checkpoint>/ for global)
    phase folder per checkpoint: see CP_FOLDER below (CP1 -> 01_intake, CP2 -> 02_evidence, ...)
It can hold any mix of: comment, include_paths, ignore_paths, code, data, attachments, answer.
Template: skills/x-feedback-rerun/templates/feedback.yaml

Lifecycle:  open -> in_progress -> applied (agent) -> verified (person)  | rejected (person, with reason)

Upstream issues (agent -> earlier phase):
  A skill that finds a problem it cannot fix in its own phase (missing evidence, wrong grain, a key that is not
  unique) does NOT work around it. It raises an item on the EARLIER checkpoint with status 'proposed':
      python tools/x_feedback.py raise S07_container_moves CP2_evidence --step p4-1-sttm-author \
             --comment "No evidence for LEGS.CARRIER_REF meaning" --blocks CP4_sttm
  A person triages it: 'accept' -> open (normal loop: plan, reset, rerun) or 'set ... rejected' with a reason.
  'proposed' does not block the earlier checkpoint, but it blocks the checkpoint named in --blocks.
  Loop guard: give --related FB-xxxx when the same problem comes back; the third time, x_validate_gate fails
  and a person must decide. All items, human and agent, are on one board: tools/x_checkpoint_pack.py board
A checkpoint cannot be approved while any of its feedback is open, in_progress, or applied
(tools/x_validate_gate.py checks this). The person who gave feedback closes it by verifying.

Commands:
    python tools/x_feedback.py new S07_container_moves CP2_evidence --comment "..." [--include 00_inbox/X/] [--ignore 00_inbox/Old/] [--rerun-from p2-3-evidence-reconcile]
    python tools/x_feedback.py list [S07_container_moves] [--open]
    python tools/x_feedback.py plan FB-0003 --source S07_container_moves      # which steps rerun, which checkpoints reset
    python tools/x_feedback.py reset FB-0003 --source S07_container_moves     # set those checkpoints back to pending
    python tools/x_feedback.py set FB-0003 applied --source S07_container_moves --summary "..." [--changed a b]
    python tools/x_feedback.py log S07_container_moves p2-3-evidence-reconcile --feedback FB-0003 --note "..."
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Step catalogue: skill -> phase -> checkpoint. Single place of truth (also shown in docs/process_map.html).
STEPS = [
    ("p1-1-inventory",          "P1", "CP1_source_brief"),
    ("p1-2-triage",             "P1", "CP1_source_brief"),
    ("p1-3-source-brief",       "P1", "CP1_source_brief"),
    ("p2-1-doc-profiles",       "P2", "CP2_evidence"),
    ("p2-2-bronze-discovery",    "P2", "CP2_evidence"),
    ("p2-3-evidence-reconcile", "P2", "CP2_evidence"),
    ("p3-1-entity-model",       "P3", "CP3_central_model"),
    ("p4-1-sttm-author",        "P4", "CP4_sttm"),
    ("p4-2-sttm-validate",      "P4", "CP4_sttm"),
    ("p4-3-sttm-review",        "P4", "CP4_sttm"),
    ("p4-4-sttm-export",        "P4", "CP4_sttm"),
    ("p5-1-pyspark-codegen",    "P5", "CP5_code_qa"),
    ("p5-2-qa-runner",          "P5", "CP5_code_qa"),
    ("p5-3-code-review",        "P5", "CP5_code_qa"),
    ("p6-1-handoff-package",    "P6", "CP6_handoff"),
]
SOURCE_CP_ORDER = ["CP1_source_brief", "CP2_evidence", "CP4_sttm", "CP4b_business_logic", "CP5_code_qa", "CP6_handoff"]
GLOBAL_CPS = ["CP3_central_model", "CP3b_key_rules"]
FIRST_STEP = {"CP1_source_brief": "p1-2-triage", "CP2_evidence": "p2-3-evidence-reconcile",
              "CP3_central_model": "p3-1-entity-model", "CP3b_key_rules": "p3-1-entity-model",
              "CP4_sttm": "p4-1-sttm-author", "CP4b_business_logic": "p4-1-sttm-author",
              "CP5_code_qa": "p5-1-pyspark-codegen", "CP6_handoff": "p6-1-handoff-package"}
KINDS = ["comment", "include_paths", "ignore_paths", "code", "data", "attachments", "answer"]
STATUSES = ["proposed", "open", "in_progress", "applied", "verified", "rejected"]
BLOCKING = {"open", "in_progress", "applied"}          # block their own checkpoint
UNRESOLVED = BLOCKING | {"proposed"}                 # block the checkpoint named in "blocks"
MAX_REPEATS = 2                                      # same problem raised more often -> a person decides
# Phase folder of each source checkpoint (folder number = phase number). P3 is global: registry/.
CP_FOLDER = {"CP1_source_brief": "01_intake", "CP2_evidence": "02_evidence", "CP4_sttm": "04_mapping",
             "CP4b_business_logic": "04_mapping", "CP5_code_qa": "05_build", "CP6_handoff": "06_handoff"}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fb_dir(source_id, checkpoint, root=ROOT):
    if source_id == "global":
        return os.path.join(root, "registry", "feedback", checkpoint)
    return os.path.join(root, "sources", source_id, CP_FOLDER[checkpoint], "feedback", checkpoint)


def all_feedback(root=ROOT, source_id=None):
    pats = [os.path.join(root, "sources", "*", "*", "feedback", "*", "FB-*.yaml"),
            os.path.join(root, "registry", "feedback", "*", "FB-*.yaml")]
    out = []
    for p in sorted(sum((glob.glob(x) for x in pats), [])):
        with open(p, encoding="utf-8") as f:
            d = yaml.safe_load(f) or {}
        d["_path"] = os.path.relpath(p, root)
        if source_id and d.get("source_id") != source_id:
            continue
        out.append(d)
    return out


def validate_item(d):
    errs = []
    for k in ("id", "source_id", "checkpoint", "raised_by", "status"):
        if not d.get(k):
            errs.append(f"{d.get('_path')}: missing '{k}'")
    if d.get("checkpoint") not in SOURCE_CP_ORDER + GLOBAL_CPS:
        errs.append(f"{d.get('_path')}: unknown checkpoint '{d.get('checkpoint')}'")
    if d.get("status") not in STATUSES:
        errs.append(f"{d.get('_path')}: status must be one of {STATUSES}")
    if not any(d.get(k) for k in KINDS):
        errs.append(f"{d.get('_path')}: give at least one of {KINDS}")
    if d.get("rerun_from") and d["rerun_from"] not in [s for s, _, _ in STEPS]:
        errs.append(f"{d.get('_path')}: rerun_from '{d['rerun_from']}' is not a known step")
    if d.get("status") == "rejected" and not (d.get("response") or {}).get("summary"):
        errs.append(f"{d.get('_path')}: rejected feedback needs response.summary with the reason")
    if d.get("blocks") and d["blocks"] not in SOURCE_CP_ORDER + GLOBAL_CPS:
        errs.append(f"{d.get('_path')}: blocks '{d['blocks']}' is not a checkpoint")
    if d.get("status") == "proposed" and not str(d.get("raised_by", "")).startswith("agent:"):
        errs.append(f"{d.get('_path')}: only agent-raised items use status 'proposed'")
    if d.get("status") == "verified" and not d.get("verified_by"):
        errs.append(f"{d.get('_path')}: verified feedback needs verified_by")
    return errs


def repeats(d, items):
    """Length of the 'related' chain behind an item (1 = first time)."""
    by_id = {x["id"]: x for x in items}
    n, cur, seen = 1, d, set()
    while cur.get("related") and cur["related"] in by_id and cur["related"] not in seen:
        seen.add(cur["related"])
        cur = by_id[cur["related"]]
        n += 1
    return n


def raise_item(source_id, checkpoint, step, comment, blocks=None, related=None, root=ROOT, target=None):
    """Programmatic 'raise' (used by tools such as p2_2_discover merge). Returns the new FB id."""
    fid = next_id(root, source_id)
    d = {"id": fid, "source_id": source_id, "checkpoint": checkpoint, "raised_by": f"agent:{step}", "raised_on": _now(),
         "origin": "upstream_issue", "blocks": blocks, "related": related, "target": target, "comment": comment,
         "include_paths": None, "ignore_paths": None, "code": None, "data": None, "attachments": None, "answer": None,
         "rerun_from": None, "status": "proposed", "response": None, "verified_by": None}
    errs = validate_item({**d, "_path": fid})
    if errs:
        raise ValueError("; ".join(errs))
    os.makedirs(fb_dir(source_id, checkpoint, root), exist_ok=True)
    with open(os.path.join(fb_dir(source_id, checkpoint, root), f"{fid}.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(d, f, sort_keys=False, allow_unicode=True)
    return fid


def next_id(root=ROOT, source_id="global"):
    """Collision-free id: FB-<source code>-<4 random characters>, e.g. FB-S07-k2q9 or FB-GLB-7mxa.
    Random, not sequential, so two people raising feedback in parallel branches never get the same id.
    (Older ids such as FB-0001 stay valid.)"""
    import secrets
    code = "GLB" if source_id == "global" else str(source_id).split("_")[0].upper()
    taken = {str(d.get("id")) for d in all_feedback(root)}
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"          # no 0/o/1/l/i: easy to read aloud
    while True:
        fid = f"FB-{code}-" + "".join(secrets.choice(alphabet) for _ in range(4))
        if fid not in taken:
            return fid


def plan(fb):
    step = fb.get("rerun_from") or FIRST_STEP[fb["checkpoint"]]
    idx = [s for s, _, _ in STEPS].index(step)
    steps = [s for s, _, _ in STEPS[idx:]]
    step_cp = STEPS[idx][2]
    if step_cp in GLOBAL_CPS:
        reset = GLOBAL_CPS[GLOBAL_CPS.index(step_cp):] + ["(every source: CP4_sttm and later)"]
    else:
        reset = SOURCE_CP_ORDER[SOURCE_CP_ORDER.index(step_cp):]
    # steps after the checkpoint's phase are only re-run if their inputs changed; list them as 'then check'
    phase_steps = [s for s, p, c in STEPS if c == step_cp and [x for x, _, _ in STEPS].index(s) >= idx]
    global_steps = {x for x, _, c in STEPS if c in GLOBAL_CPS}
    later = [s for s in steps if s not in phase_steps and (step_cp in GLOBAL_CPS or s not in global_steps)]
    return {"rerun_now": phase_steps, "then_recheck": later, "reset_checkpoints": reset}


def reset(source_id, checkpoints, root=ROOT):
    p = os.path.join(root, "registry", "sources.yaml")
    with open(p, encoding="utf-8") as f:
        reg = yaml.safe_load(f)
    changed = []

    def _pend(g, label):
        if g and g.get("status") in ("approved", "in_review"):
            g.update(status="pending", approved_by=None, date=None, pr=None)
            changed.append(label)
    if source_id == "global":
        # a central-model change resets the global checkpoints AND every source from CP4_sttm on
        for cp in checkpoints:
            if cp in GLOBAL_CPS:
                _pend(reg.get("global_checkpoints", {}).get(cp), cp)
        downstream = SOURCE_CP_ORDER[SOURCE_CP_ORDER.index("CP4_sttm"):]
        for s in reg["sources"]:
            for cp in downstream:
                _pend(s.get("checkpoints", {}).get(cp), f"{s['id']}.{cp}")
    for s in reg["sources"]:
        if s["id"] != source_id:
            continue
        for cp in checkpoints:
            _pend(s["checkpoints"].get(cp), cp)
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(reg, f, sort_keys=False)
    return changed


def log_run(source_id, step, feedback=None, note="", outputs=None, root=ROOT):
    p = os.path.join(root, "sources", source_id, "run_log.jsonl")
    rec = {"run_id": "R-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"), "ts": _now(), "step": step,
           "feedback": feedback or [], "note": note, "outputs": outputs or []}
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def _find(fid, source_id, root=ROOT):
    for d in all_feedback(root, source_id):
        if d.get("id") == fid:
            return d
    raise SystemExit(f"{fid} not found")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("source_id")
    n.add_argument("checkpoint")
    n.add_argument("--by", default=os.environ.get("USER", "reviewer"))
    n.add_argument("--comment")
    n.add_argument("--include", nargs="*")
    n.add_argument("--ignore", nargs="*")
    n.add_argument("--code")
    n.add_argument("--data-table")
    n.add_argument("--data-filter")
    n.add_argument("--attach", nargs="*")
    n.add_argument("--target-artifact")
    n.add_argument("--target-location")
    n.add_argument("--rerun-from")
    r = sub.add_parser("raise", help="agent raises an upstream issue on an earlier checkpoint (status proposed)")
    r.add_argument("source_id")
    r.add_argument("checkpoint", help="the EARLIER checkpoint that owns the problem")
    r.add_argument("--step", required=True, help="skill that found the problem, e.g. p4-1-sttm-author")
    r.add_argument("--comment", required=True)
    r.add_argument("--blocks", help="your own checkpoint that cannot pass until this is resolved")
    r.add_argument("--data-table")
    r.add_argument("--data-filter")
    r.add_argument("--target-artifact")
    r.add_argument("--target-location")
    r.add_argument("--related", help="FB id of an earlier item for the same problem")
    ac = sub.add_parser("accept", help="person accepts a proposed item -> open")
    ac.add_argument("fid")
    ac.add_argument("--source", required=True)
    ac.add_argument("--by")
    ls = sub.add_parser("list")
    ls.add_argument("source_id", nargs="?")
    ls.add_argument("--open", action="store_true")
    for name in ("plan", "reset"):
        x = sub.add_parser(name)
        x.add_argument("fid")
        x.add_argument("--source", required=True)
    st = sub.add_parser("set")
    st.add_argument("fid")
    st.add_argument("status", choices=STATUSES)
    st.add_argument("--source", required=True)
    st.add_argument("--summary")
    st.add_argument("--changed", nargs="*")
    st.add_argument("--by")
    lg = sub.add_parser("log")
    lg.add_argument("source_id")
    lg.add_argument("step")
    lg.add_argument("--feedback", nargs="*")
    lg.add_argument("--note", default="")
    lg.add_argument("--outputs", nargs="*")
    a = ap.parse_args(argv)

    if a.cmd == "new":
        fid = next_id(source_id=a.source_id)
        d = {"id": fid, "source_id": a.source_id, "checkpoint": a.checkpoint, "raised_by": a.by, "raised_on": _now(),
             "target": {"artifact": a.target_artifact, "location": a.target_location} if a.target_artifact else None,
             "comment": a.comment, "include_paths": a.include, "ignore_paths": a.ignore, "code": a.code,
             "data": [{"table": a.data_table, "filter": a.data_filter}] if a.data_table else None,
             "attachments": a.attach, "answer": None, "rerun_from": a.rerun_from, "status": "open",
             "response": None, "verified_by": None}
        errs = validate_item({**d, "_path": fid})
        if errs:
            print("\n".join(errs))
            return 1
        os.makedirs(fb_dir(a.source_id, a.checkpoint), exist_ok=True)
        p = os.path.join(fb_dir(a.source_id, a.checkpoint), f"{fid}.yaml")
        with open(p, "w", encoding="utf-8") as f:
            yaml.safe_dump(d, f, sort_keys=False, allow_unicode=True)
        print(f"created {os.path.relpath(p, ROOT)}")
        return 0
    if a.cmd == "raise":
        if a.step not in [s for s, _, _ in STEPS] + ["x-feedback-rerun"]:
            print(f"unknown step {a.step}")
            return 1
        fid = next_id(source_id=a.source_id)
        d = {"id": fid, "source_id": a.source_id, "checkpoint": a.checkpoint, "raised_by": f"agent:{a.step}", "raised_on": _now(),
             "origin": "upstream_issue", "blocks": a.blocks, "related": a.related,
             "target": {"artifact": a.target_artifact, "location": a.target_location} if a.target_artifact else None,
             "comment": a.comment, "include_paths": None, "ignore_paths": None, "code": None,
             "data": [{"table": a.data_table, "filter": a.data_filter}] if a.data_table else None,
             "attachments": None, "answer": None, "rerun_from": None, "status": "proposed", "response": None, "verified_by": None}
        errs = validate_item({**d, "_path": fid})
        if errs:
            print("\n".join(errs))
            return 1
        os.makedirs(fb_dir(a.source_id, a.checkpoint), exist_ok=True)
        p = os.path.join(fb_dir(a.source_id, a.checkpoint), f"{fid}.yaml")
        with open(p, "w", encoding="utf-8") as f:
            yaml.safe_dump(d, f, sort_keys=False, allow_unicode=True)
        n = repeats(d, all_feedback())
        print(f"raised {os.path.relpath(p, ROOT)} (proposed; a person must accept or reject)"
              + (f"\nWARNING: this problem is raised for the {n}. time - stop and ask a person" if n > MAX_REPEATS else ""))
        return 0
    if a.cmd == "accept":
        d = _find(a.fid, a.source)
        path = os.path.join(ROOT, d.pop("_path"))
        if d.get("status") != "proposed":
            print(f"{a.fid} is '{d.get('status')}', not 'proposed'")
            return 1
        d["status"] = "open"
        d["accepted_by"] = a.by or os.environ.get("USER")
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(d, f, sort_keys=False, allow_unicode=True)
        print(f"{a.fid} -> open. Next: python tools/x_feedback.py plan {a.fid} --source {a.source}")
        return 0
    if a.cmd == "list":
        items = all_feedback(source_id=a.source_id)
        if a.open:
            items = [d for d in items if d.get("status") in UNRESOLVED]
        for d in items:
            print(f"{d['id']}  {d['source_id']:22} {d['checkpoint']:20} {d['status']:11} {(d.get('comment') or '')[:60]}")
        bad = sum((validate_item(d) for d in items), [])
        for e in bad:
            print("ERROR", e)
        return 1 if bad else 0
    if a.cmd in ("plan", "reset"):
        d = _find(a.fid, a.source)
        pl = plan(d)
        print(json.dumps(pl, indent=2))
        if a.cmd == "reset":
            ch = reset(a.source, [c for c in pl["reset_checkpoints"] if c.startswith("CP")])
            print(f"reset to pending: {ch or 'none (were not approved)'}")
        return 0
    if a.cmd == "set":
        d = _find(a.fid, a.source)
        path = os.path.join(ROOT, d.pop("_path"))
        d["status"] = a.status
        if a.summary or a.changed:
            d["response"] = {"summary": a.summary, "changed": a.changed, "on": _now()}
        if a.status == "verified":
            d["verified_by"] = a.by or os.environ.get("USER")
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(d, f, sort_keys=False, allow_unicode=True)
        print(f"{a.fid} -> {a.status}")
        return 0
    if a.cmd == "log":
        print(json.dumps(log_run(a.source_id, a.step, a.feedback, a.note, a.outputs)))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
