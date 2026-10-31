# Databricks notebook source
# MAGIC %md
# MAGIC # Start here
# MAGIC 1. Choose a **source** at the top. The page shows where it is and the **next step**.
# MAGIC 2. If the next step is **Run**: set **action** to `next` and click **Run all**.
# MAGIC 3. If it is **Genie**: copy the text into Genie Code. If it is **You**: review and approve in a PR.
# MAGIC
# MAGIC
# MAGIC **Your input, at any time:** type in **message**, then set **action** to
# MAGIC `give-instruction` (before or during a step: applies to **step**, or all steps) or
# MAGIC `give-feedback` (after a review: applies to **checkpoint**, default the current one). Click **Run all**.
# MAGIC **Files:** upload them to `sources/<source>/uploads/`, set **action** `register-uploads` and **purpose**
# MAGIC (`instruction`, `feedback`, or `handover` to pass them to the next stage). Filled scope sheets are applied directly.
# MAGIC
# MAGIC **Every input is checked** against the business, data, and information ontology at once: the notebook prints how it
# MAGIC was understood, what is unknown or in conflict, and where it goes (the route).
# MAGIC **Clarify:** at the start of each checkpoint and after each new input, Genie asks you a few questions first
# MAGIC (action `clarify` shows them; type the shown `@x-clarify ...` text in Genie Code). `clarify-skip` skips one (recorded).
# MAGIC
# MAGIC First time in this workspace: set **action** to `setup-check` and click **Run all**.
# MAGIC New source: set **action** to `new-source`, fill **new_source_id** and **bronze_schema**, click **Run all**.

# COMMAND ----------
# MAGIC %pip install -q -r requirements-ci.txt

# COMMAND ----------
import os, sys
ROOT = os.path.abspath(".")                      # this notebook sits in the repo root
sys.path.insert(0, os.path.join(ROOT, "tools"))
import x_navigator as nav

ACTIONS = ["status", "next", "give-instruction", "give-feedback", "register-uploads", "setup-check", "new-source"] + list(nav.ACTIONS)
import x_feedback as _fb
src_list = nav.sources(ROOT) or ["(no sources yet)"]
dbutils.widgets.dropdown("source", src_list[0], src_list)
dbutils.widgets.dropdown("action", "status", ACTIONS)
dbutils.widgets.text("message", "")
dbutils.widgets.dropdown("purpose", "feedback", ["feedback", "instruction", "handover"])
dbutils.widgets.dropdown("step", "all", ["all"] + [x for x, _, _ in _fb.STEPS])
dbutils.widgets.dropdown("checkpoint", "current", ["current"] + _fb.SOURCE_CP_ORDER + _fb.GLOBAL_CPS)
dbutils.widgets.text("new_source_id", "")
dbutils.widgets.text("bronze_schema", "")
source, action = dbutils.widgets.get("source"), dbutils.widgets.get("action")

# COMMAND ----------
# Do the chosen action. Every code step is safe to run again. 'next' always moves on to the next code step.
_prev = globals().get("_last_source")
_last_source = source
if action == "new-source":
    print(nav.add_source(dbutils.widgets.get("new_source_id").strip(), dbutils.widgets.get("bronze_schema").strip(), root=ROOT))
    print("Re-run this notebook to see the new source in the list.")
elif action == "give-instruction":
    _out = nav.add_instruction(source, dbutils.widgets.get("message"), dbutils.widgets.get("step"), root=ROOT)
    print(_out); print(nav.understanding(source, _out, ROOT))
    print("Clear the message box before the next one.")
elif action == "register-uploads":
    _out = nav.register_uploads(source, dbutils.widgets.get("purpose"), dbutils.widgets.get("message"),
                                dbutils.widgets.get("checkpoint"), dbutils.widgets.get("step"), root=ROOT)
    print(_out); print(nav.understanding(source, _out, ROOT))
elif action == "give-feedback":
    _out = nav.give_feedback(source, dbutils.widgets.get("message"), dbutils.widgets.get("checkpoint"), root=ROOT)
    print(_out); print(nav.understanding(source, _out, ROOT))
    print("Clear the message box before the next one.")
elif action != "status" and _prev not in (None, source):
    print(f"You changed the source to {source}. Nothing was run. Click Run all again to run '{action}' for {source}.")
elif action != "status":
    print(nav.run(action, source, root=ROOT, spark=spark))

# COMMAND ----------
# Where the source is and what comes next
if source in nav.sources(ROOT):
    displayHTML(nav.html(source, ROOT))
