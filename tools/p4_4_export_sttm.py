#!/usr/bin/env python3
"""P4.4 Generate the human handoff files from an STTM YAML.

Writes, next to the STTM (sources/<id>/04_mapping/):
    exports/sttm.xlsx   one sheet per target table + a Summary and a Keys sheet
    exports/er.mmd      Mermaid ER diagram (this source's tables + linked shared masters)

Never edit these files by hand. Change 04_mapping/sttm.yaml and run this again.

Usage:
    python tools/p4_4_export_sttm.py sources/S07_container_moves/04_mapping/sttm.yaml
"""
from __future__ import annotations

import os
import sys

import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEAD = Font(bold=True, color="FFFFFF")
FILL = PatternFill("solid", fgColor="0B6E6E")
COLS = ["target", "business_rule", "evidence", "type", "nullable", "key_role", "rule", "source", "transform", "key_rule",
        "fk_target", "fk_column", "fk_lookup_on", "fk_cardinality", "orphan_policy", "dq", "business_logic",
        "description", "provenance_doc", "provenance_ref", "provenance_profiling", "confidence", "open_question"]


def _row(c):
    fk = c.get("fk") or {}
    p = c.get("provenance") or {}
    return [c.get("target"), c.get("business_rule"), ", ".join(p.get("evidence") or []), c.get("type"), c.get("nullable"), c.get("key_role"), c.get("rule"),
            c.get("source"), c.get("transform"), c.get("key_rule"),
            (f"entity {fk['entity']}" if fk.get("entity") else f"table {fk['table']}" if fk.get("table") else None), fk.get("column"),
            " | ".join((x if isinstance(x, str) else f"{x.get('expr')} [{x.get('key_rule')}]") for x in (fk.get("lookup_on") or [])) or None,
            fk.get("cardinality"), fk.get("orphan_policy"), ", ".join(c.get("dq") or []),
            bool(c.get("business_logic")), c.get("description"), p.get("doc"), p.get("ref"),
            p.get("profiling"), c.get("confidence"), c.get("open_question")]


def _header(ws, cols):
    ws.append(cols)
    for i in range(1, len(cols) + 1):
        cell = ws.cell(row=1, column=i)
        cell.font, cell.fill = HEAD, FILL
    ws.freeze_panes = "A2"


def write_xlsx(doc, path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    _header(ws, ["field", "value"])
    for k in ("source_id", "source_system", "version", "status", "owner", "notes"):
        ws.append([k, doc.get(k)])
    ks = wb.create_sheet("Keys")
    _header(ks, ["target_table", "business_object", "data_class", "kind", "conformed_entity", "grain", "load_pattern", "scd_type",
                 "primary_key", "business_key", "surrogate_key", "sources", "joins"])
    for t in doc["tables"]:
        sk = t.get("surrogate_key") or {}
        ks.append([t["target_table"], t.get("business_object"), t.get("data_class"), t["target_kind"], t.get("conformed_entity"), t["grain"],
                   t["load_pattern"], t.get("scd_type"), ", ".join(t["primary_key"]),
                   ", ".join(t["business_key"]),
                   f"{sk.get('column')} = {sk.get('method')}({', '.join(sk.get('of', []))})" if sk else None,
                   "; ".join(f"{s['table']} AS {s['alias']}" + (f" WHERE {s['filter']}" if s.get('filter') else "") for s in t["sources"]),
                   "; ".join(f"{j['left']} {j['type'].upper()} JOIN {j['right']} ON {j['condition']} [{j['cardinality']}]" for j in (t.get("joins") or []))])
        sheet = wb.create_sheet(t["target_table"][:31])
        _header(sheet, COLS)
        for c in t["columns"]:
            sheet.append(_row(c))
    for sheet in wb.worksheets:
        for i, col in enumerate(sheet.columns, start=1):
            width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
            sheet.column_dimensions[get_column_letter(i)].width = min(max(10, width + 2), 60)
            for c in col:
                c.alignment = Alignment(wrap_text=True, vertical="top")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb.save(path)


def write_mermaid(doc, path, root=ROOT):
    ents = {e["name"]: e for e in yaml.safe_load(open(os.path.join(root, "registry/entities.yaml"), encoding="utf-8"))["entities"]}
    lines = ["erDiagram"]
    linked = set()
    for t in doc["tables"]:
        lines.append(f"  {t['target_table']} {{")
        for c in t["columns"]:
            role = {"PK": " PK", "FK": " FK", "PK_FK": " PK,FK", "BK": " UK"}.get(c["key_role"], "")
            lines.append(f"    {c['type'].split('(')[0].lower()} {c['target']}{role}")
        lines.append("  }")
        for c in t["columns"]:
            fk = c.get("fk")
            if fk and fk.get("table"):
                rel = "}o--||" if fk["cardinality"] == "N:1" else "||--||"
                lines.append(f"  {t['target_table']} {rel} {fk['table']} : \"{c['target']}\"")
            if fk and fk.get("entity") in ents:
                e = ents[fk["entity"]]
                linked.add(fk["entity"])
                rel = "}o--||" if fk["cardinality"] == "N:1" else "||--||"
                lines.append(f"  {t['target_table']} {rel} {e['target_table']} : \"{c['target']}\"")
    for name in sorted(linked):
        e = ents[name]
        lines.append(f"  {e['target_table']} {{")
        lines.append(f"    string {e['surrogate_key']} PK")
        for bk in e["business_key"]:
            lines.append(f"    string {bk} UK")
        lines.append("  }")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    src = argv[0]
    with open(src, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    out = os.path.join(os.path.dirname(os.path.abspath(src)), "exports")
    write_xlsx(doc, os.path.join(out, "sttm.xlsx"))
    write_mermaid(doc, os.path.join(out, "er.mmd"))
    print(f"wrote {out}/sttm.xlsx and {out}/er.mmd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
