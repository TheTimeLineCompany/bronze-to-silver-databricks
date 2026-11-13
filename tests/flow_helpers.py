"""Builds an application up to P5 with a synthetic baseline (independent of the P2 engine)."""
import copy

from b2s import items, versions
from b2s.project import register_app
from b2s.steps import save_output
from fixtures_models import ALL

APP = "S90_yardops"


def _col(name, family="str", cls="business_attribute", use="map"):
    return {"column": name, "family": family, "column_class": cls, "use": use}


TABLES = {
    "yard.cntr_mst": {"key": ["cntr_no"], "row_count": 50, "columns": [
        _col("cntr_no", cls="key"), _col("iso_type"), _col("owner_cd"),
        _col("created_by", cls="audit_metadata", use="technical_only")]},
    "yard.mv_plan": {"key": ["plan_id"], "row_count": 40, "columns": [
        _col("plan_id", cls="key"), _col("plan_status")]},
    "yard.mv_leg": {"key": ["plan_id", "leg_no"], "row_count": 120, "columns": [
        _col("plan_id", cls="key"), _col("leg_no", "int", "key"), _col("cntr_no", cls="foreign_key"),
        _col("moved_at", "date", "business_date"), _col("xq_flg")]},
    "yard.mv_leg_bkp": {"key": ["plan_id", "leg_no"], "row_count": 120, "copy_of": "yard.mv_leg", "columns": [
        _col("plan_id", cls="key"), _col("leg_no", "int", "key")]},
    "yard.usr_session": {"key": ["session_id"], "row_count": 900, "columns": [
        _col("session_id", cls="application_log", use="out_of_scope"), _col("user_ip", cls="application_log", use="out_of_scope"),
        _col("user_agent", cls="application_log", use="out_of_scope")]},
    "yard.contact": {"key": ["contact_id"], "row_count": 30, "columns": [
        _col("contact_id", cls="key"), _col("contact_name", cls="personal_data", use="review"),
        _col("email", cls="personal_data", use="review")]},
}


def write_baseline(layout, app=APP, tables=TABLES):
    entries = []
    for name, t in tables.items():
        v = versions.save(layout, layout.stem(app, f"baseline/tables/{name}"), "json",
                          {"table": name, "row_count": t["row_count"], "columns": t["columns"]}, reason="test", app=app)
        entries.append({"table": name, "row_count": t["row_count"], "n_columns": len(t["columns"]), "key": t["key"],
                        "key_result": "key", "copy_of": t.get("copy_of"), "empty": False, "version": v.tag})
    return save_output(layout, app, "baseline/summary", {"app": app, "tables": entries, "partial": False}, reason="test")


def build_to_p5(layout, app=APP):
    register_app(layout, app, "Yard operations", ["yard"], ["yardlkp"], bronze={"connector": "local"})
    for i in range(5):
        items.create(layout, app, "assumption", {"statement": f"assumption {i + 1}"}, via="genie")
    for i in range(4):
        items.create(layout, app, "question", {"text": f"question {i + 1}?"}, via="genie")
    write_baseline(layout, app)
    save_output(layout, app, "understanding/app_brief", "# Yard operations\nPlans and executes container moves.\n",
                reason="first", via="genie")
    deps = copy.deepcopy(ALL["dependencies"])
    deps["app"] = app
    save_output(layout, app, "models/dependencies", deps, reason="first", via="genie")
    save_output(layout, app, "models/process", ALL["process"], reason="first", via="genie")
    save_output(layout, app, "models/conceptual", ALL["conceptual"], reason="first", via="genie")
