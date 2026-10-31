#!/usr/bin/env python3
"""P1.2 / P1.3 / P2.3 checks: keep the agent focused and every claim traceable.

Checks three files: sources/<id>/01_intake/ (triage, brief) and 02_evidence/ (register):
  triage.yaml            every inventoried file classified; core files within budget; read plans present
  source_brief.md        short (word budget) and cites evidence ids that exist
  evidence_register.csv  well-formed claims with origin, confidence, status; no evidence from ignored files

Usage:
    python tools/p1_2_check_context.py S07_container_moves                 # all three
    python tools/p1_2_check_context.py S07_container_moves --only triage   # triage | brief | evidence

Exit code 0 = OK, 1 = errors.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EID = re.compile(r"\bE-\d{4}\b")
REG_COLS = ["evidence_id", "claim", "about_type", "about", "origin", "file_id", "location",
            "doc_type", "confidence", "status", "corroborated_by", "notes"]
ABOUT_TYPES = {"table", "column", "grain", "key", "relationship", "entity", "business_rule", "code_value", "other"}


def _y(p):
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_register(path):
    if not os.path.exists(path):
        return None
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check(source_id, root=ROOT, only=None):
    onto = _y(os.path.join(root, "registry", "ontology", "information.yaml"))
    sdir = os.path.join(root, "sources", source_id)
    errs = {"triage": [], "brief": [], "evidence": []}
    manifest_p = os.path.join(sdir, "01_intake", "manifest.csv")
    manifest = {}
    if os.path.exists(manifest_p):
        with open(manifest_p, newline="", encoding="utf-8") as f:
            manifest = {r["file_id"]: r for r in csv.DictReader(f)}
    triage_p = os.path.join(sdir, "01_intake", "triage.yaml")
    triage = {}

    # ---- triage
    if only in (None, "triage", "evidence"):
        if not manifest:
            errs["triage"].append("01_intake/manifest.csv missing or empty: run tools/p1_1_inventory.py")
        if not os.path.exists(triage_p):
            errs["triage"].append("01_intake/triage.yaml missing")
        else:
            t = _y(triage_p) or {}
            files = t.get("files", [])
            triage = {d["file_id"]: d for d in files}
            types = set(onto["document_types"])
            rels = set(onto["relevance"])
            for fid in manifest:
                if fid not in triage:
                    errs["triage"].append(f"{fid} ({manifest[fid]['path']}) is not in triage.yaml (run inventory --refresh-triage)")
            for d in files:
                w = f"{d.get('file_id')} {d.get('path')}"
                if d.get("doc_type") not in types:
                    errs["triage"].append(f"{w}: doc_type '{d.get('doc_type')}' is not in registry/ontology/information.yaml")
                if d.get("relevance") not in rels:
                    errs["triage"].append(f"{w}: relevance '{d.get('relevance')}' is not valid")
                if d.get("relevance") in ("core", "supporting"):
                    if not d.get("read_plan"):
                        errs["triage"].append(f"{w}: core/supporting files need a read_plan (pages, sheets, sections)")
                    if d.get("status") != "confirmed":
                        errs["triage"].append(f"{w}: status must be 'confirmed' (agent confirmed the suggestion)")
                    m = manifest.get(d.get("file_id"), {})
                    if m.get("duplicate_of") and "keep" not in str(d.get("reason", "")).lower():
                        errs["triage"].append(f"{w}: exact duplicate of {m['duplicate_of']}; set ignore or give a 'keep' reason")
            budget = onto["budgets"]["max_core_files"]
            bo = t.get("budget_override")
            if bo:
                if not (bo.get("max") and bo.get("reason") and bo.get("feedback_id")):
                    errs["triage"].append("budget_override needs max, reason, and the feedback_id that approved it")
                else:
                    budget = int(bo["max"])
            n_core = sum(1 for d in files if d.get("relevance") == "core")
            if n_core > budget:
                errs["triage"].append(f"{n_core} core files > budget {budget}. Focus: move some to supporting/background, or get a budget_override by feedback")

    reg_p = os.path.join(sdir, "02_evidence", "evidence_register.csv")
    reg = load_register(reg_p)
    ids = {r["evidence_id"] for r in reg} if reg else set()

    # ---- brief
    if only in (None, "brief"):
        bp = os.path.join(sdir, "01_intake", "source_brief.md")
        if not os.path.exists(bp):
            errs["brief"].append("01_intake/source_brief.md missing")
        else:
            text = open(bp, encoding="utf-8").read()
            words = len(re.findall(r"\w+", text))
            mx = onto["budgets"]["source_brief_max_words"]
            if words > mx:
                errs["brief"].append(f"source_brief.md has {words} words > budget {mx}. Keep only what mapping needs")
            cited = set(EID.findall(text))
            if not cited:
                errs["brief"].append("source_brief.md cites no evidence ids (E-0001 ...)")
            missing = sorted(cited - ids)
            if missing:
                errs["brief"].append(f"source_brief.md cites ids not in evidence_register.csv: {missing[:10]}")

    # ---- evidence register
    if only in (None, "evidence"):
        if reg is None:
            errs["evidence"].append("02_evidence/evidence_register.csv missing")
        else:
            with open(reg_p, newline="", encoding="utf-8") as f:
                header = next(csv.reader(f), [])
            miss_cols = [c for c in REG_COLS if c not in header]
            if miss_cols:
                errs["evidence"].append(f"evidence_register.csv missing columns {miss_cols}")
            seen = set()
            mxw = onto["budgets"]["evidence_claim_max_words"]
            conf = set(onto["confidence"])
            stat = set(onto["evidence_status"])
            origins = set(onto["evidence_origins"])
            for r in reg:
                eid = r.get("evidence_id", "")
                w = f"{eid}"
                if not re.fullmatch(r"E-\d{4}", eid or ""):
                    errs["evidence"].append(f"bad evidence_id '{eid}'")
                if eid in seen:
                    errs["evidence"].append(f"{w}: duplicate id")
                seen.add(eid)
                if len(re.findall(r"\w+", r.get("claim", ""))) > mxw:
                    errs["evidence"].append(f"{w}: claim longer than {mxw} words; split it")
                if not r.get("claim"):
                    errs["evidence"].append(f"{w}: empty claim")
                if r.get("about_type") not in ABOUT_TYPES:
                    errs["evidence"].append(f"{w}: about_type must be one of {sorted(ABOUT_TYPES)}")
                if r.get("origin") not in origins:
                    errs["evidence"].append(f"{w}: origin must be one of {sorted(origins)}")
                if r.get("confidence") not in conf:
                    errs["evidence"].append(f"{w}: confidence must be one of {sorted(conf)}")
                if r.get("status") not in stat:
                    errs["evidence"].append(f"{w}: status must be one of {sorted(stat)}")
                if r.get("origin") == "document":
                    fid = r.get("file_id")
                    if fid not in manifest:
                        errs["evidence"].append(f"{w}: file_id '{fid}' is not in the inventory")
                    elif triage and triage.get(fid, {}).get("relevance") in ("ignore", None):
                        errs["evidence"].append(f"{w}: cites {fid}, which triage marks 'ignore'")
                    if not r.get("location"):
                        errs["evidence"].append(f"{w}: document evidence needs a location (page/sheet/section)")
                if r.get("origin") == "bronze_profile" and not str(r.get("location", "")).startswith(("02_evidence/profiling/", "02_evidence/discovery/")):
                    errs["evidence"].append(f"{w}: bronze_profile evidence must point to a 02_evidence/profiling/ or 02_evidence/discovery/ file")
                if r.get("origin") == "team_knowledge" and r.get("confidence") == "high":
                    errs["evidence"].append(f"{w}: team_knowledge evidence is medium at most (high needs client_answer)")
                if r.get("status") in ("corroborated", "confirmed_by_bronze") and not r.get("corroborated_by"):
                    errs["evidence"].append(f"{w}: status '{r.get('status')}' needs corroborated_by")
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source_id")
    ap.add_argument("--only", choices=["triage", "brief", "evidence"])
    a = ap.parse_args(argv)
    errs = check(a.source_id, only=a.only)
    n = 0
    for area, es in errs.items():
        if a.only and area != a.only:
            continue
        print(f"[{area}] {'OK' if not es else f'{len(es)} errors'}")
        for e in es:
            print(f"  ERROR  {e}")
        n += len(es)
    return 0 if n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
