# Databricks notebook source
# MAGIC %md
# MAGIC # P5.2 QA on the dev silver schema
# MAGIC Runs every check of `standards/qa_checklist.md` (functions in `lib/qa_checks.py`) on the tables in the QA plan
# MAGIC (`python -m b2s qa-plan <app>`) and saves `qa/results.vNNN.json`. CP5 reads the results.
# MAGIC
# MAGIC * Genie Code runs this notebook (cell by cell or Run all) after the generated notebooks and the master builds ran.
# MAGIC * It reads only the DEV silver schema named in the plan. It never writes to silver.

# COMMAND ----------

dbutils.widgets.text("project_root", "", "Project folder")
dbutils.widgets.text("app", "", "Application id (S01_name)")
dbutils.widgets.dropdown("run_by", "genie", ["genie", "person"], "Run by")

# COMMAND ----------

# Setup: framework on the path, identity from the workspace (never typed), project state.
import os, sys
sys.dont_write_bytecode = True          # no __pycache__ in /Workspace
FRAMEWORK = os.path.abspath("..")
sys.path.insert(0, FRAMEWORK)
os.environ["B2S_VIA"] = "genie" if dbutils.widgets.get("run_by") == "genie" else "notebook"
for lib_name in ("yaml",):
    __import__(lib_name)          # libraries come from the serverless environment of this notebook (DB-04)
from b2s import FRAMEWORK_VERSION, versions
from b2s.project import open_project
from b2s.build import record_results
layout = open_project((dbutils.widgets.get("project_root").strip() or os.environ.get("B2S_PROJECT", "")))
APP = dbutils.widgets.get("app")
os.environ["B2S_REGISTRY_DIR"] = os.path.join(str(layout.root), "_project")
from lib import qa_checks as qa
plan_v = versions.latest(layout.stem(APP, "qa/plan"), "json")
assert plan_v, "no QA plan: run python -m b2s qa-plan <app> first"
PLAN = versions.read(plan_v)
print("framework", FRAMEWORK_VERSION, "| user", os.environ.get("B2S_USER"), "|", plan_v.label, "|", len(PLAN["tables"]), "tables")

# COMMAND ----------

# MAGIC %md ## 1. Run the checks

# COMMAND ----------

prefix = PLAN["silver_prefix"]
cat, sch = prefix.split(".")
ENTITY_TABLES = qa.entity_tables(cat, sch, str(layout.root))
results = []
for e in PLAN["tables"]:
    expected = None
    try:
        props = {r["key"]: r["value"] for r in spark.sql(f"SHOW TBLPROPERTIES {e['fqn']}").collect()}
        expected = int(props["b2s.expected_rows"]) if "b2s.expected_rows" in props else None
    except Exception as ex:      # table missing: the checks below report it as an error
        print("properties not readable for", e["fqn"], ex)
    results += qa.run_table_checks(spark, e["spec"], e["fqn"], bronze_count=expected,
                                   entity_tables=ENTITY_TABLES, silver_prefix=prefix)
rv = record_results(layout, APP, results)
for r in results:
    print(f'{r["status"]:6} {r["check"]:32} {r["table"]}')

# COMMAND ----------

# MAGIC %md **Result:** fill in from the output above — saved results version, number of checks, number not passing.

# COMMAND ----------

# Check by a different method: read the saved results file back and compare counts with the run.
saved = versions.read(versions.latest(layout.stem(APP, "qa/results"), "json"))
assert len(saved["results"]) == len(results), "saved results differ from this run"
print(rv.label, "| checks", len(results), "| not passing", sum(r["status"] != "pass" for r in results),
      "| all_passed", saved["all_passed"])

# COMMAND ----------

# MAGIC %md
# MAGIC Next: P5.3 code review in a new chat (`@p5-3-code-review`), then `python -m b2s cp-auto <app> CP5`.

# COMMAND ----------

# Status (one short JSON line for Genie Code; feedback I-17 §4)
import json as _json
_status = {"notebook": 'nb_p5_qa', "app": globals().get("APP"), "ok": True}
for _k in ("summary", "res", "results", "req"):
    if isinstance(globals().get(_k), dict):
        _status.update({k: v for k, v in globals()[_k].items() if k in ("partial", "_version", "remaining_count", "id", "passed", "failed")})
print("B2S_STATUS " + _json.dumps(_status, default=str)[:2000])
