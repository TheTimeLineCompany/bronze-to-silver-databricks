# Databricks notebook source
# MAGIC %md
# MAGIC # P2.1 Documents (inventory, triage, extracts)
# MAGIC Lists the files in `apps/<app>/inbox`, finds copies and versions, sorts them by relevance, and extracts the text
# MAGIC of core and supporting files with personal data replaced by shapes. **A person runs this notebook.**
# MAGIC The claims (evidence) are written afterwards by Genie Code (`@p2-1-triage`, then `@p2-2-compare`), from the extracts only.

# COMMAND ----------

dbutils.widgets.text("project_root", "", "Project folder")
dbutils.widgets.dropdown("run_by", "genie", ["genie", "person"], "Run by (Genie Code orchestrates by default)")
dbutils.widgets.text("app", "", "Application id (S01_name)")

# COMMAND ----------

# Setup: framework on the path, identity from the workspace, project state.
import os, sys
sys.dont_write_bytecode = True          # no __pycache__ in /Workspace
sys.path.insert(0, os.path.abspath(".."))
from b2s import identity
identity.from_workspace(spark)            # account e-mail and display name, never typed
os.environ["B2S_VIA"] = "notebook"
os.environ["B2S_RUN_BY"] = dbutils.widgets.get("run_by")   # recorded in every event (audit)
from b2s import FRAMEWORK_VERSION, documents, versions
from b2s.project import open_project
from b2s.store import acquire_lease, release_lease
layout = open_project((dbutils.widgets.get("project_root").strip() or os.environ.get("B2S_PROJECT", "")))
APP = dbutils.widgets.get("app")
acquire_lease(layout, APP)
print("framework", FRAMEWORK_VERSION, "| user", os.environ.get("B2S_USER"))

# COMMAND ----------

# MAGIC %md ## 1. Inventory

# COMMAND ----------

inv = documents.inventory(layout, APP)
print(inv["_version"], "|", len(inv["files"]), "files,", inv["documents"], "unique")
print("copies:", inv["duplicates"])
print("same name, different content (compare):", inv["compare"])
print("unreadable:", inv["unreadable"])

# COMMAND ----------

# MAGIC %md
# MAGIC **Result:** fill in — number of files, copies, files to compare, unreadable files (they need an extractor or a person).

# COMMAND ----------

# Check by a different method: count the inbox files directly on disk.
on_disk = [p for p in layout.sub(APP, "inbox").rglob("*") if p.is_file() and not p.name.startswith(".")]
assert len(on_disk) == len(inv["files"]), (len(on_disk), len(inv["files"]))
print("check OK:", len(on_disk), "files")

# COMMAND ----------

# MAGIC %md ## 2. Triage

# COMMAND ----------

tri = documents.triage(layout, APP)
print(tri["_version"], tri["counts"])
for e in tri["documents"]:
    print(f'{e["relevance"]:11} {e["doc_id"]} {e["path"]:40} {e["type"] or ""} — {e["reason"]}')

# COMMAND ----------

# MAGIC %md
# MAGIC **Result:** fill in — core and supporting files and their reading plans. Change a relevance by giving input
# MAGIC (`00_start_here` → give-input), not by editing the triage file.

# COMMAND ----------

# Check by a different method: every unique document has exactly one non-ignored or ignored entry, and core <= budget.
ids = {f["doc_id"] for f in inv["files"]}
assert ids == {e["doc_id"] for e in tri["documents"]}
assert tri["counts"]["core"] <= tri["max_core_files"]
print("check OK")

# COMMAND ----------

# MAGIC %md ## 3. Extract

# COMMAND ----------

ext = documents.extract(layout, APP)
print("extracted:", ext["extracted"])
print("need an extractor:", ext["needs_extractor"])

# COMMAND ----------

# MAGIC %md
# MAGIC **Result:** fill in — extracted documents. Next: Genie Code `@p2-1-triage`, then `@p2-2-compare` (documents against the baseline).

# COMMAND ----------

# Check by a different method: no email address is left in any extract.
import re
for p in layout.sub(APP, "documents", "extracts").glob("*.md"):
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", p.read_text(encoding="utf-8")), p.name
print("privacy check OK")
release_lease(layout, APP)

# COMMAND ----------

# Status (one short JSON line for Genie Code; feedback I-17 §4)
import json as _json
_status = {"notebook": 'nb_p2_documents', "app": globals().get("APP"), "ok": True}
for _k in ("summary", "res", "results", "req"):
    if isinstance(globals().get(_k), dict):
        _status.update({k: v for k, v in globals()[_k].items() if k in ("partial", "_version", "remaining_count", "id", "passed", "failed")})
print("B2S_STATUS " + _json.dumps(_status, default=str)[:2000])
