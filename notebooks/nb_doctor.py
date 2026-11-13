# Databricks notebook source
# MAGIC %md
# MAGIC # Doctor — workspace checks before integration (K-01 … K-08)
# MAGIC Run this first in a new workspace. It shows **PASS / FAIL / MANUAL** for each check and writes the results into
# MAGIC `project.yaml` (`capabilities`), which the framework code follows (for example the lock method).
# MAGIC
# MAGIC | Check | What |
# MAGIC |---|---|
# MAGIC | K-01 | atomic rename on `/Workspace` files |
# MAGIC | K-02 | exclusive file create (`O_EXCL`); fallback: `mkdir` lock |
# MAGIC | K-03 | folder permissions readable; who can read the project folder |
# MAGIC | K-04 | the hash sample is the same through a view and its base table (give one view and its base table) |
# MAGIC | K-05 | lineage system tables readable |
# MAGIC | K-06 | libraries in this notebook's serverless environment |
# MAGIC | K-07, K-08 | by hand: audit logs mark Genie actions; workspace HTML may load a CDN script |

# COMMAND ----------

dbutils.widgets.text("project_root", "", "Project folder")
dbutils.widgets.dropdown("run_by", "genie", ["genie", "person"], "Run by")
dbutils.widgets.text("view", "", "K-04: a view (schema.view), optional")
dbutils.widgets.text("base_table", "", "K-04: its base table (schema.table), optional")

# COMMAND ----------

import os, sys
sys.dont_write_bytecode = True          # no __pycache__ in /Workspace
sys.path.insert(0, os.path.abspath(".."))
try:
    os.environ["B2S_USER"] = spark.sql("SELECT current_user() u").collect()[0]["u"]
except Exception:
    pass
os.environ["B2S_VIA"] = "notebook"
os.environ["B2S_RUN_BY"] = dbutils.widgets.get("run_by")
from b2s import FRAMEWORK_VERSION, doctor
from b2s.project import open_project
from b2s.install import refresh_project_agents
NB = "nb_doctor"
layout = open_project(dbutils.widgets.get("project_root").strip() or os.environ.get("B2S_PROJECT", ""))
print("framework", FRAMEWORK_VERSION, "| python", sys.version.split()[0], "| project", layout.root)

# COMMAND ----------

files = doctor.file_checks(layout)
spark_res = doctor.spark_checks(spark, layout, dbutils.widgets.get("view").strip() or None,
                                dbutils.widgets.get("base_table").strip() or None)
refresh_project_agents(layout)
print(doctor.render({**files["results"], **spark_res}))
print("capabilities:", files["capabilities"])

# COMMAND ----------

# MAGIC %md
# MAGIC **Result:** every check PASS (or MANUAL). A FAIL on K-02 is fine when MKDIR passes: the framework then locks with
# MAGIC `mkdir`. A FAIL on K-01 or SHARED stops integration: fix it first.

# COMMAND ----------

# Check by a different method: read the capabilities back from project.yaml
import yaml
caps = yaml.safe_load(open(layout.project_yaml, encoding="utf-8")).get("capabilities")
print(caps)
assert caps and caps["lock_mode"] in ("o_excl", "mkdir"), "no usable lock method on this file system"

# COMMAND ----------

# Status (one short JSON line for Genie Code)
import json as _json
_all = {**files["results"], **spark_res}
print("B2S_STATUS " + _json.dumps({"notebook": NB, "ok": all(r["ok"] is not False for r in _all.values()),
                                   "failed": [k for k, r in _all.items() if r["ok"] is False],
                                   "lock_mode": caps["lock_mode"]}))
