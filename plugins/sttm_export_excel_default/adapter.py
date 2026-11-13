"""Slot sttm_export_excel: export(sttm: dict, out_path: str) -> None"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

HEAD = Font(bold=True, color="FFFFFF")
FILL = PatternFill("solid", fgColor="1F2937")


def _sheet(wb, title, header, rows):
    ws = wb.create_sheet(title)
    ws.append(header)
    for c in ws[1]:
        c.font, c.fill = HEAD, FILL
    for r in rows:
        ws.append(r)
    ws.freeze_panes = "A2"
    for i, h in enumerate(header, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = max(12, min(48, len(h) + 4))


def export(sttm: dict, out_path: str) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    _sheet(wb, "Tables", ["target_table", "business_object", "data_class", "grain", "primary_key", "business_key", "sources"],
           [[t["target_table"], t.get("business_object"), t.get("data_class"), t.get("grain"),
             ", ".join(t.get("primary_key") or []), ", ".join(t.get("business_key") or []), ", ".join(t.get("sources") or [])]
            for t in sttm["tables"]])
    rows, open_rows = [], []
    for t in sttm["tables"]:
        for c in t["columns"]:
            src = c.get("source") or {}
            rows.append([t["target_table"], c["target_column"], c.get("type"), c.get("rule"), src.get("table"),
                         ", ".join(src.get("columns") or []), ", ".join((c.get("fk") or {}).get("lookup_on") or []),
                         (c.get("fk") or {}).get("table"), (c.get("privacy") or {}).get("handling"), c.get("status", "known"),
                         c.get("assumption") or c.get("question") or ""])
            if c.get("status", "known") != "known":
                open_rows.append([t["target_table"], c["target_column"], c.get("status"), c.get("assumption") or c.get("question")])
    _sheet(wb, "Mapping", ["target_table", "target_column", "type", "rule", "source_table", "source_columns", "fk_lookup_on",
                           "fk_table", "privacy_handling", "status", "assumption_or_question"], rows)
    _sheet(wb, "Open items", ["target_table", "target_column", "status", "item"], open_rows)
    wb.save(out_path)
