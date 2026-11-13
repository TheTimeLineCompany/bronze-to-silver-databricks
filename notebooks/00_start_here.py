# Databricks notebook source
# MAGIC %md
# MAGIC # Start here — Bronze-to-Silver V1.4
# MAGIC Pick an **action**, fill the fields it needs, and click **Run all**.
# MAGIC
# MAGIC | Action | Does |
# MAGIC |---|---|
# MAGIC | `setup-check` | checks libraries, identity, project folder location and the framework version |
# MAGIC | `new-project` | creates a project folder (not under /Workspace/Shared) |
# MAGIC | `register-app` | registers an application: id `S01_name`, schemas, lookup schemas |
# MAGIC | `status` | shows each step, what is stale and why, the approvals, and what to do next |
# MAGIC | `give-input` | records a typed instruction or feedback as an input (IN-) for Genie to route |
# MAGIC | `approve` | fallback when no chat is available: same approval request and statement as in the chat |
# MAGIC
# MAGIC Most work happens in the Genie Code chat (skills in `skills/`). Heavy work runs in `nb_p1_baseline` and `nb_p2_documents`.

# COMMAND ----------

dbutils.widgets.dropdown("action", "status", ["setup-check", "new-project", "register-app", "status", "give-input", "approve"], "Action")
dbutils.widgets.text("project_root", "", "Project folder")
dbutils.widgets.dropdown("run_by", "genie", ["genie", "person"], "Run by (Genie Code orchestrates by default)")
dbutils.widgets.text("app", "", "Application id (S01_name)")
dbutils.widgets.text("text", "", "Name / schemas / input / checkpoint (CP1..CP4) / AR id")
dbutils.widgets.text("text2", "", "Lookup schemas / statement")

# COMMAND ----------

# Setup: framework on the path, identity from the workspace (never typed).
import os, sys
sys.path.insert(0, os.path.abspath(".."))
try:
    os.environ["B2S_USER"] = spark.sql("SELECT current_user() u").collect()[0]["u"]
except Exception:
    pass
os.environ["B2S_VIA"] = "notebook"
os.environ["B2S_RUN_BY"] = dbutils.widgets.get("run_by")   # recorded in every event (audit)
from b2s import FRAMEWORK_VERSION, navigator, items
from b2s.project import init_project, open_project, register_app
from b2s.approve import request, record, ApprovalError
action = dbutils.widgets.get("action")
root, app = dbutils.widgets.get("project_root").strip(), dbutils.widgets.get("app").strip()
t1, t2 = dbutils.widgets.get("text").strip(), dbutils.widgets.get("text2").strip()
print("framework", FRAMEWORK_VERSION, "| user", os.environ.get("B2S_USER"), "| action", action)

# COMMAND ----------

if action == "setup-check":
    problems = []
    for lib in ("yaml", "openpyxl"):
        try:
            __import__(lib)
        except ImportError:
            problems.append(f"library {lib} missing: add it to this notebook's serverless environment")
    if root and "/Workspace/Shared" in root:
        problems.append("project folder is under /Workspace/Shared (readable by all users): move it")
    if not os.environ.get("B2S_USER"):
        problems.append("current_user() not available")
    print("SETUP OK" if not problems else "SETUP PROBLEMS:\n- " + "\n- ".join(problems))
elif action == "new-project":
    layout = init_project(root, t1 or "project")
    print("project created:", layout.root)
elif action == "register-app":
    layout = open_project(root)
    print(register_app(layout, app, app, [s.strip() for s in t1.split(",") if s.strip()],
                       [s.strip() for s in t2.split(",") if s.strip()]))
elif action == "status":
    layout = open_project(root)
    print(navigator.render_text(navigator.status(layout, app)))
elif action == "give-input":
    layout = open_project(root)
    it = items.create(layout, app, "input", {"text": t1, "kind": "instruction"}, via="notebook")
    print(f"recorded {it['id']}. In the Genie chat: @x-input {it['id']}")
elif action == "approve":
    layout = open_project(root)
    try:
        if t1.startswith("CP"):
            req = request(layout, app, t1)
            print(req["chat_text"])
            print(f"\nNow set action=approve, text={req['id']}, text2=<your completed statement>, and run again.")
        else:
            res = record(layout, app, t1, t2, how="notebook")
            print("recorded", res["approval"]["id"], res.get("handoff") or "")
    except ApprovalError as e:
        print("NOT RECORDED:", e)

# COMMAND ----------

# MAGIC %md
# MAGIC **Result:** read the output above. For `status`, the *Next* list says what to run: a notebook (you), a skill in the Genie chat, or an approval.

# COMMAND ----------

# Check by a different method: count events written by this run's user today (the action above must have left a trace).
if root and action not in ("setup-check",):
    from b2s.store import list_events
    evs = [e for e in list_events(open_project(root)) if e["user"] == os.environ.get("B2S_USER")]
    print(f"events by {os.environ.get('B2S_USER')}: {len(evs)} (latest: {evs[-1]['action'] if evs else '-'})")
