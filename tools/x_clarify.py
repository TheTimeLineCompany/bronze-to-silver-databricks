#!/usr/bin/env python3
"""Clarify: quiz the person at the start of a checkpoint (kickoff) and on every new input (instruction, feedback, upload).

Code builds a FACTUAL brief (what is unclear, weak, missing, or in conflict) with draft questions. The agent (skill
x-clarify) refines them, asks the person in chat, and records the answers. Answers become:
    instruction  -> sources/<id>/instructions.yaml   (standing instruction for a step or all steps)
    evidence     -> 02_evidence/evidence_register.csv (origin team_knowledge, medium; client_answer if the client said it)
    feedback     -> a feedback item on a checkpoint (drives a rerun)
    question     -> registry/open_questions.yaml      ("I don't know": ask the client, never guess)
    none         -> recorded only

Files: sources/<id>/<phase folder>/clarify/QZ-<CPn>-<nnn>.md (questions) and .answers.yaml (answers), index.yaml (status).

    python tools/x_clarify.py brief  S07_container_moves                 # kickoff for the current checkpoint
    python tools/x_clarify.py brief  S07_container_moves --input FB-S07-k2q9   # on a new input
    python tools/x_clarify.py record S07_container_moves QZ-CP2-001       # after the answers file is filled
    python tools/x_clarify.py skip   S07_container_moves QZ-CP2-001 --reason "covered in workshop"
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import sys
from datetime import datetime, timezone

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
MAX_Q = 7


def _y(p):
    return yaml.safe_load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def _csv(p):
    return list(csv.DictReader(open(p, encoding="utf-8"))) if os.path.exists(p) else []


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cdir(sid, cp, root):
    import x_feedback as fb
    if cp in fb.GLOBAL_CPS:
        return os.path.join(root, "registry", "clarify")
    return os.path.join(root, "sources", sid, fb.CP_FOLDER.get(cp, "01_intake"), "clarify")


def _index(sid, root):
    p = os.path.join(root, "sources", sid, "clarify_index.yaml")
    return p, (_y(p) or {"items": []})


def status(sid, root=ROOT):
    return _index(sid, root)[1]["items"]


def needs(sid, cp, root=ROOT):
    """What still needs clarifying: kickoff for cp (if none done) + inputs (IN/FB items) not yet clarified."""
    import x_feedback as fb
    import x_navigator as nav
    items = status(sid, root)
    done = {(i["mode"], i.get("ref")) for i in items if i["status"] in ("answered", "skipped")}
    out = []
    if cp and ("kickoff", cp) not in done:
        out.append(("kickoff", cp))
    for i in nav.instructions(sid, root):  # answers recorded by clarify itself start with [QZ-...]: no loop
        if ("input", i["id"]) not in done and not str(i.get("text", "")).startswith("[QZ-"):
            out.append(("input", i["id"]))
    for d in fb.all_feedback(root, sid):
        if d.get("status") in ("open", "proposed") and ("input", d["id"]) not in done \
                and not str(d.get("raised_by", "")).startswith("agent:") and not str(d.get("comment", "")).startswith("[QZ-"):
            out.append(("input", d["id"]))
    return out


def open_item(sid, mode, ref, root=ROOT):
    """An already asked (not answered) questionnaire for the same thing, so a rerun does not make a second one."""
    return next((i for i in status(sid, root) if i["mode"] == mode and i.get("ref") == ref and i["status"] == "asked"), None)


# ----------------------------------------------------------------------------- facts -> draft questions
def _facts(sid, cp, root):
    """Compact facts the agent should think about for this checkpoint. Each fact may carry a draft question."""
    s = os.path.join(root, "sources", sid)
    F = []

    def add(topic, fact, q=None, affects=None, options=None, record_as="evidence"):
        F.append({"topic": topic, "fact": fact, "question": q, "affects": affects or cp, "options": options, "record_as": record_as})
    reg = _y(os.path.join(root, "registry", "sources.yaml")) or {}
    src = next((x for x in reg.get("sources", []) if x["id"] == sid), {})
    if not src.get("business_objects"):
        add("scope", "sources.yaml lists no business objects for this source.",
            "Which business things does this system own (for example buyers, suppliers, parts, shipments)?", "P2 scope, P4 mapping", record_as="instruction")
    for q in (_y(os.path.join(root, "registry", "open_questions.yaml")) or {}).get("questions", []) or []:
        if q.get("source_id") == sid and q.get("status") == "open":
            add("open question", f"{q['id']} ({'blocking' if q.get('blocking') else 'not blocking'}): {' '.join(str(q['question']).split())}",
                f"Do you know the answer to {q['id']}? If the client confirmed it, say so.", "evidence, STTM", record_as="evidence")
    asked_q = {q["id"] for q in (_y(os.path.join(root, "registry", "open_questions.yaml")) or {}).get("questions", []) or []
               if q.get("source_id") == sid and q.get("status") == "open"}
    for r in _csv(os.path.join(s, "02_evidence", "evidence_register.csv")):
        if set(re.findall(r"Q-\d{4}", r.get("notes") or "")) & asked_q:
            continue                                   # already covered by the open question above
        if r.get("confidence") in ("low", "unknown") and r.get("status") == "unverified" or r.get("status") == "contradicted":
            add("weak evidence", f"{r['evidence_id']} {r['confidence']}/{r['status']}: {r['claim']}",
                f"Is this right: '{r['claim']}'? What do you know about it?", "evidence", record_as="evidence")
    d = os.path.join(s, "02_evidence", "discovery")
    for r in _csv(os.path.join(d, "tables.csv")):
        if r.get("scope") == "review":
            add("table scope", f"{r['table']}: {r.get('scope_reason')} (role {r.get('role')})",
                f"Should {r['table'].split('.')[-1]} feed silver? What is it used for?", "P2 scope", ["in_scope", "out_of_scope", "derive_instead"], "instruction")
    for r in _csv(os.path.join(d, "column_scope.csv")):
        if r.get("scope") == "review" and r.get("decided_by") == "code":
            add("column scope", f"{r['table'].split('.')[-1]}.{r['column']}: {r['column_class']} ({r['reason'][:80]})",
                f"{r['table'].split('.')[-1]}.{r['column']}: keep, mask, or leave out of silver?", "P2 scope, P4 privacy", ["keep", "mask", "out_of_scope"], "instruction")
    tscope = {r["table"]: r for r in _csv(os.path.join(d, "tables.csv"))}
    for r in _csv(os.path.join(d, "tables.csv")):
        bo = str(r.get("business_object") or "")
        if bo.startswith("NEW:"):
            add("business ontology", f"{r['table'].split('.')[-1]} is proposed as a NEW business object {bo[4:]} (not in business.yaml).",
                f"What is one {bo[4:]} in business terms, who owns it, and which business objects does it relate to?", "CP3 change request",
                record_as="change_request")
    undoc = [r["item"].split(".")[-1] for r in _csv(os.path.join(d, "doc_gaps.csv")) if r["kind"] == "in_bronze_not_documented"
             and (tscope.get(r["item"]) or {}).get("scope") not in ("out_of_scope", None)]
    if undoc:                                          # one question for all of them, not one per table
        add("documents vs bronze", f"{len(undoc)} table(s) will feed silver, but no document describes them: {', '.join(undoc)}.",
            f"Is there a data dictionary or a person who knows {', '.join(undoc[:4])}{' ...' if len(undoc) > 4 else ''}? "
            "If you know what a table holds, tell me in one line each.", "evidence", record_as="evidence")
    for r in _csv(os.path.join(d, "doc_gaps.csv")):
        if r["kind"] == "documented_not_in_bronze":
            add("documents vs bronze", f"The documents name {r['item']}, but bronze has no such table.",
                f"Where is {r['item']}: another schema, renamed, or not delivered yet?", "P2 discovery", record_as="instruction")
    for r in _csv(os.path.join(d, "tables.csv")):
        if r.get("ontology_confidence") in ("low", "none") and r.get("scope") != "out_of_scope" and r.get("decided_by") == "code":
            add("business meaning", f"{r['table']} has no clear business object.",
                f"What does one row of {r['table'].split('.')[-1]} mean in business terms?", "ontology, P4", record_as="evidence")
    tri = _y(os.path.join(s, "01_intake", "triage.yaml")) or {}
    for f in tri.get("files") or []:
        if f.get("status") != "confirmed" and f.get("relevance") in ("core", "supporting"):
            add("documents", f"{f['file_id']} {f['path']} is suggested as {f.get('relevance')} ({f.get('doc_type')}).",
                f"Is {os.path.basename(f['path'])} the latest version, and is it needed?", "P1 triage", ["yes", "older version", "not needed"], "instruction")
    return F


def _resolve(sid, ref, root):
    """(text, kind, target, files) of an instruction or feedback item."""
    import x_feedback as fb
    import x_navigator as nav
    ins = {i["id"]: i for i in nav.instructions(sid, root, active_only=False)}
    if ref in ins:
        return ins[ref]["text"], "instruction", ins[ref].get("step"), []
    try:
        d = fb._find(ref, sid, root)
    except Exception:  # noqa: BLE001
        d = None
    if not d:
        return "", "", None, []
    parts = [str(d.get("comment") or "")]
    if d.get("code"):
        parts.append(str(d["code"]))
    if d.get("data"):
        parts.append(str(d["data"]))
    return " ".join(parts), "feedback", d.get("checkpoint"), list(d.get("attachments") or []) + list(d.get("include_paths") or [])


def analyse_ref(sid, ref, root=ROOT):
    import x_input_ontology as io
    text, kind, target, files = _resolve(sid, ref, root)
    if not text:
        return {"ref": ref, "error": "not found"}
    return io.analyse(sid, ref, text, files, kind, target, root)


def _input_facts(sid, ref, root):
    """Think through one new input against the business, data, and information ontology; questions only where needed."""
    a = analyse_ref(sid, ref, root)
    if a.get("error"):
        return [{"topic": "input", "fact": f"{ref} not found", "question": None, "affects": None, "options": None, "record_as": "none"}], a
    text, kind, target, _ = _resolve(sid, ref, root)
    F = [{"topic": "input", "fact": f"{kind} {ref} for {target}: {text}", "question": None, "affects": target, "options": None, "record_as": "none"}]

    def fact(topic, f):
        F.append({"topic": topic, "fact": f, "question": None, "affects": None, "options": None, "record_as": "none"})
    for lv in ("business", "data", "information"):
        if a["levels"][lv]:
            fact(f"{lv} ontology", "; ".join(f"{d['kind']} {d['match']} (said: {', '.join(d['said'])})" for d in a["levels"][lv][:8]))
        else:
            fact(f"{lv} ontology", "no match")
    for n in a["files"]:
        fact("file", n)
    fact("intent", ", ".join(a["intents"]) or "not clear")
    r = a["route"]
    fact("route", f"earliest step {r['earliest_step'] or '-'} (checkpoint {r['applies_from'] or '-'}); current {r['current_checkpoint']}; "
                  + (f"RERUN {r['rerun_now']}, reset {r['reset_checkpoints']}" if r["rerun_needed"] else "no rerun: it applies when the step runs")
                  + (f"; change requests: {'; '.join(r['change_requests'])}" if r["change_requests"] else ""))
    for c in a["conflicts"]:
        fact("conflict", f"with {c['with']}: {c['fact']}")
    if a["unknown"]:
        fact("unknown names", ", ".join(a["unknown"]))
    for q in a["questions"]:
        F.append({"topic": "why", "fact": q["why"], "question": q["q"], "affects": r["earliest_step"], "options": None, "record_as": q["record_as"]})
    return F, a


def brief(sid, input_ref=None, root=ROOT):
    """Write QZ-<cp>-nnn.md with facts and up to MAX_Q draft questions; returns the questionnaire id and path."""
    import x_navigator as nav
    cp = nav.steps(sid, root)["checkpoint"] or "CP6_handoff"
    mode = "input" if input_ref else "kickoff"
    old = open_item(sid, mode, input_ref or cp, root)
    if old and os.path.exists(os.path.join(root, old["file"])):
        txt = open(os.path.join(root, old["file"]), encoding="utf-8").read()
        return old["id"], os.path.join(root, old["file"]), txt.count("_(why:")
    analysis = None
    if input_ref:
        facts, analysis = _input_facts(sid, input_ref, root)
    else:
        facts = _facts(sid, cp, root)
    qs = [f for f in facts if f.get("question")][:MAX_Q]
    d = _cdir(sid, cp, root)
    os.makedirs(d, exist_ok=True)
    if analysis and not analysis.get("error"):
        import x_input_ontology as io
        io.to_yaml(analysis, os.path.join(d, f"IA-{input_ref}.yaml"))
    n = len(glob.glob(os.path.join(d, f"QZ-{cp.split('_')[0]}-*.md"))) + 1
    qid = f"QZ-{cp.split('_')[0]}-{n:03d}"
    L = [f"# {qid}: {'clarify ' + input_ref if input_ref else 'kickoff for ' + cp} ({sid})", "",
         "For the agent (@x-clarify): think the facts through, keep the questions that matter most (max 7), "
         "add any the facts miss, and ask them in chat. Say why each question is asked and what it changes. "
         "Ask nothing that the ontology, the evidence, or an earlier answer already settles."
         + (f" Full input analysis: `IA-{input_ref}.yaml`." if input_ref else ""), "",
         "## Facts", ""] + [f"- [{f['topic']}] {f['fact']}" for f in facts if f['topic'] != 'why'] + ["", "## Draft questions", ""]
    for i, f in enumerate(qs, 1):
        L.append(f"{i}. {f['question']}  _(why: {f['fact'] if f['topic'] == 'why' else f['topic']}; affects: {f['affects']}; record as: {f['record_as']}"
                 + (f"; options: {', '.join(f['options'])}" if f.get("options") else "") + ")_")
    if not qs:
        L.append("No open points found by code: the input matches the ontology, has a clear intent, and no conflict. "
                 "Tell the person in one or two lines how you understood it and where it goes (the route). "
                 "Ask only if your own reading finds a gap; else record with no answers (`record_as: none`).")
    L += ["", "## Answers", "", f"Write them to `{qid}.answers.yaml`, then run `python tools/x_clarify.py record {sid} {qid}`:", "",
          "```yaml", f"questionnaire: {qid}", "answers:",
          "  - q: 1",
          "    answer: <the person's words>",
          "    record_as: instruction | evidence | feedback | question | change_request | none",
          "    step: all             # for instructions: a step name, or all",
          "    about: <TABLE.COLUMN> # for evidence",
          "    confidence: medium    # evidence: medium (team knowledge) or high if the client confirmed it",
          "    client_confirmed: false",
          "    checkpoint: current   # for feedback", "```", ""]
    path = os.path.join(d, f"{qid}.md")
    open(path, "w", encoding="utf-8").write("\n".join(L))
    ip, idx = _index(sid, root)
    idx["items"].append({"id": qid, "mode": mode, "ref": input_ref or cp, "checkpoint": cp, "status": "asked", "on": _now(),
                         "file": os.path.relpath(path, root)})
    yaml.safe_dump(idx, open(ip, "w", encoding="utf-8"), sort_keys=False)
    return qid, path, len(qs)


def record(sid, qid, by=None, root=ROOT):
    """Turn the answers file into instructions, evidence, feedback, or client questions."""
    import x_navigator as nav
    ip, idx = _index(sid, root)
    item = next((i for i in idx["items"] if i["id"] == qid), None)
    if not item:
        return f"{qid} is not in clarify_index.yaml"
    ap = os.path.join(root, os.path.dirname(item["file"]), f"{qid}.answers.yaml")
    if not os.path.exists(ap):
        return f"No answers file {os.path.relpath(ap, root)} (write it; 'answers: []' when no question was needed)"
    ans = (_y(ap) or {}).get("answers") or []
    notes = []
    for a in ans:
        kind, text = a.get("record_as", "none"), " ".join(str(a.get("answer") or "").split())
        if not text:
            continue
        if kind == "instruction":
            notes.append(nav.add_instruction(sid, f"[{qid} q{a.get('q')}] {text}", a.get("step") or "all", by, root))
        elif kind == "feedback":
            notes.append(nav.give_feedback(sid, f"[{qid} q{a.get('q')}] {text}", a.get("checkpoint") or "current", by, root).splitlines()[0])
        elif kind == "question":
            import p2_2_discover as disc
            notes.append(f"client question {disc._add_question(sid, text, root)}")
        elif kind == "evidence":
            notes.append(_add_evidence(sid, text, a, qid, root))
        elif kind == "change_request":
            import x_feedback as fb
            fid = fb.raise_item("global", a.get("checkpoint") if a.get("checkpoint") in fb.GLOBAL_CPS else "CP3_central_model",
                                "x-clarify", f"[{qid} q{a.get('q')}] from {sid}: {text}", root=root)
            notes.append(f"change request {fid} (proposed, CP3): a person accepts or rejects it")
    if item["mode"] == "input":
        notes.append(_apply_route(sid, item, root))
    item["status"], item["answered_on"] = "answered", _now()
    yaml.safe_dump(idx, open(ip, "w", encoding="utf-8"), sort_keys=False)
    return "\n".join([f"{qid}: {len(ans)} answer(s) recorded"] + [n for n in notes if n])


def _apply_route(sid, item, root):
    """Update the path: the input now carries its route (steps that must use it) and its ontology references."""
    import x_feedback as fb
    ia = os.path.join(root, os.path.dirname(item["file"]), f"IA-{item['ref']}.yaml")
    a = _y(ia) or {}
    r = a.get("route") or {}
    if not r.get("earliest_step"):
        return f"{item['ref']}: no route (intent not clear)"
    order = [s_ for s_, _, _ in fb.STEPS]
    refs = sorted({d["match"] for lv in (a.get("levels") or {}).values() for d in lv})[:20]
    if item["ref"].startswith("IN-"):
        p = os.path.join(root, "sources", sid, "instructions.yaml")
        doc = _y(p) or {}
        for i in doc.get("instructions") or []:
            if i["id"] == item["ref"]:
                if i.get("step") == "all":
                    i["first_used_by"] = r["earliest_step"]           # 'all' stays all; the route says where it bites first
                else:
                    i["route_steps"] = sorted({i["step"], r["earliest_step"]}, key=order.index)
                i["ontology_refs"] = refs
                i["intents"] = a.get("intents") or []
        with open(p, "w", encoding="utf-8") as f:
            f.write("# Standing instructions from people. Every skill reads the active ones for its step (or 'all') before it starts.\n"
                    "# Retire one by setting status: retired (do not delete: it is the history of decisions).\n")
            yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True)
        return f"{item['ref']}: route set, first used by {r['earliest_step']}" + (f" (rerun of {r['applies_from']})" if r.get("rerun_needed") else "")
    try:
        d = fb._find(item["ref"], sid, root)
    except Exception:  # noqa: BLE001
        return f"{item['ref']}: not found"
    path = os.path.join(root, d.pop("_path"))
    default = fb.FIRST_STEP[d["checkpoint"]]
    if order.index(r["earliest_step"]) < order.index(default) and not d.get("rerun_from"):
        d["rerun_from"] = r["earliest_step"]
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(d, f, sort_keys=False, allow_unicode=True)
    return f"{item['ref']}: rerun from {d.get('rerun_from') or default}"


def _add_evidence(sid, text, a, qid, root):
    p = os.path.join(root, "sources", sid, "02_evidence", "evidence_register.csv")
    rows = _csv(p)
    cols = ["evidence_id", "claim", "about_type", "about", "origin", "file_id", "location", "doc_type", "confidence", "status", "corroborated_by", "notes"]
    n = max([int(r["evidence_id"][2:]) for r in rows] or [0]) + 1
    client = bool(a.get("client_confirmed"))
    claim = " ".join(text.split()[:40])
    rows.append({"evidence_id": f"E-{n:04d}", "claim": claim, "about_type": "other" if not a.get("about") else "column",
                 "about": a.get("about") or "", "origin": "client_answer" if client else "team_knowledge", "file_id": "",
                 "location": f"clarify/{qid}#q{a.get('q')}", "doc_type": "", "confidence": "high" if client else (a.get("confidence") or "medium"),
                 "status": "unverified", "corroborated_by": "", "notes": f"from {qid}"})
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return f"evidence E-{n:04d} ({'client_answer' if client else 'team_knowledge'})"


def skip(sid, qid=None, reason="", ref=None, root=ROOT):
    """Skip clarification (recorded). Without qid: skip the next needed clarification."""
    import x_navigator as nav
    ip, idx = _index(sid, root)
    if not qid:
        cp = nav.steps(sid, root)["checkpoint"]
        nd = needs(sid, cp, root)
        if not nd:
            return "Nothing to clarify."
        mode, ref = nd[0]
        idx["items"].append({"id": f"SKIP-{len(idx['items']) + 1:03d}", "mode": mode, "ref": ref, "checkpoint": cp, "status": "skipped",
                             "on": _now(), "reason": reason or "skipped by the person"})
    else:
        it = next((i for i in idx["items"] if i["id"] == qid), None)
        if not it:
            return f"{qid} not found"
        it["status"], it["reason"] = "skipped", reason or "skipped by the person"
    yaml.safe_dump(idx, open(ip, "w", encoding="utf-8"), sort_keys=False)
    return "Skipped (recorded in clarify_index.yaml)."


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["brief", "record", "skip", "needs"])
    ap.add_argument("source_id")
    ap.add_argument("qid", nargs="?")
    ap.add_argument("--input")
    ap.add_argument("--reason", default="")
    a = ap.parse_args(argv)
    if a.cmd == "brief":
        qid, path, n = brief(a.source_id, a.input)
        print(f"{qid}: {n} draft question(s) -> {os.path.relpath(path, ROOT)}")
        print(open(path, encoding="utf-8").read())
    elif a.cmd == "record":
        print(record(a.source_id, a.qid))
    elif a.cmd == "skip":
        print(skip(a.source_id, a.qid, a.reason))
    else:
        import x_navigator as nav
        print(needs(a.source_id, nav.steps(a.source_id)["checkpoint"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
