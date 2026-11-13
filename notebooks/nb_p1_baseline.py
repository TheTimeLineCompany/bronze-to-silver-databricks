# Databricks notebook source
# MAGIC %md
# MAGIC # P1 Bronze baseline (S0 inventory, S1 column profile, S2 grain and keys, S5 report)
# MAGIC Profiles the bronze tables of one application, finds keys, copies and empty tables, and writes open points.
# MAGIC **A person runs this notebook** (Run all, or cell by cell). Genie Code reads only `baseline/summary.vNNN.json`.
# MAGIC
# MAGIC * Values of sensitive columns are removed **before** anything is written (R-01).
# MAGIC * The run stops after the time budget (default 25 minutes) and resumes on the next run; unchanged tables are skipped.
# MAGIC * Set `fresh_run = yes` only after a framework fix; it is cleared after this run.

# COMMAND ----------

dbutils.widgets.text("project_root", "", "Project folder")
dbutils.widgets.dropdown("run_by", "genie", ["genie", "person"], "Run by (Genie Code orchestrates by default)")
dbutils.widgets.text("app", "", "Application id (S01_name)")
dbutils.widgets.dropdown("fresh_run", "no", ["no", "yes"], "Fresh run (one run only)")
dbutils.widgets.text("fresh_reason", "", "Reason for a fresh run")
dbutils.widgets.text("catalog", "", "Catalog (empty = current)")
dbutils.widgets.text("profiler_run", "", "Profiler plug-in run (plan.json path; empty = core profiler)")

# COMMAND ----------

# Setup: framework on the path, identity from the workspace (never typed), libraries check, project state.
import os, sys
FRAMEWORK = os.path.abspath("..")          # notebooks/ sits inside the framework folder; the working dir is the notebook's
sys.path.insert(0, FRAMEWORK)
try:
    os.environ["B2S_USER"] = spark.sql("SELECT current_user() u").collect()[0]["u"]
except Exception:
    pass
os.environ["B2S_VIA"] = "notebook"
os.environ["B2S_RUN_BY"] = dbutils.widgets.get("run_by")   # recorded in every event (audit)
for lib in ("yaml", "openpyxl"):
    __import__(lib)            # set libraries in the serverless environment of this notebook (DB-04), not %pip
from b2s import FRAMEWORK_VERSION
from b2s.project import open_project, app_config
from b2s.store import acquire_lease
from b2s.baseline import run, SparkReader
layout = open_project(dbutils.widgets.get("project_root"))
APP = dbutils.widgets.get("app")
lease = acquire_lease(layout, APP)
print("framework", FRAMEWORK_VERSION, "| user", os.environ.get("B2S_USER"), "| lease until", lease["expires"])
print(app_config(layout, APP))

# COMMAND ----------

# MAGIC %md ## 1. Run the baseline

# COMMAND ----------

fresh = dbutils.widgets.get("fresh_run") == "yes"
if fresh and not dbutils.widgets.get("fresh_reason").strip():
    raise ValueError("fresh_run needs a reason (it is logged)")
reader = SparkReader(spark, catalog=dbutils.widgets.get("catalog") or None)
ext, info = None, None
if dbutils.widgets.get("profiler_run").strip():        # the client profiler notebook ran first (integrated plug-in)
    import json
    from b2s import plugins
    plan = json.load(open(dbutils.widgets.get("profiler_run").strip()))
    ext, info = plugins.collect(layout, APP, plan), {"name": plan["plugin"], "version": plan["version"]}
summary = run(layout, APP, reader, fresh=fresh, external_profiles=ext, external_info=info)
if fresh:                         # 'fresh' is a one-run flag (DC-07): reset it to "no" after the run
    dbutils.widgets.remove("fresh_run")
    dbutils.widgets.dropdown("fresh_run", "no", ["no", "yes"], "Fresh run (one run only)")
print(summary["_version"], "partial:", summary["partial"], "| remaining:", len(summary["remaining"]))
for e in summary["tables"]:
    print(f'{e["table"]:40} {e["key_result"]:22} {e["key"]} {"copy of " + e["copy_of"] if e["copy_of"] else ""}')

# COMMAND ----------

# MAGIC %md
# MAGIC **Result:** fill in from the output above — tables profiled, how many have a key, open points, and whether
# MAGIC the run is partial (run again to continue).

# COMMAND ----------

# Check by a different method: read the saved files back from disk and recount, instead of trusting `summary`.
import json
from b2s import versions
sv = versions.latest(layout.stem(APP, "baseline/summary"), "json")
saved = json.loads(sv.path.read_text())
assert versions.verify(sv), "summary file changed after it was written"
n_files = sum(1 for t in saved["tables"] if versions.latest(layout.stem(APP, f"baseline/tables/{t['table']}"), "json"))
assert n_files == len(saved["tables"]), "a table file is missing"
print("check OK:", sv.label, n_files, "table files,", len(saved["open_points"]), "open points")

# COMMAND ----------

# MAGIC %md ## 2. Privacy check

# COMMAND ----------

# Different method: scan the written table files for any value of a column classed as sensitive.
bad = []
for t in saved["tables"]:
    prof = json.loads(versions.latest(layout.stem(APP, f"baseline/tables/{t['table']}"), "json").path.read_text())
    for c in prof["columns"]:
        if c.get("redacted") and (c.get("min") is not None or c.get("max") is not None or c.get("topk")):
            bad.append((t["table"], c["column"]))
assert not bad, f"values of sensitive columns were written: {bad}"
print("privacy check OK")

# COMMAND ----------

# MAGIC %md
# MAGIC **Result:** privacy check passed (no value of a sensitive column in any file).
# MAGIC Next: ask Genie Code for checkpoint **CP1** (bronze baseline) in the chat (`@x-approve`), or continue with P2.

# COMMAND ----------

from b2s.store import release_lease
release_lease(layout, APP)
