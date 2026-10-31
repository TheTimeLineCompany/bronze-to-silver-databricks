#!/usr/bin/env python3
"""Checkpoint check for registry/sources.yaml (runs on every PR).

A checkpoint can be 'approved' only when (also: its checkpoint pack exists and is not stale):
  1. the checkpoints before it are approved (or not_required),
  2. its evidence files exist and pass their code checks,
  3. no feedback for it is still open, in_progress, or applied-but-not-verified,
  4. approved_by, date, and pr are filled in.
Approval itself is a human PR review (CODEOWNERS). This script checks the approval is allowed.

Usage:
    python tools/x_validate_gate.py                         # all sources
    python tools/x_validate_gate.py S07_container_moves
    python tools/x_validate_gate.py --next                  # what each source needs next

Exit code 0 = consistent. Exit code 1 = a checkpoint is approved too early or without evidence.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import p1_2_check_context as ctxcheck  # noqa: E402
import p4_2_validate_sttm as vsttm  # noqa: E402
import x_checkpoint_pack as pack  # noqa: E402
sys.path.insert(0, ROOT)
from lib import qa_rules  # noqa: E402
import x_feedback as fb  # noqa: E402

ORDER = fb.SOURCE_CP_ORDER
GLOBAL = fb.GLOBAL_CPS
OK = {"approved", "not_required"}


def _load(p):
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _passed(path):
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as f:
        return any(line.strip().lower() == "result: pass" for line in f)


def open_feedback(root, source_id, cp):
    return [d["id"] for d in fb.all_feedback(root, source_id) if d.get("checkpoint") == cp and d.get("status") in fb.BLOCKING]


def upstream_blockers(root, source_id, cp):
    """Agent-raised items that name this checkpoint in 'blocks' and are not resolved yet."""
    return [d["id"] for d in fb.all_feedback(root, source_id) if d.get("blocks") == cp and d.get("status") in fb.UNRESOLVED]


def check(root=ROOT, only=None):
    errors, notes = [], []
    reg = _load(os.path.join(root, "registry/sources.yaml"))
    ents = _load(os.path.join(root, "registry/entities.yaml"))["entities"]
    qs = (_load(os.path.join(root, "registry/open_questions.yaml")) or {}).get("questions", [])
    gl = reg.get("global_checkpoints", {})

    def meta(where, g):
        for k in ("approved_by", "date", "pr"):
            if not g.get(k):
                errors.append(f"{where}: approved but '{k}' is empty")

    # feedback files must be well formed
    allfb = fb.all_feedback(root)
    from collections import Counter as _C
    for fid, n in _C(str(d.get("id")) for d in allfb).items():
        if n > 1:
            errors.append(f"feedback: id {fid} is used by {n} files (two branches picked the same id): rename one")
    for d in allfb:
        errors += [f"feedback: {e}" for e in fb.validate_item(d)]
        if d.get("status") in fb.UNRESOLVED and fb.repeats(d, allfb) > fb.MAX_REPEATS:
            errors.append(f"feedback: {d['id']} is the {fb.repeats(d, allfb)}. attempt for the same problem - a person must decide")

    # global checkpoints
    for cp in GLOBAL:
        g = gl.get(cp, {})
        if g.get("status") != "approved":
            continue
        meta(cp, g)
        if cp == "CP3_central_model":
            bad = [e["name"] for e in ents if e.get("status") != "approved"]
            if bad:
                errors.append(f"{cp}: approved but entities not approved: {bad}")
        if cp == "CP3b_key_rules" and gl.get("CP3_central_model", {}).get("status") != "approved":
            errors.append(f"{cp}: approved before CP3_central_model")
        op = open_feedback(root, "global", cp)
        if op:
            errors.append(f"{cp}: feedback still open {op}")
        st = pack.stale("global", cp, root)
        if st:
            errors.append(f"{cp}: {st}")
    globals_ok = all(gl.get(c, {}).get("status") == "approved" for c in GLOBAL)

    ctx = vsttm.load_context(root)
    for s in reg["sources"]:
        sid = s["id"]
        if only and sid != only:
            continue
        cps = s.get("checkpoints", {})
        sdir = os.path.join(root, "sources", sid)
        sttm = os.path.join(sdir, "04_mapping", "sttm.yaml")
        blocking_q = [q["id"] for q in qs if q.get("source_id") == sid and q.get("blocking") and q.get("status") == "open"]
        needs_4b = False
        if os.path.exists(sttm):
            try:
                needs_4b = any(c.get("business_logic") for t in _load(sttm).get("tables", []) for c in t.get("columns", []))
            except Exception:  # noqa: BLE001
                pass
        for i, cp in enumerate(ORDER):
            st = cps.get(cp, {}).get("status", "pending")
            w = f"{sid}.{cp}"
            if cp == "CP4b_business_logic" and st == "not_required" and needs_4b:
                errors.append(f"{w}: not_required, but the STTM has business_logic columns")
            if st != "approved":
                continue
            meta(w, cps[cp])
            for prev in ORDER[:i]:
                if cps.get(prev, {}).get("status") not in OK:
                    errors.append(f"{w}: approved before {prev}")
            op = open_feedback(root, sid, cp)
            if op:
                errors.append(f"{w}: feedback still open or not verified: {op}")
            ub = upstream_blockers(root, sid, cp)
            if ub:
                errors.append(f"{w}: upstream issues raised from this phase are not resolved: {ub}")
            st = pack.stale(sid, cp, root)
            if st:
                errors.append(f"{w}: {st}")
            if cp == "CP1_source_brief":
                e = ctxcheck.check(sid, root)
                for area in ("triage", "brief"):
                    errors += [f"{w}: {area}: {x}" for x in e[area]]
            if cp == "CP2_evidence":
                e = ctxcheck.check(sid, root, only="evidence")
                errors += [f"{w}: evidence: {x}" for x in e["evidence"]]
                disc = os.path.join(sdir, "02_evidence", "discovery")
                if not (os.path.exists(os.path.join(disc, "tables.csv")) or glob.glob(os.path.join(sdir, "02_evidence", "profiling", "*.json"))):
                    errors.append(f"{w}: no bronze results: run tools/p2_2_discover.py (02_evidence/discovery/tables.csv) "
                                  "or tools/p2_2_profile_table.py (02_evidence/profiling/*.json)")
                cards = {os.path.basename(c)[:-3] for c in glob.glob(os.path.join(disc, "cards", "[TRD]-*.md"))}
                done = {os.path.basename(c).split(".")[0] for c in glob.glob(os.path.join(disc, "cards", "*.result.yaml"))}
                if cards - done:
                    errors.append(f"{w}: discovery cards not answered: {sorted(cards - done)}")
            if cp == "CP4_sttm":
                if not globals_ok:
                    errors.append(f"{w}: approved before global CP3 and CP3b")
                if not os.path.exists(sttm):
                    errors.append(f"{w}: 04_mapping/sttm.yaml missing")
                else:
                    r = vsttm.validate(sttm, ctx, root)
                    if not r.ok:
                        errors.append(f"{w}: STTM validator fails ({len(r.errors)} errors)")
                    if _load(sttm).get("status") != "approved":
                        errors.append(f"{w}: STTM status is not 'approved'")
                if not _passed(os.path.join(sdir, "04_mapping", "reviews", "sttm_review.md")):
                    errors.append(f"{w}: 04_mapping/reviews/sttm_review.md missing or not 'Result: PASS'")
            if cp == "CP4b_business_logic" and not _passed(os.path.join(sdir, "04_mapping", "reviews", "business_logic_signoff.md")):
                errors.append(f"{w}: 04_mapping/reviews/business_logic_signoff.md missing or not 'Result: PASS'")
            if cp == "CP5_code_qa":
                summ = os.path.join(sdir, "05_build", "qa_results", "summary.json")
                if not os.path.exists(summ):
                    errors.append(f"{w}: 05_build/qa_results/summary.json missing")
                else:
                    with open(summ, encoding="utf-8") as f:
                        res = json.load(f)
                    checks = res.get("checks", [])
                    if not checks:
                        errors.append(f"{w}: QA summary has no checks")
                    if os.path.exists(sttm):
                        # every applicable checklist item, for every mapped table, must be present and pass
                        for tname, cv in qa_rules.coverage(_load(sttm), checks, root).items():
                            if cv["missing"]:
                                errors.append(f"{w}: QA missing for {tname}: {cv['missing']} (required: {cv['required']})")
                            if cv["not_passing"]:
                                errors.append(f"{w}: QA not passing for {tname}: {cv['not_passing']}")
                    stray = [c.get("check") for c in checks if c.get("status") != "pass"
                             and str(c.get("table") or "").split(".")[-1] not in {n for n, _ in qa_rules.expected_results(_load(sttm) or {"tables": []})}]
                    if stray:
                        errors.append(f"{w}: QA not passing for tables outside the STTM: {stray}")
                # shared masters: the master build (masters/<table>/) must have run with full, passing QA
                for t_ in (_load(sttm) or {}).get("tables", []) if os.path.exists(sttm) else []:
                    if t_.get("target_kind") != "master":
                        continue
                    mdir = os.path.join(root, "masters", t_["target_table"])
                    ms = os.path.join(mdir, "qa_results", "summary.json")
                    if not os.path.exists(ms):
                        errors.append(f"{w}: master build QA missing: masters/{t_['target_table']}/qa_results/summary.json "
                                      f"(generate with tools/p5_4_gen_master_build.py {t_.get('conformed_entity')}, then run it)")
                        continue
                    from lib.survivorship import feeding_sttms, master_spec
                    ent_by = {e["name"]: e for e in ents}
                    feed = feeding_sttms(t_.get("conformed_entity"), root)
                    spec = master_spec(ent_by[t_["conformed_entity"]], list(feed.values()))
                    with open(ms, encoding="utf-8") as f:
                        mres = json.load(f).get("checks", [])
                    cv = qa_rules.coverage({}, mres, root, pairs=[(t_["target_table"], spec)])[t_["target_table"]]
                    if cv["missing"] or cv["not_passing"]:
                        errors.append(f"{w}: master build QA for {t_['target_table']}: missing {cv['missing']}, not passing {cv['not_passing']}")
                for nb in sorted(glob.glob(os.path.join(sdir, "05_build", "nb_*.py"))):
                    with open(nb, encoding="utf-8") as f:
                        txt = f.read()
                    if "# REVIEW(" in txt:
                        errors.append(f"{w}: {os.path.basename(nb)} has REVIEW blocks (STTM changed after the code was written)")
                    if "df = df  # replace" in txt:
                        errors.append(f"{w}: {os.path.basename(nb)} still has an unfinished TODO(genie) cell")
                if not _passed(os.path.join(sdir, "05_build", "reviews", "code_review.md")):
                    errors.append(f"{w}: 05_build/reviews/code_review.md missing or not 'Result: PASS'")
            if cp == "CP6_handoff":
                for f_ in ("04_mapping/exports/sttm.xlsx", "04_mapping/exports/er.mmd", "06_handoff/readiness.md"):
                    if not os.path.exists(os.path.join(sdir, f_)):
                        errors.append(f"{w}: {f_} missing")
                if blocking_q:
                    errors.append(f"{w}: blocking questions still open: {blocking_q}")
        nxt = next((c for c in ORDER if cps.get(c, {}).get("status") not in OK), None)
        opn = [d["id"] for d in fb.all_feedback(root, sid) if d.get("status") in fb.UNRESOLVED]
        notes.append(f"{sid}: next checkpoint = {nxt or 'done'}"
                     + (f"; blocking questions: {blocking_q}" if blocking_q else "")
                     + (f"; open feedback: {opn}" if opn else ""))
    return errors, notes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?")
    ap.add_argument("--next", action="store_true")
    a = ap.parse_args(argv)
    errors, notes = check(only=a.source)
    if a.next or not errors:
        print("\n".join(notes))
    for e in errors:
        print(f"ERROR  {e}")
    print("CHECKPOINTS CONSISTENT" if not errors else f"CHECKPOINT CHECK FAILED ({len(errors)} errors)")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
