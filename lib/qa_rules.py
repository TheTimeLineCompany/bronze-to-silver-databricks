"""Which QA checks apply to which silver table. Pure Python (no Spark): used by the notebooks
(lib/qa_checks.py) AND by the checkpoint check (tools/x_validate_gate.py), so both agree.

Rule: every ID in standards/qa_checklist.md is REQUIRED for every table, unless APPLIES_IF below says
it does not apply. A client check added to the checklist is therefore required by default.
"""
from __future__ import annotations

import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

APPLIES_IF = {
    "QA-05": lambda t: any(c.get("key_role") in ("FK", "PK_FK") for c in t["columns"]),   # foreign keys exist
    "QA-06": lambda t: t.get("load_pattern") == "scd2",                                     # SCD2 tables only
    "QA-07": lambda t: any(c.get("rule") == "normalised_key" for c in t["columns"]),        # normalised keys exist
}


def checklist_ids(root: str | None = None) -> list:
    path = os.path.join(root or _ROOT, "standards", "qa_checklist.md")
    with open(path, encoding="utf-8") as f:
        return sorted(set(re.findall(r"^\|\s*(QA-\d+)\s*\|", f.read(), re.M)))


def required_checks(sttm_table: dict, root: str | None = None) -> list:
    return [i for i in checklist_ids(root) if APPLIES_IF.get(i, lambda t: True)(sttm_table)]


def check_id(result: dict) -> str | None:
    m = re.match(r"(QA-\d+)", str(result.get("check", "")))
    return m.group(1) if m else None


def expected_results(sttm_doc: dict) -> list:
    """(result table name, spec) pairs that a source's QA summary must cover.
    Shared masters are checked on the source's staging table (lib/survivorship.py)."""
    from lib.survivorship import staging_spec, staging_table
    out = []
    for t in sttm_doc.get("tables", []):
        if t.get("target_kind") == "master":
            out.append((staging_table(t["target_table"], sttm_doc["source_id"]), staging_spec(t)))
        else:
            out.append((t["target_table"], t))
    return out


def coverage(sttm_doc: dict, results: list, root: str | None = None, pairs: list | None = None) -> dict:
    """Per expected table: required checks, missing checks, and checks not passing."""
    out = {}
    for name, t in (pairs if pairs is not None else expected_results(sttm_doc)):
        mine = [r for r in results if str(r.get("table") or "").split(".")[-1] == name]
        req = required_checks(t, root)
        got = {check_id(r) for r in mine}
        out[name] = {"required": req, "missing": [i for i in req if i not in got],
                     "not_passing": sorted({f"{check_id(r)}={r.get('status')}" for r in mine if r.get("status") != "pass"})}
    return out
