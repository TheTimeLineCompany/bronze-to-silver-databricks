#!/usr/bin/env python3
"""Navigator behind 00_start_here: where is a source, what is the next step, and run the code steps.

    python tools/x_navigator.py S07_container_moves            # status + next step (text)
    python tools/x_navigator.py S07_container_moves --run next # run the next CODE step (no Spark steps from the CLI)

Each phase is a short list of steps. A step is done when its output exists (checked from files, never from memory).
Who does a step:
    code   -> the navigator can run it (button in 00_start_here)
    agent  -> type the shown text in Genie Code
    human  -> a person reviews or approves (PR)
"""
from __future__ import annotations

import csv
import glob
import json
import os
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def _y(p):
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _passed(p):
    return os.path.exists(p) and any(ln.strip().lower() == "result: pass" for ln in open(p, encoding="utf-8"))


def sources(root=ROOT):
    return [s["id"] for s in (_y(os.path.join(root, "registry", "sources.yaml")) or {}).get("sources", [])]


# ----------------------------------------------------------------------------- the step catalogue
def steps(sid, root=ROOT):
    """All steps of the source's CURRENT checkpoint, each with done True/False."""
    import x_checkpoint_pack as pk
    import x_feedback as fb
    s = os.path.join(root, "sources", sid)
    sttm = os.path.join(s, "04_mapping", "sttm.yaml")
    doc = _y(sttm) or {}
    reg = _y(os.path.join(root, "registry", "sources.yaml")) or {}
    src = next((x for x in reg.get("sources", []) if x["id"] == sid), {})
    cps = src.get("checkpoints", {})
    gl = reg.get("global_checkpoints", {})
    ok = {"approved", "not_required"}
    order = ["CP1_source_brief", "CP2_evidence", "CP3_central_model", "CP4_sttm", "CP4b_business_logic", "CP5_code_qa", "CP6_handoff"]
    status = {c: (gl.get(c) or {}).get("status", "pending") if c.startswith("CP3") else (cps.get(c) or {}).get("status", "pending") for c in order}
    status["CP3_central_model"] = "approved" if all((gl.get(c) or {}).get("status") == "approved" for c in fb.GLOBAL_CPS) else \
        (gl.get("CP3_central_model") or {}).get("status", "pending")
    current = next((c for c in order if status[c] not in ok), None)

    def fresh(cp):
        return pk.stale(sid, cp, root) is None

    def ex(*p):
        return os.path.exists(os.path.join(s, *p))

    def triage_confirmed():
        t = _y(os.path.join(s, "01_intake", "triage.yaml")) or {}
        return bool(t.get("files")) and all(f.get("status") == "confirmed" for f in t["files"])

    def cards_done():
        d = os.path.join(s, "02_evidence", "discovery", "cards")
        cards = {os.path.basename(c)[:-3] for c in glob.glob(os.path.join(d, "[TRD]-*.md"))}
        done = {os.path.basename(c).split(".")[0] for c in glob.glob(os.path.join(d, "*.result.yaml"))}
        return ex("02_evidence", "discovery", "tables.csv") and not (cards - done)

    def merged():
        p = os.path.join(s, "02_evidence", "discovery", "tasks.jsonl")
        return os.path.exists(p) and any('"task": "merge"' in ln for ln in open(p, encoding="utf-8"))

    def discovery_evidence():
        p = os.path.join(s, "02_evidence", "evidence_register.csv")
        return os.path.exists(p) and any(r.get("location", "").startswith("02_evidence/discovery/") for r in csv.DictReader(open(p, encoding="utf-8")))

    def sttm_valid():
        if not os.path.exists(sttm):
            return False
        import p4_2_validate_sttm as vs
        return vs.validate(sttm, vs.load_context(root), root).ok

    def notebooks():
        return bool(glob.glob(os.path.join(s, "05_build", "nb_*.py")))

    def notebooks_finished():
        nbs = glob.glob(os.path.join(s, "05_build", "nb_*.py"))
        return bool(nbs) and not any(("df = df  # replace" in open(n).read() or "# REVIEW(" in open(n).read()) for n in nbs)

    def logged(step):
        p = os.path.join(s, "run_log.jsonl")
        return os.path.exists(p) and any(f'"step": "{step}"' in ln for ln in open(p, encoding="utf-8"))

    def global_requests_open():
        return any(d.get("status") in fb.UNRESOLVED for d in fb.all_feedback(root, "global"))

    masters = [t for t in doc.get("tables", []) if t.get("target_kind") == "master"]
    has_bl = any(c.get("business_logic") for t in doc.get("tables", []) for c in t.get("columns", []))
    a = lambda skill: f"@{skill} for {sid}"
    P = {
        "CP1_source_brief": [
            ("List the files in 00_inbox", "code", lambda: ex("01_intake", "manifest.md"), "inventory"),
            ("Classify files and write read plans", "agent", triage_confirmed, a("p1-2-triage")),
            ("Write the source brief and first evidence", "agent", lambda: ex("01_intake", "source_brief.md"), a("p1-3-source-brief")),
            ("Make the CP1 checkpoint pack", "code", lambda: fresh("CP1_source_brief"), "pack"),
            ("Review 01_intake/checkpoint/CP1_source_brief.html and approve CP1 in a PR", "human", lambda: status["CP1_source_brief"] in ok, None)],
        "CP2_evidence": [
            ("Extract the client's profiling workbooks", "code", lambda: ex("02_evidence", "profiling", "doc_profiles.csv"), "doc-profiles"),
            ("Discover the bronze tables (Spark)", "code", lambda: ex("02_evidence", "discovery", "tables.csv"), "discover"),
            ("Answer the discovery cards (one new chat per card)", "agent", cards_done, f"@p2-2-bronze-discovery card sources/{sid}/02_evidence/discovery/cards/T-xxx.md"),
            ("Merge the card answers", "code", merged, "discover-merge"),
            ("Add bronze facts to the evidence register", "code", discovery_evidence, "discover-evidence"),
            ("Reconcile the evidence", "agent", lambda: logged("p2-3-evidence-reconcile") or fresh("CP2_evidence"), a("p2-3-evidence-reconcile")),
            ("Make the CP2 checkpoint pack", "code", lambda: fresh("CP2_evidence"), "pack"),
            ("Review 02_evidence/checkpoint/CP2_evidence.html and approve CP2 in a PR", "human", lambda: status["CP2_evidence"] in ok, None)],
        "CP3_central_model": [
            ("Handle central-model requests (new objects, relationships, key rules, survivorship)", "agent",
             lambda: not global_requests_open(), "@p3-1-entity-model"),
            ("Make the CP3 checkpoint packs", "code", lambda: pk.stale("global", "CP3_central_model", root) is None, "pack-global"),
            ("Data architect reviews registry/checkpoint/*.html and approves CP3 and CP3b in a PR", "human",
             lambda: status["CP3_central_model"] in ok, None)],
        "CP4_sttm": [
            ("Write the mapping (STTM)", "agent", lambda: os.path.exists(sttm), a("p4-1-sttm-author")),
            ("Validate the STTM", "code", sttm_valid, "validate"),
            ("Independent review in a NEW chat", "agent", lambda: _passed(os.path.join(s, "04_mapping", "reviews", "sttm_review.md")), a("p4-3-sttm-review")),
            ("Export Excel and ER diagram", "code", lambda: ex("04_mapping", "exports", "sttm.xlsx"), "export"),
            ("Make the CP4 checkpoint pack", "code", lambda: fresh("CP4_sttm"), "pack"),
            ("Review 04_mapping/checkpoint/CP4_sttm.html and approve CP4 in a PR", "human", lambda: status["CP4_sttm"] in ok, None)],
        "CP4b_business_logic": [
            ("Make the CP4b checkpoint pack", "code", lambda: fresh("CP4b_business_logic"), "pack"),
            ("Business expert signs off 04_mapping/reviews/business_logic_signoff.md" if has_bl else
             "No business logic: set CP4b to not_required in a PR", "human", lambda: status["CP4b_business_logic"] in ok, None)],
        "CP5_code_qa": [
            ("Generate the notebooks (safe to re-run)", "code", notebooks, "generate"),
            *([("Generate the master build(s)", "code", lambda: all(os.path.exists(os.path.join(root, "masters", t["target_table"])) for t in masters),
                "generate-masters")] if masters else []),
            ("Finish the TODO cells and the job", "agent", notebooks_finished, a("p5-1-pyspark-codegen")),
            ("Run the notebooks in dev and check QA", "agent", lambda: ex("05_build", "qa_results", "summary.json"), a("p5-2-qa-runner")),
            ("Code review in a NEW chat", "agent", lambda: _passed(os.path.join(s, "05_build", "reviews", "code_review.md")), a("p5-3-code-review")),
            ("Make the CP5 checkpoint pack", "code", lambda: fresh("CP5_code_qa"), "pack"),
            ("Review 05_build/checkpoint/CP5_code_qa.html and approve CP5 in a PR", "human", lambda: status["CP5_code_qa"] in ok, None)],
        "CP6_handoff": [
            ("Write the readiness report", "agent", lambda: ex("06_handoff", "readiness.md"), a("p6-1-handoff-package")),
            ("Make the CP6 checkpoint pack", "code", lambda: fresh("CP6_handoff"), "pack"),
            ("Deployment lead reviews 06_handoff/checkpoint/CP6_handoff.html and approves CP6 in a PR", "human",
             lambda: status["CP6_handoff"] in ok, None)],
    }
    import x_clarify as qz
    lst = []
    for mode, ref in (qz.needs(sid, current, root) if current else []):
        old = qz.open_item(sid, mode, ref, root)
        label = (f"Clarify with you before {current.split('_')[0]} (kickoff questions)" if mode == "kickoff"
                 else f"Think through your input {ref} with you (questions)")
        how = f"@x-clarify {'kickoff' if mode == 'kickoff' else 'input ' + ref} for {sid}"
        lst.append({"step": label + (f" - {old['id']} is waiting for answers" if old else ""), "who": "agent", "done": False, "how": how})
    # feedback on a LATER checkpoint waits until that checkpoint is current (it is listed under "Needs attention")
    pos = {c: i for i, c in enumerate(order)} | {c: order.index("CP3_central_model") for c in fb.GLOBAL_CPS}
    now = pos.get(current, len(order))
    open_fb = [d for d in fb.all_feedback(root, sid) if d.get("status") in ("open", "in_progress") and pos.get(d.get("checkpoint"), 0) <= now]
    for d in open_fb:
        lst.append({"step": f"Apply feedback {d['id']} ({d['checkpoint']}): {' '.join(str(d.get('comment') or '').split())[:80]}",
                    "who": "agent", "done": False, "how": f"@x-feedback-rerun apply {d['id']} for {sid}"})
    for d in [d for d in fb.all_feedback(root, sid) if d.get("status") == "applied"]:
        lst.append({"step": f"Check the change for {d['id']} and verify it (or reject / give new feedback)", "who": "human", "done": False,
                    "how": f"python tools/x_feedback.py set {d['id']} verified --source {sid} --by <you>"})
    for label, who, done, how in P.get(current, []):
        try:
            d = bool(done())
        except Exception:  # noqa: BLE001  a check that cannot run counts as not done
            d = False
        lst.append({"step": label, "who": who, "done": d, "how": how})
    return {"source": sid, "checkpoint": current, "status": status, "steps": lst}


def next_step(info):
    return next((x for x in info["steps"] if not x["done"]), None)


def attention(sid, root=ROOT):
    """Things a person must look at now: open feedback, proposed upstream issues, blocking questions."""
    import x_feedback as fb
    items = [d for d in fb.all_feedback(root, sid) + fb.all_feedback(root, "global") if d.get("status") in fb.UNRESOLVED]
    out = [f"{d['id']} ({d['status']}) at {d['checkpoint']}: {' '.join(str(d.get('comment') or '').split())[:120]}" for d in items]
    qs = (_y(os.path.join(root, "registry", "open_questions.yaml")) or {}).get("questions", []) or []
    out += [f"{q['id']} blocking question: {' '.join(str(q.get('question')).split())[:120]}" for q in qs
            if q.get("source_id") == sid and q.get("blocking") and q.get("status") == "open"]
    return out


# ----------------------------------------------------------------------------- running code steps
ACTIONS = {
    "inventory":         ("List the files in 00_inbox", ["p1_1_inventory.py", "{sid}"]),
    "check":             ("Check triage, brief, and evidence", ["p1_2_check_context.py", "{sid}"]),
    "doc-profiles":      ("Extract client profiling workbooks", ["p2_1_extract_doc_profiles.py", "{sid}"]),
    "discover":          ("Discover bronze tables (Spark)", None),
    "discover-merge":    ("Merge discovery card answers", ["p2_2_discover.py", "merge", "{sid}"]),
    "discover-evidence": ("Add discovery facts to the evidence register", ["p2_2_discover.py", "evidence", "{sid}"]),
    "validate":          ("Validate the STTM", ["p4_2_validate_sttm.py", "sources/{sid}/04_mapping/sttm.yaml"]),
    "export":            ("Export STTM to Excel and ER", ["p4_4_export_sttm.py", "sources/{sid}/04_mapping/sttm.yaml"]),
    "generate":          ("Generate notebooks (safe to re-run)", ["p5_1_gen_notebook.py", "sources/{sid}/04_mapping/sttm.yaml"]),
    "generate-masters":  ("Generate master builds", None),
    "pack":              ("Make the checkpoint pack for the current checkpoint", None),
    "pack-global":       ("Make the CP3 / CP3b packs", ["x_checkpoint_pack.py", "global", "--all"]),
    "gate":              ("Check all checkpoints", ["x_validate_gate.py", "{sid}", "--next"]),
    "board":             ("Feedback board", ["x_checkpoint_pack.py", "board"]),
    "clarify":           ("Make the clarify questions for the next kickoff or input", None),
    "clarify-skip":      ("Skip the next clarify step (recorded)", None),
}


# ----------------------------------------------------------------------------- user input: instructions and feedback
def instructions(sid, root=ROOT, step=None, active_only=True):
    """Standing instructions typed by a person (sources/<id>/instructions.yaml). step=None -> all."""
    doc = _y(os.path.join(root, "sources", sid, "instructions.yaml")) or {}
    out = [i for i in doc.get("instructions") or [] if not active_only or i.get("status") == "active"]
    return [i for i in out if step is None or (i.get("route_steps") and step in i["route_steps"])
            or (not i.get("route_steps") and i.get("step") in ("all", step))]


def add_instruction(sid, text, step="all", by=None, root=ROOT):
    """Save a typed instruction for a whole source or one step. Skills read active instructions before they start."""
    import x_feedback as fb
    text = " ".join(str(text or "").split())
    if len(text) < 5:
        return "Type the instruction in the message box first."
    steps_ok = ["all"] + [s_ for s_, _, _ in fb.STEPS]
    if step not in steps_ok:
        return f"Unknown step '{step}'. Use one of: {', '.join(steps_ok)}"
    p = os.path.join(root, "sources", sid, "instructions.yaml")
    doc = _y(p) or {"source_id": sid, "instructions": []}
    lst = doc.setdefault("instructions", []) or []
    n = max([int(str(i["id"]).split("-")[1]) for i in lst] or [0]) + 1
    from datetime import datetime, timezone
    lst.append({"id": f"IN-{n:03d}", "step": step, "text": text, "by": by or os.environ.get("USER", "user"),
                "on": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "status": "active"})
    doc["instructions"] = lst
    with open(p, "w", encoding="utf-8") as f:
        f.write("# Standing instructions from people. Every skill reads the active ones for its step (or 'all') before it starts.\n"
                "# Retire one by setting status: retired (do not delete: it is the history of decisions).\n")
        yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True)
    return f"Saved IN-{n:03d} for {sid} ({'all steps' if step == 'all' else step}). Genie reads it at the start of the step."


def give_feedback(sid, text, checkpoint="current", by=None, root=ROOT):
    """Typed review feedback -> a normal feedback item (open) on the chosen checkpoint (default: the current one)."""
    import x_feedback as fb
    text = " ".join(str(text or "").split())
    if len(text) < 5:
        return "Type the feedback in the message box first."
    cp = steps(sid, root)["checkpoint"] if checkpoint in (None, "", "current") else checkpoint
    if not cp:
        cp = "CP6_handoff"
    if cp not in fb.SOURCE_CP_ORDER + fb.GLOBAL_CPS:
        return f"Unknown checkpoint '{cp}'."
    src = "global" if cp in fb.GLOBAL_CPS else sid
    fid = fb.next_id(root, src)
    from datetime import datetime, timezone
    d = {"id": fid, "source_id": src, "checkpoint": cp, "raised_by": by or os.environ.get("USER", "reviewer"),
         "raised_on": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "target": None, "comment": text,
         "include_paths": None, "ignore_paths": None, "code": None, "data": None, "attachments": None, "answer": None,
         "rerun_from": None, "status": "open", "response": None, "verified_by": None}
    os.makedirs(fb.fb_dir(src, cp, root), exist_ok=True)
    with open(os.path.join(fb.fb_dir(src, cp, root), f"{fid}.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(d, f, sort_keys=False, allow_unicode=True)
    return (f"Saved {fid} on {cp}. Next: in Genie Code type  @x-feedback-rerun apply {fid} for {sid}\n"
            "(Genie plans the rerun, redoes the affected steps, and marks it applied; you then verify it.)")


def _apply_decision_sheet(sid, path, label, root=ROOT):
    """Filled sheet with columns (table, column, scope) or (table, scope) -> discovery decisions. Returns a note or None."""
    rows = []
    if path.lower().endswith(".csv"):
        rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    elif path.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            it = ws.iter_rows(values_only=True)
            head = [str(h or "").strip().lower() for h in next(it, [])]
            if "table" in head and "scope" in head:
                rows += [{head[i]: (v if v is not None else "") for i, v in enumerate(r) if i < len(head)} for r in it]
    rows = [{k.lower(): str(v).strip() for k, v in r.items()} for r in rows if r]
    if not rows or not {"table", "scope"} <= set(rows[0]):
        return None
    ok_scope = {"in_scope", "out_of_scope", "derive_instead", "in_scope_masked", "technical", "review"}
    bad = [r for r in rows if r.get("scope") and r["scope"] not in ok_scope]
    if bad:
        return f"{os.path.basename(path)}: unknown scope values {sorted({r['scope'] for r in bad})}; nothing applied"
    d = os.path.join(root, "sources", sid, "02_evidence", "discovery")
    n = 0
    if "column" in rows[0]:
        p = os.path.join(d, "column_scope.csv")
        if not os.path.exists(p):
            return f"{os.path.basename(path)}: column decisions found, but discovery has not run yet"
        cur = list(csv.DictReader(open(p, encoding="utf-8")))
        dec = {(r["table"].split(".")[-1].lower(), r["column"].lower()): r["scope"] for r in rows if r.get("scope") and r.get("column")}
        for r in cur:
            k = (r["table"].split(".")[-1].lower(), r["column"].lower())
            if k in dec and dec[k] != r["scope"]:
                r["scope"], r["decided_by"], r["reason"] = dec[k], label, f"{dec[k]} ({label})"
                n += 1
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["table", "column", "column_class", "scope", "reason", "decided_by"])
            w.writeheader()
            w.writerows(cur)
    else:
        p = os.path.join(d, "tables.csv")
        if not os.path.exists(p):
            return f"{os.path.basename(path)}: table decisions found, but discovery has not run yet"
        cur = list(csv.DictReader(open(p, encoding="utf-8")))
        dec = {r["table"].split(".")[-1].lower(): r["scope"] for r in rows if r.get("scope")}
        for r in cur:
            k = r["table"].split(".")[-1].lower()
            if k in dec and dec[k] != r.get("scope"):
                r["scope"], r["scope_reason"], r["decided_by"] = dec[k], f"{label}", label
                n += 1
        keys_ = list(dict.fromkeys(k for r in cur for k in r))
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys_)
            w.writeheader()
            w.writerows(cur)
    return f"{os.path.basename(path)}: {n} scope decision(s) applied to discovery ({label})"


def register_uploads(sid, purpose, message="", checkpoint="current", step="all", by=None, root=ROOT):
    """Turn new files in sources/<id>/uploads/ into instructions, feedback, or handover inputs (each file once, by hash)."""
    import hashlib
    import shutil
    import x_feedback as fb
    up = os.path.join(root, "sources", sid, "uploads")
    os.makedirs(up, exist_ok=True)
    reg_p = os.path.join(up, "registered.yaml")
    reg = _y(reg_p) or {"files": []}
    seen = {f["sha1"] for f in reg["files"]}
    new = []
    for f in sorted(os.listdir(up)):
        full = os.path.join(up, f)
        if f in ("registered.yaml", "README.md", ".gitkeep") or not os.path.isfile(full):
            continue
        h = hashlib.sha1(open(full, "rb").read()).hexdigest()
        if h not in seen:
            new.append((f, h))
    if not new:
        return "No new files in uploads/. Upload files there first (Databricks: folder menu > Import / Upload)."
    if purpose not in ("instruction", "feedback", "handover"):
        return "Choose purpose: instruction, feedback, or handover."
    rel = [f"uploads/{f}" for f, _ in new]
    notes = []
    from datetime import datetime, timezone
    if purpose == "instruction":
        notes.append(add_instruction(sid, (message or "See the attached file(s).") + " Files: " + ", ".join(rel), step, by, root))
    elif purpose == "feedback":
        out = give_feedback(sid, (message or "See the attached file(s).") + " Files: " + ", ".join(rel), checkpoint, by, root)
        fid = out.split()[1]
        item = fb._find(fid, "global" if (checkpoint in fb.GLOBAL_CPS) else sid, root)
        path = os.path.join(root, item.pop("_path"))
        item["attachments"] = [f"sources/{sid}/{r}" for r in rel]
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(item, fh, sort_keys=False, allow_unicode=True)
        notes.append(out)
    else:
        cp = steps(sid, root)["checkpoint"] if checkpoint in (None, "", "current") else checkpoint
        folder = fb.CP_FOLDER.get(cp, "01_intake")
        hd = os.path.join(root, "sources", sid, folder, "handover")
        os.makedirs(hd, exist_ok=True)
        for f, _ in new:
            shutil.copyfile(os.path.join(up, f), os.path.join(hd, f))
        notes.append(f"Copied {len(new)} file(s) to {folder}/handover/: the {cp} checkpoint pack lists them for the next stage.")
    for f, _ in new:
        n = _apply_decision_sheet(sid, os.path.join(up, f), f"upload {f}", root)
        if n:
            notes.append(n)
    reg["files"] += [{"file": f, "sha1": h, "purpose": purpose, "by": by or os.environ.get("USER", "user"),
                      "on": datetime.now(timezone.utc).strftime("%Y-%m-%d")} for f, h in new]
    with open(reg_p, "w", encoding="utf-8") as fh:
        yaml.safe_dump(reg, fh, sort_keys=False)
    return "\n".join(notes)


def understanding(sid, saved_text, root=ROOT):
    """After an input is saved: how it was understood against the 3-level ontology, and what happens next. Short."""
    import re as _re
    import x_clarify as qz
    out = []
    for ref in dict.fromkeys(_re.findall(r"\b(IN-\d{3}|FB-[A-Za-z0-9]+-[a-z0-9]{4}|FB-\d{4})\b", saved_text or "")):
        a = qz.analyse_ref(sid, ref, root)
        if a.get("error"):
            continue
        lv = a["levels"]
        r = a["route"]
        out.append(f"{ref} understood as: {', '.join(a['intents']) or 'not clear yet'}")
        for k in ("business", "data", "information"):
            out.append(f"  {k:<11} " + (", ".join(sorted({d['match'] for d in lv[k]}))[:150] or "-"))
        if a["unknown"]:
            out.append(f"  unknown     {', '.join(a['unknown'][:8])}")
        if a["new_concepts"]:
            out.append(f"  new         {', '.join(a['new_concepts'])} (CP3 change request)")
        for c in a["conflicts"]:
            out.append(f"  check       {c['fact'][:150]}")
        out.append(f"  route       first used by {r['earliest_step'] or '-'}"
                   + (f"; RERUN, back to pending: {', '.join(r['reset_checkpoints'])}" if r["rerun_needed"] else "")
                   + (f"; {'; '.join(r['change_requests'])}" if r["change_requests"] else ""))
        n = len(a["questions"])
        out.append(f"  next        {'Genie has ' + str(n) + ' question(s): type  @x-clarify input ' + ref + ' for ' + sid if n else 'no questions needed: type  @x-clarify input ' + ref + ' for ' + sid + '  to confirm the route'}")
    return "\n".join(out)


def add_source(sid, bronze_schema, name="", root=ROOT):
    """Create sources/<sid>/ from sources/_template and register it in registry/sources.yaml (all checkpoints pending)."""
    import re as _re
    import shutil
    if not _re.match(r"^S[0-9]{2}_[a-z0-9_]+$", sid or ""):
        return "Source id must look like S12_part_catalogue (S + two digits + _ + lower-case name)."
    if not bronze_schema:
        return "Give the bronze schema, for example bronze.part_catalogue."
    dst = os.path.join(root, "sources", sid)
    if os.path.exists(dst) or sid in sources(root):
        return f"{sid} already exists."
    shutil.copytree(os.path.join(root, "sources", "_template"), dst)
    for rd in glob.glob(os.path.join(dst, "**", "README.md"), recursive=True):
        t = open(rd, encoding="utf-8").read().replace("template - copy this folder for a new source", sid)
        open(rd, "w", encoding="utf-8").write(t)
    p = os.path.join(root, "registry", "sources.yaml")
    reg = _y(p)
    pend = {"status": "pending", "approved_by": None, "date": None, "pr": None}
    reg["sources"].append({"id": sid, "name": name or sid, "domains": [], "processes": [], "business_objects": [],
                           "bronze_schema": bronze_schema, "discovery": {"include": None, "exclude": None},
                           "phase1_owner": "tbd", "phase2_owner": "tbd", "wave": "tbd",
                           "checkpoints": {c: dict(pend) for c in ["CP1_source_brief", "CP2_evidence", "CP4_sttm",
                                                                    "CP4b_business_logic", "CP5_code_qa", "CP6_handoff"]}})
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(reg, f, sort_keys=False)
    return (f"Created sources/{sid}/ and added it to registry/sources.yaml.\n"
            f"Next: put the client's files in sources/{sid}/00_inbox/ (as they are), fill domains / processes / business_objects "
            f"in registry/sources.yaml, then choose {sid} and run the next step.")


def setup_check(root=ROOT):
    out = [_py(["x_ontology_check.py"], root).splitlines()[-1], _py(["x_validate_gate.py"], root).splitlines()[-1]]
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=root, capture_output=True, text=True)
    out.append(((r.stdout or r.stderr).strip().splitlines() or ["pytest did not run"])[-1])
    ok = "ONTOLOGY COHERENT" in out[0] and "CONSISTENT" in out[1] and "failed" not in out[2] and "error" not in out[2].lower()
    return ("SETUP OK\n" if ok else "SETUP HAS PROBLEMS\n") + "\n".join(out)


def _py(args, root):
    r = subprocess.run([sys.executable, os.path.join(root, "tools", args[0])] + args[1:], cwd=root, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip() or f"exit code {r.returncode}"


def run(action, sid, root=ROOT, spark=None):
    """Run one code step. Returns the text output. 'next' runs the next not-done code step."""
    if action == "next":
        nx = next_step(steps(sid, root))
        if not nx:
            return "Nothing to do: the current checkpoint is complete."
        if nx["who"] != "code":
            return f"The next step is for {'Genie Code' if nx['who'] == 'agent' else 'a person'}: {nx['step']}" + \
                   (f"\nType in Genie Code:  {nx['how']}" if nx["who"] == "agent" else "")
        action = nx["how"]
    if action == "setup-check":
        return setup_check(root)
    if action not in ACTIONS:
        return f"Unknown action '{action}'. Choose one of: {', '.join(ACTIONS)}"
    if action == "discover":
        if spark is None:
            return "Bronze discovery needs Spark: run it from 00_start_here in Databricks."
        import p2_2_discover as d
        d.plan(sid, root)
        d.run(spark, sid, "all", root=root)
        return open(os.path.join(root, "sources", sid, "02_evidence", "discovery", "summary.md"), encoding="utf-8").read()
    if action in ("clarify", "clarify-skip"):
        import x_clarify as qz
        info = steps(sid, root)
        nd = qz.needs(sid, info["checkpoint"], root) if info["checkpoint"] else []
        if not nd:
            return "Nothing to clarify."
        if action == "clarify-skip":
            return qz.skip(sid, reason="skipped from 00_start_here", root=root)
        mode, ref = nd[0]
        qid, path, n = qz.brief(sid, ref if mode == "input" else None, root)
        return (f"{qid}: {n} draft question(s). In Genie Code type:  @x-clarify {'kickoff' if mode == 'kickoff' else 'input ' + ref} for {sid}\n\n"
                + open(path, encoding="utf-8").read())
    if action == "generate-masters":
        doc = _y(os.path.join(root, "sources", sid, "04_mapping", "sttm.yaml")) or {}
        ents = [t["conformed_entity"] for t in doc.get("tables", []) if t.get("target_kind") == "master"]
        return "\n".join(_py(["p5_4_gen_master_build.py", e], root) for e in ents) or "This source feeds no shared master."
    if action == "pack":
        cp = steps(sid, root)["checkpoint"]
        if not cp:
            return "All checkpoints are approved."
        if cp.startswith("CP3"):
            return _py(["x_checkpoint_pack.py", "global", "--all"], root)
        return _py(["x_checkpoint_pack.py", sid, cp], root)
    return _py([a.format(sid=sid) for a in ACTIONS[action][1]], root)


# ----------------------------------------------------------------------------- display
ICON = {"code": "Run", "agent": "Genie", "human": "You"}


def html(sid, root=ROOT):
    """A small, plain page for displayHTML: progress, the next step, and what needs attention."""
    import html as h
    info = steps(sid, root)
    cps = info["status"]
    nx = next_step(info)
    att = attention(sid, root)
    cells = "".join(
        f"<td style='padding:6px 10px;border:1px solid #d5dde2;background:{'#e3f3f1' if v in ('approved', 'not_required') else ('#fbeedf' if k == info['checkpoint'] else '#fff')}'>"
        f"<b>{k.split('_')[0]}</b><br><span style='font-size:12px;color:#5b6a74'>{h.escape(v)}</span></td>" for k, v in cps.items())
    rows = "".join(
        f"<tr><td style='padding:4px 8px'>{'&#10003;' if x['done'] else ('&#9654;' if x is nx else '&middot;')}</td>"
        f"<td style='padding:4px 8px'>{h.escape(x['step'])}</td><td style='padding:4px 8px;color:#5b6a74'>{ICON[x['who']]}</td>"
        f"<td style='padding:4px 8px;font-family:monospace;font-size:12px'>{h.escape(str(x['how'] or ''))}</td></tr>" for x in info["steps"])
    if not nx:
        todo = "<p><b>This checkpoint is complete.</b></p>" if info["checkpoint"] else "<p><b>All checkpoints are approved.</b></p>"
    elif nx["who"] == "code":
        todo = f"<p><b>Next:</b> {h.escape(nx['step'])}.<br>Set <b>action</b> to <code>next</code> and run the last cell.</p>"
    elif nx["who"] == "agent":
        todo = f"<p><b>Next:</b> {h.escape(nx['step'])}.<br>Type this in Genie Code: <code>{h.escape(nx['how'])}</code></p>"
    else:
        todo = f"<p><b>Next (a person):</b> {h.escape(nx['step'])}.</p>"
    attn = ("<p><b>Needs attention</b></p><ul>" + "".join(f"<li>{h.escape(x)}</li>" for x in att) + "</ul>") if att else ""
    ins = instructions(sid, root)
    if ins:
        attn += ("<p><b>Your standing instructions</b> (Genie reads them before each step)</p><ul>"
                 + "".join(f"<li>{h.escape(i['id'])} [{h.escape(i['step'])}]: {h.escape(i['text'])}</li>" for i in ins) + "</ul>")
    return (f"<div style='font-family:system-ui,sans-serif;max-width:900px'>"
            f"<h2 style='margin:0 0 8px'>{h.escape(sid)}</h2>"
            f"<table style='border-collapse:collapse;margin-bottom:12px'><tr>{cells}</tr></table>"
            f"<div style='border:1px solid #d5dde2;padding:10px 14px;margin-bottom:10px'>{todo}</div>"
            f"<p style='margin:6px 0'><b>Steps of {h.escape(str(info['checkpoint']))}</b></p>"
            f"<table style='border-collapse:collapse'>{rows}</table>{attn}</div>")


def text(sid, root=ROOT):
    info = steps(sid, root)
    nx = next_step(info)
    L = [f"{sid}: current checkpoint {info['checkpoint'] or 'none (all approved)'}"]
    for x in info["steps"]:
        L.append(f"  {'[x]' if x['done'] else ('[>]' if x is nx else '[ ]')} {x['step']}  ({ICON[x['who']]}{': ' + str(x['how']) if x['how'] else ''})")
    for a in attention(sid, root):
        L.append(f"  ! {a}")
    for i in instructions(sid, root):
        L.append(f"  i {i['id']} [{i['step']}]: {i['text']}")
    return "\n".join(L)


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    if not a:
        print("Sources:", ", ".join(sources()))
        return 0
    sid = a[0]
    if "--run" in a:
        print(run(a[a.index("--run") + 1], sid))
    else:
        print(text(sid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
