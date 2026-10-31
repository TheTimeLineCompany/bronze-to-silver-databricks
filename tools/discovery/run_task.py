# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze discovery task runner (P2.2)
# MAGIC One notebook for every code task of `tools/p2_2_discover.py`. The job (`02_evidence/discovery/job.json`)
# MAGIC calls it with `stage` (+ `table` or `batch`). Read-only on bronze. Writes part files in the repo folder.

# COMMAND ----------
import glob, json, os, sys
dbutils.widgets.text("source_id", "")
dbutils.widgets.text("stage", "")
dbutils.widgets.text("table", "")
dbutils.widgets.text("batch", "")
dbutils.widgets.text("repo_path", "")
repo = dbutils.widgets.get("repo_path") or os.path.abspath("../..")
sys.path.insert(0, os.path.join(repo, "tools"))
import p2_2_discover as disc

sid, stage = dbutils.widgets.get("source_id"), dbutils.widgets.get("stage")

# COMMAND ----------
if stage == "emit-tables":          # feeds the for_each task
    tabs = [r["table"] for r in disc._catalog(sid, repo)]
    dbutils.jobs.taskValues.set("tables", tabs)
elif stage == "plan-links":
    batches = disc.st_plan_links(spark, sid, repo)
    dbutils.jobs.taskValues.set("batches", list(range(len(batches))))
else:
    disc.run(spark, sid, stage, dbutils.widgets.get("table") or None, dbutils.widgets.get("batch") or None, repo)
