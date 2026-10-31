#!/usr/bin/env python3
"""Checkpoint pack: the assets a person reviews, and the next step consumes, at each checkpoint.

One command writes four files with the SAME content, from the files of the phase:
    <checkpoint>.json   machine-readable: next skill, agents, a Delta table, an API
    <checkpoint>.xlsx   machine- and human-readable: one sheet per list, filters on, README sheet first
    <checkpoint>.md     one-page text summary (for the PR description and Git history)
    <checkpoint>.html   one page, no tabs: status, key numbers, connections, what needs attention,
                        what the reviewer decides, one key table. Self-contained (no web fonts, no scripts).

Location:
    sources/<id>/<phase folder>/checkpoint/      CP1 01_intake, CP2 02_evidence, CP4/CP4b 04_mapping, CP5 05_build, CP6 06_handoff
    registry/checkpoint/                         CP3_central_model, CP3b_key_rules (global)

The .json keeps a SHA-1 of every input file. tools/x_validate_gate.py refuses an approved checkpoint
when its pack is missing or stale (an input changed after the pack was made).

Usage:
    python tools/x_checkpoint_pack.py S07_container_moves CP2_evidence
    python tools/x_checkpoint_pack.py global CP3_central_model
    python tools/x_checkpoint_pack.py S07_container_moves --all        # every source checkpoint
    python tools/x_checkpoint_pack.py board                            # all feedback + upstream issues -> registry/board/
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import html
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import x_feedback as fb  # noqa: E402

TITLES = {
    "CP1_source_brief": ("P1", "Source brief", "Check that the agent reads the right files, and that the brief describes the source correctly."),
    "CP2_evidence": ("P2", "Evidence", "Check that each fact the mapping needs has enough evidence, and that conflicts are handled."),
    "CP3_central_model": ("P3", "Central model", "Check the shared business objects, relationships, and master entities for all sources."),
    "CP3b_key_rules": ("P3", "Key rules", "Check the key formats and which source wins for shared attributes."),
    "CP4_sttm": ("P4", "Source-to-target mapping", "Check the mapping from bronze to silver, column by column, back to evidence."),
    "CP4b_business_logic": ("P4", "Business logic", "The business expert checks each calculated value and its formula."),
    "CP5_code_qa": ("P5", "Code and QA", "Check that the code implements the mapping and passes every QA check."),
    "CP6_handoff": ("P6", "Handoff", "Check that the deployment package is complete."),
}
NEXT = {
    "CP1_source_brief": "p2-1-doc-profiles, p2-2-bronze-discovery, p2-3-evidence-reconcile",
    "CP2_evidence": "p4-1-sttm-author (reads evidence and bronze results)",
    "CP3_central_model": "p4-1-sttm-author for every source",
    "CP3b_key_rules": "p4-1-sttm-author, lib/keys.py",
    "CP4_sttm": "Handover H1 (with CP4b) -> p5-1-pyspark-codegen",
    "CP4b_business_logic": "Handover H1 -> p5-1-pyspark-codegen",
    "CP5_code_qa": "p6-1-handoff-package",
    "CP6_handoff": "Handover H2 -> deployment team",
}
MAX_HTML_ROWS = 25


# ----------------------------------------------------------------------------- helpers
def _y(*p, root=None):
    path = os.path.join(root or ROOT, *p)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def pack_dir(source_id, cp, root=None):
    root = root or ROOT
    if cp in fb.GLOBAL_CPS:
        return os.path.join(root, "registry", "checkpoint")
    return os.path.join(root, "sources", source_id, fb.CP_FOLDER[cp], "checkpoint")


def _status(source_id, cp, root):
    reg = _y("registry", "sources.yaml", root=root) or {}
    if cp in fb.GLOBAL_CPS:
        return (reg.get("global_checkpoints", {}).get(cp) or {}).get("status", "pending")
    for s in reg.get("sources", []):
        if s["id"] == source_id:
            return (s.get("checkpoints", {}).get(cp) or {}).get("status", "pending")
    return "unknown"


def _questions(source_id, root):
    qs = (_y("registry", "open_questions.yaml", root=root) or {}).get("questions", []) or []
    rows = [q for q in qs if source_id == "global" or q.get("source_id") == source_id]
    return [{"id": q["id"], "blocking": bool(q.get("blocking")), "status": q.get("status"), "owner": q.get("owner"),
             "question": " ".join(str(q.get("question", "")).split()), "answer": " ".join(str(q.get("answer") or "").split())} for q in rows]


def _feedback(source_id, cp, root):
    return [{"id": d["id"], "status": d.get("status"), "raised_by": d.get("raised_by"),
             "kinds": ", ".join(k for k in fb.KINDS if d.get(k)),
             "comment": " ".join(str(d.get("comment") or "").split())[:200], "file": d["_path"]}
            for d in fb.all_feedback(root, source_id) if d.get("checkpoint") == cp]


def _table(rows, cols=None):
    cols = cols or (list(rows[0].keys()) if rows else [])
    return {"columns": cols, "rows": [[r.get(c) for c in cols] for r in rows]}


class Pack(dict):
    def __init__(self, source_id, cp, root):
        phase, title, purpose = TITLES[cp]
        info = _y("registry", "ontology", "information.yaml", root=root) or {}
        super().__init__(checkpoint=cp, source_id=source_id, phase=phase, title=title, purpose=purpose,
                         approver=(info.get("checkpoints", {}).get(cp) or {}).get("approver"),
                         status=_status(source_id, cp, root),
                         generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         next_step=NEXT[cp], inputs={}, metrics=[], connections={"kind": "none"},
                         issues=[], decide=[], key_table=None, tables={})
        self._root = root

    def inp(self, *relparts):
        rel = os.path.join(*relparts)
        full = os.path.join(self._root, rel)
        if os.path.isfile(full):
            self["inputs"][rel.replace(os.sep, "/")] = _sha1(full)
        return full

    def m(self, label, value, note=""):
        self["metrics"].append({"label": label, "value": value, "note": note})

    def issue(self, severity, item, text):
        self["issues"].append({"severity": severity, "item": item, "text": text})


# ----------------------------------------------------------------------------- collectors
def _cp1(p, sid, root):
    sdir = os.path.join("sources", sid)
    man = _csv(p.inp(sdir, "01_intake", "manifest.csv"))
    tri = _y(sdir, "01_intake", "triage.yaml", root=root) or {}
    p.inp(sdir, "01_intake", "triage.yaml")
    brief_p = p.inp(sdir, "01_intake", "source_brief.md")
    reg = _csv(p.inp(sdir, "02_evidence", "evidence_register.csv"))
    info = _y("registry", "ontology", "information.yaml", root=root) or {}
    bud = info.get("budgets", {})
    files = tri.get("files", []) or []
    rel = Counter(f.get("relevance") for f in files)
    dups = sum(1 for r in man if r.get("duplicate_of"))
    old = sum(1 for r in man if str(r.get("latest_in_group", "")).startswith("no"))   # inventory writes "no (latest: IF-xxxx)"
    words = len(open(brief_p, encoding="utf-8").read().split()) if os.path.exists(brief_p) else 0
    p.m("Files in inbox", len(man))
    p.m("Duplicates / old versions", f"{dups} / {old}")
    p.m("Core files", rel["core"], f"max {bud.get('max_core_files')}")
    p.m("Supporting / background / ignore", f"{rel['supporting']} / {rel['background']} / {rel['ignore']}")
    p.m("Brief words", words, f"max {bud.get('source_brief_max_words')}")
    p.m("Evidence claims", len(reg))
    p["connections"] = {"kind": "funnel", "steps": [
        ["00_inbox", f"{len(man)} files"], ["Inventory", f"{dups} duplicates, {old} old versions"],
        ["Triage", f"{rel['core']} core, {rel['supporting']} supporting"],
        ["Read plans", f"{sum(1 for f in files if f.get('read_plan'))} files with named parts"],
        ["Evidence", f"{len(reg)} claims"], ["Brief", f"{words} words"]]}
    import p1_2_check_context as cc
    e = cc.check(sid, root)
    for area in ("triage", "brief", "evidence"):
        for x in e[area]:
            p.issue("error", area, x)
    for f in files:
        if f.get("status") != "confirmed":
            p.issue("warn", f.get("file_id"), "triage line not confirmed")
    p["decide"] = ["Is each core file the latest and right version?",
                   "Do the ignored and background files hold nothing the mapping needs?",
                   "Does the brief name the right business objects, grain, and keys?"]
    rows = [{"file_id": f.get("file_id"), "path": f.get("path"), "doc_type": f.get("doc_type"), "relevance": f.get("relevance"),
             "reason": f.get("reason"), "read_plan": "; ".join(f"{k}: {v}" for k, v in (f.get("read_plan") or {}).items() if k != "why")}
            for f in files]
    order = {"core": 0, "supporting": 1, "background": 2, "ignore": 3}
    rows.sort(key=lambda r: (order.get(r["relevance"], 9), r["file_id"] or ""))
    p["tables"]["Files"] = _table(rows)
    p["tables"]["Evidence"] = _table(reg, ["evidence_id", "claim", "about", "origin", "file_id", "location", "confidence", "status"])
    p["key_table"] = "Files"


def _cp2(p, sid, root):
    sdir = os.path.join("sources", sid)
    reg = _csv(p.inp(sdir, "02_evidence", "evidence_register.csv"))
    dp = _csv(p.inp(sdir, "02_evidence", "profiling", "doc_profiles.csv"))
    checks = []
    for j in sorted(glob.glob(os.path.join(root, sdir, "02_evidence", "profiling", "*.json"))):
        p.inp(os.path.relpath(j, root))
        d = json.load(open(j, encoding="utf-8"))
        for c in d.get("checks", []):
            checks.append({"table": d.get("table"), "check": c.get("check"), "status": c.get("status"),
                           "evidence": str(c.get("evidence"))[:200], "file": os.path.basename(j)})
    conf = Counter(r["confidence"] for r in reg)
    st = Counter(r["status"] for r in reg)
    cst = Counter(c["status"] for c in checks)
    p.m("Evidence claims", len(reg))
    p.m("High / medium / low+unknown", f"{conf['high']} / {conf['medium']} / {conf['low'] + conf['unknown']}")
    p.m("Confirmed by bronze or corroborated", st["confirmed_by_bronze"] + st["corroborated"])
    p.m("Contradicted", st["contradicted"])
    p.m("Client profiling rows", len(dp), f"{Counter(r['confidence'] for r in dp)['low']} low")
    levels, stats = ["high", "medium", "low", "unknown"], ["unverified", "corroborated", "confirmed_by_bronze", "contradicted", "superseded"]
    matrix = {"kind": "matrix", "rows": levels, "cols": stats,
              "cells": [[sum(1 for r in reg if r["confidence"] == lv and r["status"] == s) for s in stats] for lv in levels],
              "caption": "Evidence claims by confidence (rows) and status (columns)"}
    # bronze discovery (P2.2)
    ddir = os.path.join(sdir, "02_evidence", "discovery")
    dt = _csv(p.inp(ddir, "tables.csv"))
    dl = [l for l in _csv(p.inp(ddir, "links.csv")) if l.get("status") in ("fk", "fk_partial")]
    cards = sorted(os.path.basename(c)[:-3] for c in glob.glob(os.path.join(root, ddir, "cards", "[TRD]-*.md")))
    answered = set()
    for c in glob.glob(os.path.join(root, ddir, "cards", "*.result.yaml")):
        p.inp(os.path.relpath(c, root))
        answered.add(os.path.basename(c).split(".")[0])
    role = {r["table"]: r["role"] for r in dt}
    if dt:
        p.m("Bronze tables", len(dt), f"{sum(1 for r in dt if r['role'] == 'staging')} staging")
        p.m("FK links found", len(dl), f"{sum(1 for l in dl if 'normalisation' in (l.get('note') or ''))} need a key rule")
        p.m("Agent cards answered", f"{len(answered & set(cards))} / {len(cards)}")
        for c in sorted(set(cards) - answered):
            p.issue("error", c, "discovery card not answered")
        for r in dt:
            if r["role"] != "staging" and r.get("ontology_confidence") in ("low", "none") and r.get("decided_by") == "code":
                p.issue("warn", r["table"].split(".")[-1], "no clear business object")
            if str(r.get("business_object", "")).startswith("NEW:"):
                p.issue("info", r["table"].split(".")[-1], f"proposes {r['business_object']}: needs a CP3 change request")
        for l in dl:
            if "normalisation" in (l.get("note") or ""):
                p.issue("info", f"{l['dep_table'].split('.')[-1]}.{l['dep_column']}", "values match only after normalisation: key rule needed (CP3b)")
        graph = {"kind": "flows", "caption": "Bronze lineage: column -> referenced table (role), containment",
                 "flows": [[f"{l['dep_table'].split('.')[-1]}.{l['dep_column']}", f"{l['cardinality']} ({max(float(l['containment_raw']), float(l['containment_norm'])):.0%})",
                            f"{l['ref_table'].split('.')[-1]} ({role.get(l['ref_table'], '?')})", l.get("status")] for l in dl]}
        roles_block = {"kind": "chain", "caption": "Tables in lineage order (level: table, role -> business object)",
                       "steps": [[f"{r['lineage_level']}: {r['table'].split('.')[-1]}", f"{r['role']} -> {r['business_object'] or '-'}"] for r in dt]}
        # scope, privacy, metadata, documents vs bronze, related tables (P2.2 wider discovery)
        cs = _csv(p.inp(ddir, "column_scope.csv"))
        gaps = _csv(p.inp(ddir, "doc_gaps.csv"))
        ov = _csv(p.inp(ddir, "overlap.csv"))
        rel = _csv(p.inp(ddir, "related.csv"))
        sc = Counter(r.get("scope") or "in_scope" for r in dt)
        p.m("Table scope in / out / derive / review", f"{sc['in_scope']} / {sc['out_of_scope']} / {sc['derive_instead']} / {sc['review']}")
        if cs:
            ccl = Counter(r.get("column_class") for r in cs)
            ccs = Counter(r.get("scope") for r in cs)
            p.m("Columns out of scope / in review", f"{ccs['out_of_scope']} / {ccs['review']}",
                f"{ccl['application_log']} app log, {ccl['audit_metadata']} audit, {ccl['secret_or_token']} secret")
            p.m("Personal-data columns", ccl["personal_data"], "need privacy handling in the STTM")
            for r in cs:
                if r.get("column_class") == "secret_or_token":
                    p.issue("warn", f"{r['table'].split('.')[-1]}.{r['column']}", "secret or token: never goes to silver")
                elif r.get("scope") == "review":
                    p.issue("info", f"{r['table'].split('.')[-1]}.{r['column']}", f"column scope in review: {r.get('column_class')} ({(r.get('reason') or '')[:80]})")
            p["tables"]["Column scope"] = _table(cs)
        for r in dt:
            if r.get("scope") == "review":
                p.issue("warn", r["table"].split(".")[-1], f"table scope in review: {r.get('scope_reason')}")
        av = _csv(p.inp(ddir, "metadata", "availability.csv"))
        if av:
            ok_ = [r["section"] for r in av if str(r.get("available")).lower() == "true"]
            miss = [r["section"] for r in av if r["section"] not in ok_]
            p.m("Unity Catalog metadata sections read", f"{len(ok_)} / {len(av)}", ("missing: " + ", ".join(miss))[:80] if miss else "all")
        if gaps:
            p.m("Documents vs bronze gaps", len(gaps))
            p["tables"]["Doc gaps"] = _table(gaps)
        if rel:
            p.m("Related tables outside the schema", len(rel))
            p["tables"]["Related tables"] = _table(rel)
        if ov:
            p["tables"]["Overlap with other sources"] = _table(ov)
            p.issue("info", "overlap", f"{len(ov)} table(s) look like tables of another source: see CP3")
        p["connections"] = [roles_block, graph, matrix]
        p["tables"]["Bronze tables"] = _table(dt, ["table", "rows", "key", "grain", "role", "role_confidence", "data_class", "lineage_level",
                                                   "derived_from", "business_object", "ontology_confidence", "scope", "scope_reason", "decided_by"])
        p["tables"]["Bronze links"] = _table(dl, ["dep_table", "dep_column", "ref_table", "ref_column", "status", "cardinality",
                                                  "containment_raw", "containment_norm", "coverage", "note"])
    else:
        p["connections"] = matrix
    import p1_2_check_context as cc
    for x in cc.check(sid, root, only="evidence")["evidence"]:
        p.issue("error", "evidence", x)
    if checks:
        p.m("Targeted bronze checks ok / warn / fail / error", f"{cst['ok']} / {cst['warn']} / {cst['fail']} / {cst['error']}")
    if not checks and not dt:
        p.issue("error", "bronze", "no bronze results: run tools/p2_2_discover.py")
    for c in checks:
        if c["status"] in ("fail", "error"):
            p.issue("error" if c["status"] == "error" else "warn", f"{c['table']} {c['check']}", c["evidence"])
    for r in reg:
        if r["status"] == "contradicted":
            p.issue("warn", r["evidence_id"], f"contradicted: {r['claim']}")
        if r["confidence"] in ("low", "unknown") and r["status"] == "unverified":
            q = re.findall(r"Q-\d{4}", r.get("notes") or "")
            p.issue("warn" if q else "error", r["evidence_id"], f"{r['confidence']} confidence, unverified" + (f"; question {q[0]}" if q else "; no question"))
    p["decide"] = ["Are the table roles, grain keys, and business objects right (see lineage order)?",
                   "Is the scope right: no logs, audit, or staging data in silver, and personal data handled?",
                   "Is the evidence enough for every key, foreign key, grain, and business rule?",
                   "Are contradictions resolved, with bronze for structure and documents for meaning?",
                   "Are the open questions the right ones, and is 'blocking' set correctly?"]
    p["tables"]["Evidence"] = _table(reg, ["evidence_id", "claim", "about_type", "about", "origin", "file_id", "location", "confidence", "status", "corroborated_by", "notes"])
    p["tables"]["Bronze checks"] = _table(checks, ["table", "check", "status", "evidence", "file"])
    p["tables"]["Client profiling"] = _table(dp, ["profile_id", "table", "column", "data_type", "null_pct", "distinct", "pk_candidate", "raw_confidence", "confidence", "description"])
    p["key_table"] = "Bronze tables" if dt else "Evidence"


def _cp3(p, sid, root, keys_only=False):
    bus = _y("registry", "ontology", "business.yaml", root=root)
    for f in (("registry", "ontology", "business.yaml"), ("registry", "ontology", "data.yaml"), ("registry", "entities.yaml"), ("registry", "key_normalisation.yaml")):
        p.inp(*f)
    ents = (_y("registry", "entities.yaml", root=root) or {}).get("entities", [])
    kn = (_y("registry", "key_normalisation.yaml", root=root) or {}).get("rules", {}) or {}
    import x_ontology_check as oc
    errs, warns = oc.check(root)
    for x in errs:
        p.issue("error", "ontology", x)
    for x in warns:
        p.issue("warn", "ontology", x)
    est = Counter(e.get("status") for e in ents)
    p.m("Business objects", len(bus["business_objects"]))
    p.m("Relationships", len(bus["relationships"]))
    p.m("Entities approved / proposed", f"{est['approved']} / {est['proposed']}")
    p.m("Key rules", len(kn))
    p.m("Business rules", len(bus.get("business_rules", {})))
    ent_rows = [{"name": e["name"], "business_object": e.get("business_object"), "data_class": e.get("data_class"), "target_table": e.get("target_table"),
                 "business_key": ", ".join(e.get("business_key", [])), "key_rule": e.get("key_rule"), "scd_type": e.get("scd_type"), "status": e.get("status")} for e in ents]
    key_rows = [{"rule": k, **{a: (json.dumps(v) if isinstance(v, (dict, list)) else v) for a, v in (r or {}).items()}} for k, r in kn.items()]
    kcols = ["rule"] + sorted({a for r in key_rows for a in r if a != "rule"})
    p["tables"]["Entities"] = _table(ent_rows)
    p["tables"]["Key rules"] = _table(key_rows, kcols)
    if keys_only:
        users = Counter(e.get("key_rule") for e in ents)
        p["connections"] = {"kind": "flows", "caption": "Key rule -> shared entity that uses it",
                            "flows": [[k, "normalises", ", ".join(e["name"] for e in ents if e.get("key_rule") == k) or "(no entity)"] for k in kn]}
        for k in kn:
            if not users.get(k):
                p.issue("info", k, "key rule not used by a shared entity (may be used by source keys)")
        p["decide"] = ["Does each rule produce the same key from every source format?",
                       "Is the pattern strict enough to catch bad keys?",
                       "Is survivorship (which source wins) agreed for shared attributes?"]
        p["key_table"] = "Key rules"
        return
    for e in ents:
        if e.get("status") != "approved":
            p.issue("info", e["name"], "entity not yet approved")
    p["connections"] = {"kind": "flows", "caption": "Business relationships (subject - verb - object, cardinality)",
                        "flows": [[r["subject"], f"{r['verb']} ({r['cardinality']})", r["object"], rid] for rid, r in bus["relationships"].items()]}
    obj_rows = [{"object": n, "kind": o.get("kind"), "domain": o.get("domain"), "definition": o.get("definition"), "synonyms": ", ".join(o.get("synonyms", []))}
                for n, o in bus["business_objects"].items()]
    p["tables"]["Business objects"] = _table(obj_rows)
    p["tables"]["Relationships"] = _table([{"id": k, **v} for k, v in bus["relationships"].items()], ["id", "subject", "verb", "object", "cardinality"])
    p["tables"]["Business rules"] = _table([{"id": k, **v} for k, v in bus.get("business_rules", {}).items()], ["id", "object", "desc", "status", "owner"])
    p["decide"] = ["Does each business object have one clear definition, and are the synonyms right?",
                   "Is every relationship true for the business, with the right cardinality?",
                   "Is each shared entity a master or reference, with the right business key and history?"]
    p["key_table"] = "Entities"


def _sttm(p, sid, root):
    sp = p.inp("sources", sid, "04_mapping", "sttm.yaml")
    p.inp("sources", sid, "02_evidence", "evidence_register.csv")
    if not os.path.exists(sp):
        p.issue("error", "sttm", "04_mapping/sttm.yaml missing")
        return None
    return _y("sources", sid, "04_mapping", "sttm.yaml", root=root)


def _cp4(p, sid, root):
    doc = _sttm(p, sid, root)
    if not doc:
        return
    bus = _y("registry", "ontology", "business.yaml", root=root)
    rels = bus["relationships"]
    import p4_2_validate_sttm as vs
    r = vs.validate(os.path.join(root, "sources", sid, "04_mapping", "sttm.yaml"), vs.load_context(root), root)
    for x in r.errors:
        p.issue("error", "validator", x)
    for x in r.warnings:
        if "blocking question" not in x:          # shown once, from the question register
            p.issue("warn", "validator", x)
    rev = p.inp("sources", sid, "04_mapping", "reviews", "sttm_review.md")
    rev_res = "missing"
    if os.path.exists(rev):
        rev_res = next((ln.split(":", 1)[1].strip() for ln in open(rev, encoding="utf-8") if ln.lower().startswith("result:")), "no result line")
    cols, fks, tabs = [], [], []
    flows = []
    for t in doc.get("tables", []):
        tabs.append({"target_table": t["target_table"], "business_object": t.get("business_object"), "data_class": t.get("data_class"),
                     "grain": t.get("grain"), "load_pattern": t.get("load_pattern"), "scd_type": t.get("scd_type"),
                     "business_key": ", ".join(t.get("business_key") or []), "sources": ", ".join(s["table"] for s in t.get("sources", []))})
        flows.append([t.get("business_object"), "is stored as", f"{t['target_table']} ({t.get('data_class')}, {t.get('load_pattern')})", ""])
        for c in t.get("columns", []):
            pv = c.get("provenance") or {}
            cols.append({"table": t["target_table"], "column": c["target"], "type": c.get("type"), "key_role": c.get("key_role"), "rule": c.get("rule"),
                         "source": c.get("source"), "transform": c.get("transform"), "evidence": ", ".join(pv.get("evidence") or []),
                         "confidence": c.get("confidence"), "business_rule": c.get("business_rule"), "question": c.get("open_question")})
            if c.get("fk"):
                f = c["fk"]
                pbo = f.get("entity") or next((x.get("business_object") for x in doc["tables"] if x["target_table"] == f.get("table")), None)
                rid = " | ".join(k for k, v in rels.items() if {v["subject"], v["object"]} == {t.get("business_object"), pbo}) or "none"
                parent = f.get("entity") or f.get("table")
                fks.append({"table": t["target_table"], "column": c["target"], "entity": parent, "entity_column": f.get("column"),
                            "cardinality": f.get("cardinality"), "orphan_policy": f.get("orphan_policy"), "relationship": rid})
                flows.append([t["target_table"], f"{c['target']} {f.get('cardinality')}", parent, rid])
            if c.get("confidence") in ("low", "unknown"):
                p.issue("warn", f"{t['target_table']}.{c['target']}", f"{c.get('confidence')} confidence" + (f"; question {c.get('open_question')}" if c.get("open_question") else ""))
    qs = _questions(sid, root)
    for q in qs:
        if q["blocking"] and q["status"] == "open":
            p.issue("error", q["id"], f"blocking question open: {q['question']}")
    if rev_res.upper() != "PASS":
        p.issue("info", "review", f"sttm_review.md: {rev_res}")
    p.m("Target tables", len(tabs))
    p.m("Columns", len(cols))
    p.m("Foreign keys", len(fks))
    p.m("Business-logic columns", sum(1 for c in cols if c["business_rule"]), "need CP4b")
    p.m("Low / unknown confidence", sum(1 for c in cols if c["confidence"] in ("low", "unknown")))
    p.m("Validator", "PASS" if r.ok else "FAIL", f"{len(r.errors)} errors, {len(r.warnings)} warnings")
    p.m("Independent review", rev_res)
    p["connections"] = {"kind": "flows", "caption": "Business object -> silver table -> shared masters (relationship id)", "flows": flows}
    p["decide"] = ["Is the grain right, and is the business key unique in bronze?",
                   "Does each foreign key follow a real business relationship?",
                   "Are the transforms exact, and does each column cite good evidence?"]
    p["tables"]["Tables"] = _table(tabs)
    p["tables"]["Columns"] = _table(cols)
    p["tables"]["Foreign keys"] = _table(fks, ["table", "column", "entity", "entity_column", "cardinality", "orphan_policy", "relationship"])
    p["key_table"] = "Columns"


def _cp4b(p, sid, root):
    doc = _sttm(p, sid, root)
    if not doc:
        return
    brs = _y("registry", "ontology", "business.yaml", root=root).get("business_rules", {})
    p.inp("registry", "ontology", "business.yaml")
    so = p.inp("sources", sid, "04_mapping", "reviews", "business_logic_signoff.md")
    reg = {r["evidence_id"]: r for r in _csv(os.path.join(root, "sources", sid, "02_evidence", "evidence_register.csv"))}
    rows = []
    for t in doc.get("tables", []):
        for c in t.get("columns", []):
            if c.get("business_logic"):
                br = brs.get(c.get("business_rule"), {})
                ev = (c.get("provenance") or {}).get("evidence") or []
                rows.append({"business_rule": c.get("business_rule"), "rule_text": br.get("desc"), "rule_status": br.get("status"), "owner": br.get("owner"),
                             "table": t["target_table"], "column": c["target"], "formula": c.get("transform"), "inputs": c.get("source"),
                             "evidence": ", ".join(ev), "evidence_claims": " | ".join(reg.get(e, {}).get("claim", "?") for e in ev)})
    res = "missing"
    if os.path.exists(so):
        res = next((ln.split(":", 1)[1].strip() for ln in open(so, encoding="utf-8") if ln.lower().startswith("result:")), "no result line")
    p.m("Business-logic columns", len(rows))
    p.m("Rules still 'proposed'", sum(1 for r in rows if r["rule_status"] == "proposed"))
    p.m("SME sign-off", res)
    p["connections"] = {"kind": "flows", "caption": "Business rule -> silver column -> formula",
                        "flows": [[r["business_rule"], "computes", f"{r['table']}.{r['column']}", r["formula"]] for r in rows]}
    if not rows:
        p.issue("info", "scope", "no business-logic columns: CP4b can be 'not_required'")
    for r in rows:
        if r["rule_status"] == "proposed":
            p.issue("info", r["business_rule"], "rule is 'proposed' in business.yaml; set 'approved' with the sign-off")
    p["decide"] = ["Is each formula the one the business uses (units, rounding, time zone)?",
                   "Are the inputs the right fields?", "Who owns each rule after go-live?"]
    p["tables"]["Business logic"] = _table(rows)
    p["key_table"] = "Business logic"


def _cp5(p, sid, root):
    doc = _sttm(p, sid, root)
    bdir = os.path.join("sources", sid, "05_build")
    nbs = sorted(glob.glob(os.path.join(root, bdir, "nb_*.py")))
    for n in nbs:
        p.inp(os.path.relpath(n, root))
    summ_p = p.inp(bdir, "qa_results", "summary.json")
    cr = p.inp(bdir, "reviews", "code_review.md")
    checks = json.load(open(summ_p, encoding="utf-8")).get("checks", []) if os.path.exists(summ_p) else []
    if not checks:
        p.issue("error", "qa", "05_build/qa_results/summary.json missing or empty")
    st = Counter(c.get("status") for c in checks)
    for c in checks:
        if c.get("status") != "pass":
            p.issue("error", f"{c.get('table')} {c.get('check')}", str(c.get("evidence"))[:200])
    todo, review = {}, {}
    for n in nbs:
        txt = open(n, encoding="utf-8").read().split("\n")
        todo[os.path.basename(n)] = sum(1 for ln in txt if ln.startswith("# TODO(genie)") and "df = df  # replace" in "\n".join(txt))
        review[os.path.basename(n)] = sum(1 for ln in txt if ln.startswith("# REVIEW("))
    for n, k in todo.items():
        if k:
            p.issue("warn", n, "a TODO(genie) cell still has the placeholder 'df = df  # replace'")
    for n, k in review.items():
        if k:
            p.issue("error", n, f"{k} REVIEW block(s): the STTM changed after this code was written; check and remove them")
    if doc and checks:
        import sys as _s
        _s.path.insert(0, root)
        from lib import qa_rules
        for tname, cv in qa_rules.coverage(doc, checks, root).items():
            if cv["missing"]:
                p.issue("error", tname, f"QA checks missing: {cv['missing']}")
    res = "missing"
    if os.path.exists(cr):
        res = next((ln.split(":", 1)[1].strip() for ln in open(cr, encoding="utf-8") if ln.lower().startswith("result:")), "no result line")
    p.m("Notebooks", len(nbs))
    p.m("QA pass / fail / error", f"{st['pass']} / {st['fail']} / {st['error']}")
    p.m("Code review", res)
    tables = [t["target_table"] for t in (doc or {}).get("tables", [])]
    p["connections"] = {"kind": "flows", "caption": "STTM table -> notebook -> QA result",
                        "flows": [[t, "built by", next((os.path.basename(n) for n in nbs if t in n), "(no notebook)"),
                                   f"{sum(1 for c in checks if c.get('table', '').endswith(t) and c.get('status') == 'pass')}/"
                                   f"{sum(1 for c in checks if c.get('table', '').endswith(t))} QA pass"] for t in tables]}
    p["decide"] = ["Does the code do exactly what the STTM says, and nothing more?",
                   "Do all QA checks pass without changed thresholds?", "Does the code follow the naming and coding standards?"]
    p["tables"]["QA checks"] = _table([{k: c.get(k) for k in ("check", "table", "status", "metric", "threshold", "evidence")} for c in checks],
                                      ["check", "table", "status", "metric", "threshold", "evidence"])
    p["tables"]["Notebooks"] = _table([{"notebook": k, "placeholder_left": bool(v), "review_blocks": review.get(k, 0)} for k, v in todo.items()],
                                      ["notebook", "placeholder_left", "review_blocks"])
    p["key_table"] = "QA checks"


def _cp6(p, sid, root):
    sdir = os.path.join("sources", sid)
    p.inp("registry", "sources.yaml")
    p.inp(sdir, "06_handoff", "readiness.md")
    reg = _y("registry", "sources.yaml", root=root)
    src = next((s for s in reg["sources"] if s["id"] == sid), {})
    cps = [(c, (reg.get("global_checkpoints", {}).get(c) or {}).get("status", "pending")) for c in fb.GLOBAL_CPS]
    cps += [(c, (src.get("checkpoints", {}).get(c) or {}).get("status", "pending")) for c in fb.SOURCE_CP_ORDER]
    order = ["CP1_source_brief", "CP2_evidence", "CP3_central_model", "CP3b_key_rules", "CP4_sttm", "CP4b_business_logic", "CP5_code_qa", "CP6_handoff"]
    cps.sort(key=lambda x: order.index(x[0]))
    deliv = ["04_mapping/sttm.yaml", "04_mapping/exports/sttm.xlsx", "04_mapping/exports/er.mmd", "05_build/qa_results/summary.json",
             "04_mapping/reviews/sttm_review.md", "05_build/reviews/code_review.md", "06_handoff/readiness.md"]
    drows = [{"deliverable": d, "present": os.path.exists(os.path.join(root, sdir, d))} for d in deliv]
    for d in drows:
        if not d["present"]:
            p.issue("error", d["deliverable"], "missing")
    allfb = [x for x in fb.all_feedback(root, sid)]
    for d in allfb:
        if d.get("status") in fb.BLOCKING:
            p.issue("error", d["id"], f"feedback {d.get('status')} at {d.get('checkpoint')}")
    for q in _questions(sid, root):
        if q["blocking"] and q["status"] == "open":
            p.issue("error", q["id"], "blocking question open")
    p.m("Checkpoints approved", f"{sum(1 for _, s in cps if s in ('approved', 'not_required'))} / {len(cps)}")
    p.m("Deliverables present", f"{sum(d['present'] for d in drows)} / {len(drows)}")
    p.m("Feedback items (all)", len(allfb))
    p["connections"] = {"kind": "chain", "caption": "Checkpoint status for this source", "steps": [[c.split("_")[0], s] for c, s in cps]}
    p["decide"] = ["Can the deployment team run the job from this package alone?",
                   "Are known limits and non-blocking questions acceptable for go-live?", "Are grants and parameters per environment clear?"]
    p["tables"]["Checkpoints"] = _table([{"checkpoint": c, "status": s} for c, s in cps])
    p["tables"]["Deliverables"] = _table(drows)
    p["tables"]["Feedback history"] = _table([{"id": d["id"], "checkpoint": d.get("checkpoint"), "status": d.get("status"),
                                               "comment": " ".join(str(d.get("comment") or "").split())[:200]} for d in allfb])
    p["key_table"] = "Deliverables"


COLLECT = {"CP1_source_brief": _cp1, "CP2_evidence": _cp2, "CP3_central_model": _cp3,
           "CP3b_key_rules": lambda p, s, r: _cp3(p, s, r, keys_only=True), "CP4_sttm": _cp4,
           "CP4b_business_logic": _cp4b, "CP5_code_qa": _cp5, "CP6_handoff": _cp6}


def build(source_id, cp, root=None):
    root = root or ROOT
    p = Pack(source_id, cp, root)
    COLLECT[cp](p, source_id, root)
    qs = _questions(source_id, root) if cp not in fb.GLOBAL_CPS else []
    if qs:
        p["tables"]["Questions"] = _table(qs)
    fbs = _feedback(source_id, cp, root)
    p["tables"]["Feedback"] = _table(fbs, ["id", "status", "raised_by", "kinds", "comment", "file"])
    for d in fbs:
        if d["status"] in fb.BLOCKING:
            p.issue("error", d["id"], f"feedback is '{d['status']}': blocks approval")
    ups = [d for d in fb.all_feedback(root, None if cp in fb.GLOBAL_CPS else source_id) if d.get("blocks") == cp and d.get("status") in fb.UNRESOLVED]
    for d in ups:
        p.issue("error", d["id"], f"upstream issue at {d['checkpoint']} ({d['status']}) blocks this checkpoint: {' '.join(str(d.get('comment')).split())[:160]}")
    if ups:
        p["tables"]["Upstream issues"] = _table([{"id": d["id"], "at": d["checkpoint"], "status": d["status"], "raised_by": d.get("raised_by"),
                                                  "comment": " ".join(str(d.get("comment")).split())} for d in ups])
    if cp not in fb.GLOBAL_CPS:
        _person_inputs(p, source_id, cp, root)
    sev = {"error": 0, "warn": 1, "info": 2}
    p["issues"].sort(key=lambda i: sev.get(i["severity"], 9))
    p["counts"] = dict(Counter(i["severity"] for i in p["issues"]))
    return p


def _person_inputs(p, sid, cp, root):
    """Handover files, standing instructions, and clarify status: what people gave this stage."""
    sdir = os.path.join(root, "sources", sid)
    hd = os.path.join(sdir, fb.CP_FOLDER.get(cp, "01_intake"), "handover")
    files = sorted(f for f in (os.listdir(hd) if os.path.isdir(hd) else []) if not f.startswith("."))
    for f in files:
        p.inp(os.path.relpath(os.path.join(hd, f), root))
    p["handover_files"] = [os.path.relpath(os.path.join(hd, f), root) for f in files]
    if files:
        p.m("Handover files from people", len(files), "passed to the next stage")
        p["tables"]["Handover files"] = _table([{"file": f} for f in p["handover_files"]])
    ins = (_y("sources", sid, "instructions.yaml", root=root) or {}).get("instructions") or []
    act = [i for i in ins if i.get("status") == "active"]
    if act:
        p["tables"]["Instructions"] = _table(act, ["id", "step", "text", "by", "on"])
    qz = (_y("sources", sid, "clarify_index.yaml", root=root) or {}).get("items") or []
    mine = [i for i in qz if i.get("checkpoint") == cp]
    if mine:
        p["tables"]["Clarify"] = _table(mine, ["id", "mode", "ref", "status", "on", "reason"])
    for i in mine:
        if i.get("status") == "asked":
            p.issue("warn", i["id"], "clarify questions not answered yet")


# ----------------------------------------------------------------------------- writers
def _name(p):
    return p["checkpoint"]


def write_json(p, d):
    out = {k: v for k, v in p.items()}
    with open(os.path.join(d, _name(p) + ".json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)


def write_xlsx(p, d):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = "README"
    bold = Font(bold=True)
    head = PatternFill("solid", fgColor="DDE3E8")
    ws.append([f"{p['checkpoint']} - {p['title']}"])
    ws["A1"].font = Font(bold=True, size=14)
    for k in ("source_id", "phase", "status", "approver", "generated_at", "next_step", "purpose"):
        ws.append([k, p[k]])
    ws.append([])
    ws.append(["Key numbers", "value", "note"])
    for c in ws[ws.max_row]:
        c.font, c.fill = bold, head
    for m in p["metrics"]:
        ws.append([m["label"], str(m["value"]), m["note"]])
    ws.append([])
    ws.append(["Needs attention", "item", "text"])
    for c in ws[ws.max_row]:
        c.font, c.fill = bold, head
    for i in p["issues"] or [{"severity": "-", "item": "-", "text": "No issues found by code."}]:
        ws.append([i["severity"], i["item"], i["text"]])
    ws.append([])
    ws.append(["Reviewer decides"])
    ws[f"A{ws.max_row}"].font = bold
    for q in p["decide"]:
        ws.append(["", q])
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width, ws.column_dimensions["C"].width = 30, 60, 60
    for name, t in p["tables"].items():
        s = wb.create_sheet(re.sub(r"[\[\]\*\?/\\:]", "", name)[:31])
        s.append(t["columns"])
        for c in s[1]:
            c.font, c.fill = bold, head
        for r in t["rows"]:
            s.append(["" if v is None else (v if isinstance(v, (int, float, bool)) else str(v)) for v in r])
        s.freeze_panes = "A2"
        if t["columns"]:
            s.auto_filter.ref = f"A1:{get_column_letter(len(t['columns']))}{max(1, s.max_row)}"
        for i, col in enumerate(t["columns"], 1):
            w = max([len(str(col))] + [len(str(r[i - 1] or "")) for r in t["rows"][:200]])
            s.column_dimensions[get_column_letter(i)].width = min(max(10, w + 2), 60)
            for cell in s[get_column_letter(i)][1:]:
                cell.alignment = Alignment(wrap_text=w > 60, vertical="top")
    wb.save(os.path.join(d, _name(p) + ".xlsx"))


def write_md(p, d):
    L = [f"# {p['checkpoint']} - {p['title']}", "",
         f"Source: `{p['source_id']}` · Phase: {p['phase']} · Status: **{p['status']}** · Approver: {p['approver']} · Generated: {p['generated_at']}", "",
         p["purpose"], "", "## Key numbers", "", "| Item | Value | Note |", "|---|---|---|"]
    L += [f"| {m['label']} | {m['value']} | {m['note']} |" for m in p["metrics"]]
    L += ["", "## Connections", ""]
    for c in (p["connections"] if isinstance(p["connections"], list) else [p["connections"]]):
        if c.get("caption"):
            L.append(f"*{c['caption']}*")
        if c.get("kind") == "flows":
            L += [f"- `{f[0]}` {f[1]} -> `{f[2]}`" + (f" ({f[3]})" if len(f) > 3 and f[3] else "") for f in c["flows"][:30]]
        elif c.get("kind") in ("chain", "funnel"):
            L += [f"- {a}: {b}" for a, b in c["steps"]]
        elif c.get("kind") == "matrix":
            L += ["| | " + " | ".join(c["cols"]) + " |", "|---" * (len(c["cols"]) + 1) + "|"]
            L += [f"| {r} | " + " | ".join(str(v) for v in c["cells"][i]) + " |" for i, r in enumerate(c["rows"])]
        L.append("")
    L += ["## Needs attention", ""]
    L += [f"- **{i['severity']}** `{i['item']}`: {i['text']}" for i in p["issues"]] or ["No issues found by code."]
    L += ["", "## Reviewer decides", ""] + [f"- [ ] {q}" for q in p["decide"]]
    L += ["", "## Files in this pack", "",
          f"- `{_name(p)}.xlsx` full lists: {', '.join(p['tables'])}",
          f"- `{_name(p)}.json` machine-readable, for {p['next_step']}",
          f"- `{_name(p)}.html` one-page view", "",
          f"Give feedback: `python tools/x_feedback.py new {p['source_id']} {p['checkpoint']} --comment \"...\"`", ""]
    with open(os.path.join(d, _name(p) + ".md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))


CSS = """
:root{--bg:#f4f6f7;--sf:#fff;--ink:#18232b;--mu:#5b6a74;--ln:#d5dde2;--err:#a3202f;--errb:#f8e6e8;--wrn:#8a5a00;--wrnb:#fbf0d9;--inf:#3d4f9c;--infb:#e7eaf7;--ok:#0f7c78;--okb:#e3f3f1;
--sans:"Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;--mono:ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#12181c;--sf:#1a2227;--ink:#e3e9ec;--mu:#94a3ad;--ln:#2c3840;--err:#f08a98;--errb:#3a1d22;--wrn:#f0c05a;--wrnb:#352b14;--inf:#9aa9f0;--infb:#1e2540;--ok:#4fc3bc;--okb:#143331;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#12181c;--sf:#1a2227;--ink:#e3e9ec;--mu:#94a3ad;--ln:#2c3840;--err:#f08a98;--errb:#3a1d22;--wrn:#f0c05a;--wrnb:#352b14;--inf:#9aa9f0;--infb:#1e2540;--ok:#4fc3bc;--okb:#143331;color-scheme:dark}
*{box-sizing:border-box}main>*,section,header{min-width:0}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 var(--sans)}
main{max-width:1040px;margin:0 auto;padding-block:24px 48px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:grid;gap:24px}
h1{font-size:28px;line-height:1.15;margin:0;text-wrap:balance}h2{font-size:13px;font-family:var(--mono);text-transform:uppercase;letter-spacing:.08em;color:var(--mu);margin:0 0 8px;font-weight:500}
p{margin:0;max-width:70ch}code{font-family:var(--mono);font-size:.86em}
.meta{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13px;color:var(--mu)}
.pill{display:inline-block;padding:1px 8px;font-family:var(--mono);font-size:12px;border:1px solid currentColor}
.s-approved,.s-not_required{color:var(--ok)}.s-pending{color:var(--mu)}.s-in_review{color:var(--inf)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}
.tile{background:var(--sf);border:1px solid var(--ln);padding:10px 12px;display:grid;gap:2px;align-content:start}
.tile b{font-size:22px;font-variant-numeric:tabular-nums;line-height:1.1;overflow-wrap:anywhere}.tile span{font-size:13px;color:var(--mu)}
.box{background:var(--sf);border:1px solid var(--ln);padding:14px 16px;min-width:0}
.flow{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr) auto;gap:6px 10px;align-items:center;font-size:14px}
.node{border:1px solid var(--ln);padding:4px 8px;font-family:var(--mono);font-size:12.5px;overflow-wrap:anywhere;background:var(--bg)}
.edge{color:var(--mu);font-size:12.5px;white-space:nowrap}.edge::after{content:" \\2192"}.rid{font-family:var(--mono);font-size:11.5px;color:var(--mu);overflow-wrap:anywhere}
@media (max-width:620px){.flow{grid-template-columns:1fr}.edge{white-space:normal}}
.funnel{display:grid;gap:4px}.fs{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:6px 12px;background:var(--infb);margin-inline:calc(var(--i)*3%)}
.fs b{font-weight:600}.fs span{font-family:var(--mono);font-size:12.5px;color:var(--inf)}
.chain{display:flex;flex-wrap:wrap;gap:6px}.ch{padding:6px 10px;border:1px solid var(--ln);font-family:var(--mono);font-size:12.5px;display:grid}
.ch small{font-size:11px}
.issues{list-style:none;margin:0;padding:0;display:grid;gap:4px}
.issues li{display:grid;grid-template-columns:62px minmax(0,1fr);gap:10px;padding:6px 10px;font-size:14px}
.issues .sev{font-family:var(--mono);font-size:11.5px;text-transform:uppercase;padding-top:2px}
.error{background:var(--errb)}.error .sev{color:var(--err)}.warn{background:var(--wrnb)}.warn .sev{color:var(--wrn)}.info{background:var(--infb)}.info .sev{color:var(--inf)}
.issues code{overflow-wrap:anywhere}
.decide{margin:0;padding-left:20px;display:grid;gap:4px}
.tw{overflow-x:auto;background:var(--sf);border:1px solid var(--ln)}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--ln);vertical-align:top}
th{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--mu);font-weight:500;white-space:nowrap}
td{max-width:420px;min-width:80px;overflow-wrap:break-word}tr:last-child td{border-bottom:0}
.mx td,.mx th{text-align:center}.mx td:first-child,.mx th:first-child{text-align:left}.mx td{font-variant-numeric:tabular-nums}
.z{color:var(--mu)}
footer{font-size:13px;color:var(--mu);display:grid;gap:4px;border-top:1px solid var(--ln);padding-top:10px}
"""


def _conn_html(c):
    e = html.escape
    if isinstance(c, list):
        return "<div style='display:grid;gap:18px'>" + "".join(_conn_html(x) for x in c) + "</div>"
    k = c.get("kind")
    cap = f"<p style='font-size:13px;color:var(--mu);margin-bottom:8px'>{e(c.get('caption', ''))}</p>" if c.get("caption") else ""
    if k == "funnel":
        return "<div class='funnel'>" + "".join(f"<div class='fs' style='--i:{i}'><b>{e(a)}</b><span>{e(b)}</span></div>" for i, (a, b) in enumerate(c["steps"])) + "</div>"
    if k == "flows":
        rows = "".join(f"<div class='node'>{e(str(f[0]))}</div><div class='edge'>{e(str(f[1]))}</div><div class='node'>{e(str(f[2]))}</div>"
                       f"<div class='rid'>{e(str(f[3])) if len(f) > 3 else ''}</div>" for f in c["flows"])
        return cap + f"<div class='flow'>{rows}</div>"
    if k == "matrix":
        head = "<tr><th></th>" + "".join(f"<th>{e(x)}</th>" for x in c["cols"]) + "</tr>"
        body = "".join("<tr><td><b>" + e(r) + "</b></td>" + "".join(f"<td class='{'z' if v == 0 else ''}'>{v}</td>" for v in c["cells"][i]) + "</tr>"
                       for i, r in enumerate(c["rows"]))
        return cap + f"<div class='tw'><table class='mx'>{head}{body}</table></div>"
    if k == "chain":
        return cap + "<div class='chain'>" + "".join(f"<div class='ch s-{e(s.replace(' ', '_'))}'>{e(a)}<small>{e(s)}</small></div>" for a, s in c["steps"]) + "</div>"
    return "<p>No connections for this checkpoint.</p>"


def write_html(p, d):
    e = html.escape
    tiles = "".join(f"<div class='tile'><b>{e(str(m['value']))}</b><span>{e(m['label'])}{(' · ' + e(m['note'])) if m['note'] else ''}</span></div>" for m in p["metrics"])
    iss = "".join(f"<li class='{e(i['severity'])}'><span class='sev'>{e(i['severity'])}</span><span><code>{e(str(i['item']))}</code> {e(i['text'])}</span></li>"
                  for i in p["issues"][:30])
    more = f"<p style='font-size:13px;color:var(--mu)'>{len(p['issues']) - 30} more in the .xlsx (README sheet).</p>" if len(p["issues"]) > 30 else ""
    iss_html = f"<ul class='issues'>{iss}</ul>{more}" if p["issues"] else "<p>No issues found by code.</p>"
    kt = p["tables"].get(p.get("key_table") or "", None)
    kt_html = ""
    if kt and kt["rows"]:
        head = "".join(f"<th>{e(c)}</th>" for c in kt["columns"])
        body = "".join("<tr>" + "".join(f"<td>{e('' if v is None else str(v))}</td>" for v in r) + "</tr>" for r in kt["rows"][:MAX_HTML_ROWS])
        cut = f" (first {MAX_HTML_ROWS} of {len(kt['rows'])})" if len(kt["rows"]) > MAX_HTML_ROWS else ""
        kt_html = f"<section><h2>{e(p['key_table'])}{cut}</h2><div class='tw'><table><tr>{head}</tr>{body}</table></div></section>"
    cnt = p.get("counts", {})
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e(p['checkpoint'])} {e(p['source_id'])}</title><style>{CSS}</style></head><body><main>
<header style="display:grid;gap:8px"><h2>{e(p['phase'])} · checkpoint · {e(p['source_id'])}</h2><h1>{e(p['checkpoint'].split('_')[0])} {e(p['title'])}</h1>
<div class="meta"><span class="pill s-{e(p['status'])}">{e(p['status'])}</span><span>Approver: {e(str(p['approver']))}</span><span>Generated {e(p['generated_at'])}</span>
<span>{cnt.get('error', 0)} errors · {cnt.get('warn', 0)} warnings</span></div><p>{e(p['purpose'])}</p></header>
<section><h2>Key numbers</h2><div class="tiles">{tiles}</div></section>
<section><h2>Connections</h2><div class="box">{_conn_html(p['connections'])}</div></section>
<section><h2>Needs attention</h2>{iss_html}</section>
<section><h2>Reviewer decides</h2><div class="box"><ol class="decide">{''.join(f'<li>{e(q)}</li>' for q in p['decide'])}</ol></div></section>
{kt_html}
<footer><span>Full lists: <code>{e(_name(p))}.xlsx</code> ({e(', '.join(p['tables']))}). Machine-readable: <code>{e(_name(p))}.json</code>. Next: {e(p['next_step'])}.</span>
{('<span>Handover files for the next stage: ' + ', '.join('<code>' + e(f) + '</code>' for f in p.get('handover_files', [])) + '</span>') if p.get('handover_files') else ''}
<span>Feedback: <code>python tools/x_feedback.py new {e(p['source_id'])} {e(p['checkpoint'])} --comment "..."</code></span></footer>
</main></body></html>"""
    with open(os.path.join(d, _name(p) + ".html"), "w", encoding="utf-8") as f:
        f.write(doc)


def write(source_id, cp, root=None):
    root = root or ROOT
    p = build(source_id, cp, root)
    d = pack_dir(source_id, cp, root)
    os.makedirs(d, exist_ok=True)
    write_json(p, d)
    write_xlsx(p, d)
    write_md(p, d)
    write_html(p, d)
    return p, d


def board(root=None):
    """One view of ALL feedback: human items and agent-raised upstream issues -> registry/board/."""
    root = root or ROOT
    items = fb.all_feedback(root)
    p = {"checkpoint": "feedback_board", "source_id": "all sources", "phase": "X", "title": "Feedback and upstream issues",
         "purpose": "All human feedback and all agent-raised upstream issues, with what each one blocks.",
         "approver": "each item's checkpoint approver", "status": f"{sum(1 for d in items if d.get('status') in fb.UNRESOLVED)} unresolved",
         "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "next_step": "x-feedback-rerun", "inputs": {},
         "metrics": [], "issues": [], "tables": {}, "key_table": "Items"}
    st = Counter(d.get("status") for d in items)
    p["metrics"] = [{"label": "Items", "value": len(items), "note": ""},
                    {"label": "Proposed by agents (to triage)", "value": st["proposed"], "note": "accept or reject"},
                    {"label": "Open / in progress / applied", "value": f"{st['open']} / {st['in_progress']} / {st['applied']}", "note": ""},
                    {"label": "Verified / rejected", "value": f"{st['verified']} / {st['rejected']}", "note": ""}]
    for d in items:
        n = fb.repeats(d, items)
        if d.get("status") == "proposed":
            p["issues"].append({"severity": "warn", "item": d["id"], "text": f"proposed by {d.get('raised_by')} at {d['checkpoint']}: a person must accept or reject"})
        if n > fb.MAX_REPEATS and d.get("status") in fb.UNRESOLVED:
            p["issues"].append({"severity": "error", "item": d["id"], "text": f"attempt {n} for the same problem: a person decides"})
    p["connections"] = {"kind": "flows", "caption": "Who raised it -> at which checkpoint (status) -> what it blocks",
                        "flows": [[d.get("raised_by"), f"{d['id']} {d.get('status')}", f"{d['source_id']} {d['checkpoint']}",
                                   f"blocks {d['blocks']}" if d.get("blocks") else ""] for d in items if d.get("status") in fb.UNRESOLVED]}
    p["decide"] = ["Accept or reject each proposed item.", "Verify each applied item.", "Stop loops: decide items that came back a third time."]
    p["tables"]["Items"] = _table([{"id": d["id"], "source": d["source_id"], "checkpoint": d["checkpoint"], "status": d.get("status"),
                                     "raised_by": d.get("raised_by"), "blocks": d.get("blocks"), "related": d.get("related"),
                                     "kinds": ", ".join(k for k in fb.KINDS if d.get(k)), "comment": " ".join(str(d.get("comment") or "").split())[:240],
                                     "file": d["_path"]} for d in items])
    p["counts"] = dict(Counter(i["severity"] for i in p["issues"]))
    d = os.path.join(root, "registry", "board")
    os.makedirs(d, exist_ok=True)
    for w in (write_json, write_xlsx, write_md, write_html):
        w(p, d)
    return p, d


def stale(source_id, cp, root=None):
    """Return None if the pack is fresh, else a reason string."""
    root = root or ROOT
    jp = os.path.join(pack_dir(source_id, cp, root), cp + ".json")
    if not os.path.exists(jp):
        return "checkpoint pack missing: run tools/x_checkpoint_pack.py"
    with open(jp, encoding="utf-8") as f:
        inputs = json.load(f).get("inputs", {})
    for rel, h in inputs.items():
        full = os.path.join(root, rel)
        if not os.path.exists(full) or _sha1(full) != h:
            return f"checkpoint pack is stale ({rel} changed): run tools/x_checkpoint_pack.py again"
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source_id", help="source id, 'global' for CP3 / CP3b, or 'board' for the feedback board")
    ap.add_argument("checkpoint", nargs="?")
    ap.add_argument("--all", action="store_true", help="all checkpoints of this source (or both global ones)")
    a = ap.parse_args(argv)
    if a.source_id == "board":
        p, d = board()
        print(f"feedback board: {os.path.relpath(d, ROOT)}/feedback_board.(json|xlsx|md|html)")
        return 0
    cps = (fb.GLOBAL_CPS if a.source_id == "global" else fb.SOURCE_CP_ORDER) if a.all else [a.checkpoint]
    if not cps or cps == [None]:
        ap.error("give a checkpoint or --all")
    for cp in cps:
        p, d = write(a.source_id, cp)
        c = p.get("counts", {})
        print(f"{cp}: {os.path.relpath(d, ROOT)}/{cp}.(json|xlsx|md|html)  errors={c.get('error', 0)} warnings={c.get('warn', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
