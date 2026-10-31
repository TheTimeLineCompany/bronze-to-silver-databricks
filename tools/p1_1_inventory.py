#!/usr/bin/env python3
"""P1.1 Inventory: list every file in a source's 00_inbox WITHOUT reading content in depth.

The agent must not read a large dump file by file. This script does the cheap,
deterministic part first:
  - one row per file (IF-0001 ...): path, type, size, modified date, hash
  - exact duplicates (same hash)
  - version groups (same name apart from v2 / final / dates / "copy of")
  - Excel: sheet names and used rows/columns; PPTX: slide count; PDF: page count (if libraries exist)
  - a suggested document type and relevance from registry/ontology/information.yaml

Outputs (in sources/<id>/):
  01_intake/manifest.csv    full list (for code and for people)
  01_intake/manifest.md     short summary - THE ONLY inventory file an agent reads first
  01_intake/triage.yaml       a draft triage, created only if it does not exist yet

Usage:
    python tools/p1_1_inventory.py S07_container_moves
    python tools/p1_1_inventory.py S07_container_moves --refresh-triage   # add new files to an existing triage
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {".DS_Store", "Thumbs.db", ".gitkeep"}
VERSION_NOISE = re.compile(
    r"(\b|_)(v\d+(\.\d+)*|ver\d+|final|draft|latest|copy( of)?|backup|old|new|rev\d+|\(\d+\)|"
    r"\d{4}[-_.]?\d{2}[-_.]?\d{2}|\d{2}[-_.]\d{2}[-_.]\d{2,4})(\b|_)", re.I)


def _ontology():
    with open(os.path.join(ROOT, "registry", "ontology", "information.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def _sha1(path, block=1 << 20):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(block)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _group_key(name):
    stem = os.path.splitext(name)[0].lower()
    stem = VERSION_NOISE.sub(" ", stem)
    stem = re.sub(r"[^a-z0-9]+", " ", stem).strip()
    return stem


def _details(path, ext):
    """Cheap structural details only. Never the full content."""
    d = {"sheets": "", "pages": ""}
    try:
        if ext in (".xlsx", ".xlsm"):
            from openpyxl import load_workbook
            wb = load_workbook(path, read_only=True, data_only=True)
            d["sheets"] = "; ".join(f"{ws.title}({ws.max_row}x{ws.max_column})" for ws in wb.worksheets)
            d["pages"] = len(wb.worksheets)
            wb.close()
        elif ext == ".pptx":
            from pptx import Presentation  # optional
            d["pages"] = len(Presentation(path).slides)
        elif ext == ".pdf":
            from pypdf import PdfReader  # optional
            d["pages"] = len(PdfReader(path).pages)
        elif ext == ".docx":
            from docx import Document  # optional
            d["pages"] = f"{len(Document(path).paragraphs)} paragraphs"
        elif ext in (".csv", ".txt", ".sql", ".html", ".htm", ".md", ".json"):
            with open(path, "rb") as f:
                d["pages"] = f"{sum(1 for _ in f)} lines"
    except Exception as e:  # noqa: BLE001  - optional libraries may be missing
        d["pages"] = d["pages"] or f"n/a ({type(e).__name__})"
    return d


EXT_PRIOR = {".xlsx": "profiling_workbook", ".xlsm": "profiling_workbook", ".sql": "schema_ddl",
             ".pptx": "process_deck", ".html": "profiling_html", ".htm": "profiling_html",
             ".csv": "sample_extract", ".msg": "email_or_chat", ".eml": "email_or_chat",
             ".docx": "system_overview", ".pdf": "system_overview", ".txt": "meeting_notes",
             ".png": "unrelated", ".jpg": "unrelated", ".gif": "unrelated"}
STALE = re.compile(r"(^|[/_ \-])(archive|old|backup|draft|superseded|copy of|v0)([/_ \-.]|$)", re.I)


def _hits(signals, text):
    n = 0
    for sig in signals:
        if re.search(r"(?<![a-z0-9])" + re.escape(sig.lower()) + r"s?(?![a-z])", text):
            n += 1
    return n


def _suggest(rel_path, ext, sheets, onto):
    """Score each document type: file name (x3) > folder path (x1) > sheet names (x1, workbooks only) + extension prior."""
    name = os.path.basename(rel_path).lower()
    folder = os.path.dirname(rel_path).lower()
    sheets_l = str(sheets).lower()
    best, best_score = "unrelated", 0.0
    for t, spec in onto["document_types"].items():
        if t == "draft_or_superseded":
            continue
        sig = spec.get("signals", [])
        sc = 3 * _hits(sig, name) + _hits(sig, folder)
        if t == "profiling_workbook" and ext in (".xlsx", ".xlsm"):
            sc += _hits(sig, sheets_l) + (2 if "profil" in name else 0)
        if EXT_PRIOR.get(ext) == t:
            sc += 1.5
        if sc > best_score:
            best, best_score = t, sc
    if STALE.search(rel_path):
        return "draft_or_superseded"
    return best


def _stale_rank(r):
    """Lower is better: prefer files not in archive/draft paths, higher version numbers, newer dates."""
    stale = 1 if STALE.search(r["path"]) else 0
    m = re.findall(r"v(\d+)", r["name"].lower())
    ver = max(int(x) for x in m) if m else 0
    final = 1 if "final" in r["name"].lower() else 0
    return (stale, -final, -ver, tuple(-ord(c) for c in r["modified"]))


def build(source_id, refresh_triage=False):
    sdir = os.path.join(ROOT, "sources", source_id)
    inbox = os.path.join(sdir, "00_inbox")
    if not os.path.isdir(inbox):
        raise SystemExit(f"no inbox: {inbox}")
    onto = _ontology()
    rows = []
    for dp, dns, fns in os.walk(inbox):
        dns.sort()
        for fn in sorted(fns):
            if fn in SKIP or fn.startswith("~$"):
                continue
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, sdir)
            ext = os.path.splitext(fn)[1].lower()
            st = os.stat(p)
            det = _details(p, ext)
            rows.append({"file_id": "", "path": rel, "folder": os.path.relpath(dp, sdir), "name": fn, "ext": ext,
                         "size_kb": round(st.st_size / 1024, 1),
                         "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%d"),
                         "sha1": _sha1(p), "sheets": det["sheets"], "pages": det["pages"],
                         "group": _group_key(fn), "duplicate_of": "", "latest_in_group": "",
                         "suggested_type": "", "suggested_relevance": ""})
    for i, r in enumerate(rows, 1):
        r["file_id"] = f"IF-{i:04d}"
    first_by_hash = {}
    for r in rows:
        if r["sha1"] in first_by_hash:
            r["duplicate_of"] = first_by_hash[r["sha1"]]
        else:
            first_by_hash[r["sha1"]] = r["file_id"]
    groups = defaultdict(list)
    for r in rows:
        if not r["duplicate_of"]:
            groups[(r["ext"], r["group"])].append(r)
    for g in groups.values():
        latest = min(g, key=_stale_rank)
        for r in g:
            r["latest_in_group"] = "yes" if r is latest else f"no (latest: {latest['file_id']})"
    for r in rows:
        t = _suggest(r["path"], r["ext"], r["sheets"], onto)
        rel = onto["document_types"][t]["default_relevance"]
        if r["duplicate_of"] or r["latest_in_group"].startswith("no"):
            t, rel = ("draft_or_superseded", "ignore")
        r["suggested_type"], r["suggested_relevance"] = t, rel

    inv_dir = os.path.join(sdir, "01_intake")
    os.makedirs(inv_dir, exist_ok=True)
    with open(os.path.join(inv_dir, "manifest.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["file_id"])
        w.writeheader()
        w.writerows(rows)
    _write_summary(source_id, rows, os.path.join(inv_dir, "manifest.md"))
    _write_triage(source_id, rows, os.path.join(sdir, "01_intake", "triage.yaml"), refresh_triage)
    return rows


def _write_summary(source_id, rows, path):
    by_type = Counter(r["suggested_type"] for r in rows)
    by_rel = Counter(r["suggested_relevance"] for r in rows)
    by_folder = Counter(r["folder"] for r in rows)
    dups = sum(1 for r in rows if r["duplicate_of"])
    old = sum(1 for r in rows if r["latest_in_group"].startswith("no"))
    total_mb = sum(r["size_kb"] for r in rows) / 1024
    md = [f"# Inventory summary: {source_id}", "",
          f"- Files: **{len(rows)}** ({total_mb:.1f} MB). Exact duplicates: **{dups}**. Older versions: **{old}**.",
          f"- Suggested relevance: " + ", ".join(f"{k} {v}" for k, v in by_rel.most_common()),
          "", "## By suggested document type", "| type | files |", "|---|---|"]
    md += [f"| {k} | {v} |" for k, v in by_type.most_common()]
    md += ["", "## Top folders", "| folder | files |", "|---|---|"]
    md += [f"| {k} | {v} |" for k, v in by_folder.most_common(15)]
    md += ["", "## Candidate core and supporting files (latest versions only)",
           "| id | path | type | relevance | size KB | sheets / pages |", "|---|---|---|---|---|---|"]
    for r in rows:
        if r["suggested_relevance"] in ("core", "supporting"):
            md.append(f"| {r['file_id']} | {r['path']} | {r['suggested_type']} | {r['suggested_relevance']} | "
                      f"{r['size_kb']} | {str(r['sheets'] or r['pages'])[:80]} |")
    md += ["", "Read this summary first. Do not open files that are background or ignore."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")


def _write_triage(source_id, rows, path, refresh):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing = {}
    if os.path.exists(path):
        if not refresh:
            return
        with open(path, encoding="utf-8") as f:
            existing = {d["file_id"]: d for d in (yaml.safe_load(f) or {}).get("files", [])}
    files = []
    for r in rows:
        if r["file_id"] in existing:
            files.append(existing[r["file_id"]])
            continue
        files.append({"file_id": r["file_id"], "path": r["path"], "doc_type": r["suggested_type"],
                      "relevance": r["suggested_relevance"], "status": "suggested",
                      "reason": "duplicate or older version" if r["suggested_relevance"] == "ignore" and r["suggested_type"] == "draft_or_superseded" else "suggested by inventory signals",
                      "read_plan": None})
    doc = {"source_id": source_id, "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "budget_override": None, "files": files}
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Triage for this source. The agent (skill p1-2-triage) confirms each line; a person approves at CP1.\n"
                "# relevance: core | supporting | background | ignore.  status: suggested | confirmed\n"
                "# read_plan: which pages/sheets/sections to read (required for core and supporting).\n")
        yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source_id")
    ap.add_argument("--refresh-triage", action="store_true")
    a = ap.parse_args(argv)
    rows = build(a.source_id, a.refresh_triage)
    print(f"{a.source_id}: {len(rows)} files inventoried -> 01_intake/manifest.csv, manifest.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
