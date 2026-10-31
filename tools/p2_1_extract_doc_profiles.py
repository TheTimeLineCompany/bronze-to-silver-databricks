#!/usr/bin/env python3
"""P2.1 Extract client profiling workbooks into ONE normalised table.

The client's profiled Excel files have different layouts and their own confidence
labels (high / medium / low, percentages, colours in words, etc.). The agent should
not read every sheet. This script reads only workbooks that triage marks as
doc_type 'profiling_workbook' or 'data_dictionary' (Excel) with relevance core or supporting, finds the header row,
maps column names by synonyms, and normalises confidence to high/medium/low/unknown.

Output (sources/<id>/02_evidence/profiling/):
  doc_profiles.csv          one row per (table, column) claim: DP-00001 ...
  doc_profiles_summary.md   counts per table and confidence; unmapped sheets listed

Usage:
    python tools/p2_1_extract_doc_profiles.py S07_container_moves
    python tools/p2_1_extract_doc_profiles.py S07_container_moves --file IF-0004   # one workbook

Add synonyms below when a client workbook uses other header names (or give them by feedback).
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SYNONYMS = {
    "table":        ["table", "table name", "tablename", "entity", "object", "source table"],
    "column":       ["column", "column name", "field", "field name", "attribute", "columnname"],
    "data_type":    ["data type", "datatype", "type", "format"],
    "null_pct":     ["null %", "null pct", "% null", "null percent", "nulls %", "null ratio", "null rate"],
    "distinct":     ["distinct", "distinct count", "unique values", "cardinality", "# distinct"],
    "pk_candidate": ["pk", "primary key", "key", "pk candidate", "is key", "unique"],
    "description":  ["description", "definition", "meaning", "business description", "comment"],
    "sample":       ["sample", "sample values", "example", "examples"],
    "confidence":   ["confidence", "confidence level", "certainty", "quality", "conf", "score", "match confidence"],
    "comment":      ["notes", "remarks", "observation", "finding"],
}
WORDS = {"high": "high", "h": "high", "strong": "high", "confirmed": "high", "green": "high",
         "medium": "medium", "med": "medium", "m": "medium", "moderate": "medium", "amber": "medium", "yellow": "medium",
         "low": "low", "l": "low", "weak": "low", "red": "low", "tentative": "low", "assumed": "low"}


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower().replace("_", " "))


def norm_confidence(raw):
    if raw is None or str(raw).strip() == "":
        return "unknown"
    s = _norm(raw)
    if s in WORDS:
        return WORDS[s]
    m = re.match(r"^(\d+(\.\d+)?)\s*%?$", s)
    if m:
        v = float(m.group(1))
        v = v / 100.0 if v > 1 else v
        return "high" if v >= 0.8 else "medium" if v >= 0.5 else "low"
    for k, v in WORDS.items():
        if len(k) > 1 and k in s:
            return v
    return "unknown"


def _map_header(cells):
    mapping = {}
    for i, c in enumerate(cells):
        n = _norm(c)
        if not n:
            continue
        for field, syns in SYNONYMS.items():
            if field not in mapping and n in syns:
                mapping[field] = i
    return mapping


def extract(source_id, only_file=None, root=ROOT):
    from openpyxl import load_workbook
    sdir = os.path.join(root, "sources", source_id)
    with open(os.path.join(sdir, "01_intake", "triage.yaml"), encoding="utf-8") as f:
        triage = yaml.safe_load(f)
    targets = [d for d in triage["files"] if d.get("doc_type") in ("profiling_workbook", "data_dictionary")
               and str(d.get("path", "")).lower().endswith((".xlsx", ".xlsm"))
               and d.get("relevance") in ("core", "supporting") and (not only_file or d["file_id"] == only_file)]
    out, unmapped = [], []
    for d in targets:
        path = os.path.join(sdir, d["path"])
        try:
            wb = load_workbook(path, read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001
            unmapped.append((d["file_id"], "*", f"cannot open: {e}"))
            continue
        sheets_allowed = None
        rp = d.get("read_plan") or {}
        if isinstance(rp, dict) and rp.get("sheets"):
            sheets_allowed = set(rp["sheets"])
        for ws in wb.worksheets:
            if sheets_allowed and ws.title not in sheets_allowed:
                continue
            rows = list(ws.iter_rows(values_only=True))
            hdr_i, mp = None, {}
            for i, r in enumerate(rows[:15]):
                m = _map_header(r)
                if "column" in m and len(m) >= 2:
                    hdr_i, mp = i, m
                    break
            if hdr_i is None:
                unmapped.append((d["file_id"], ws.title, "no header row with a column-name field"))
                continue
            for j, r in enumerate(rows[hdr_i + 1:], start=hdr_i + 2):
                def g(k):
                    return r[mp[k]] if k in mp and mp[k] < len(r) else None
                col = g("column")
                if col is None or str(col).strip() == "":
                    continue
                table = g("table") or ws.title
                out.append({"profile_id": "", "file_id": d["file_id"], "file": d["path"], "sheet": ws.title, "row": j,
                            "table": str(table).strip(), "column": str(col).strip(),
                            "data_type": g("data_type"), "null_pct": g("null_pct"), "distinct": g("distinct"),
                            "pk_candidate": g("pk_candidate"), "description": g("description"), "sample": g("sample"),
                            "raw_confidence": g("confidence"), "confidence": norm_confidence(g("confidence")),
                            "comment": g("comment")})
        wb.close()
    for i, r in enumerate(out, 1):
        r["profile_id"] = f"DP-{i:05d}"
    pdir = os.path.join(sdir, "02_evidence", "profiling")
    os.makedirs(pdir, exist_ok=True)
    fields = ["profile_id", "file_id", "file", "sheet", "row", "table", "column", "data_type", "null_pct", "distinct",
              "pk_candidate", "description", "sample", "raw_confidence", "confidence", "comment"]
    with open(os.path.join(pdir, "doc_profiles.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    per = defaultdict(Counter)
    for r in out:
        per[r["table"]][r["confidence"]] += 1
    md = [f"# Client profiling extract: {source_id}", "",
          f"Workbooks read: {len(targets)}. Rows extracted: {len(out)}.", "",
          "| table | columns | high | medium | low | unknown |", "|---|---|---|---|---|---|"]
    for t in sorted(per):
        c = per[t]
        md.append(f"| {t} | {sum(c.values())} | {c['high']} | {c['medium']} | {c['low']} | {c['unknown']} |")
    if unmapped:
        md += ["", "## Sheets not extracted (check by hand or add synonyms)", "| file | sheet | reason |", "|---|---|---|"]
        md += [f"| {a} | {b} | {c} |" for a, b, c in unmapped]
    md += ["", "Confidence rules: registry/ontology/information.yaml (confidence). Low and unknown are hypotheses until bronze confirms them."]
    with open(os.path.join(pdir, "doc_profiles_summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    return out, unmapped


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source_id")
    ap.add_argument("--file")
    a = ap.parse_args(argv)
    out, unmapped = extract(a.source_id, a.file)
    print(f"{len(out)} profile rows; {len(unmapped)} sheets not extracted -> 02_evidence/profiling/doc_profiles.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
