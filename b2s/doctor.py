"""Workspace checks K-01 ... K-08 (design §22) and the capability flags the code follows (feedback I-17 §1).

`file_checks(layout)` runs where the project folder lives (local disk or /Workspace):
  K-01 atomic rename over an existing file      K-02 exclusive create (O_EXCL)      mkdir as a lock (fallback)
and writes `capabilities` into project.yaml: lock_mode o_excl | mkdir, atomic_rename true | false.
`spark_checks(spark, ...)` runs in the notebook nb_doctor on Databricks: K-04 sample through a view = base table,
K-05 lineage system tables readable, K-06 libraries in the serverless environment, K-03 folder permissions.
K-07 (audit logs mark Genie actions) and K-08 (CDN scripts in workspace HTML) are manual: listed as such.
"""
from __future__ import annotations

import os
import secrets
import sys

import yaml

from .layout import Layout, guard_write, is_shared, workspace_path
from .store import atomic_write, dump_yaml, emit_event, now_iso


def _probe_dir(layout: Layout):
    d = guard_write(layout.state_dir / "probe" / secrets.token_hex(4))
    d.mkdir(parents=True, exist_ok=True)
    return d


def file_checks(layout: Layout, save: bool = True) -> dict:
    d = _probe_dir(layout)
    res = {}
    # K-01 atomic rename over an existing file
    try:
        a, b = d / "a.txt", d / "b.txt"
        a.write_text("old")
        b.write_text("new")
        os.replace(b, a)
        res["K-01"] = {"ok": a.read_text() == "new" and not b.exists(), "what": "atomic rename over an existing file"}
    except Exception as e:  # noqa: BLE001
        res["K-01"] = {"ok": False, "what": "atomic rename over an existing file", "error": repr(e)}
    # K-02 exclusive create
    try:
        p = d / "x.lock"
        os.close(os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        try:
            os.close(os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            ok = False                                   # second create must fail
        except FileExistsError:
            ok = True
        res["K-02"] = {"ok": ok, "what": "exclusive file create (O_EXCL) refuses a second create"}
    except Exception as e:  # noqa: BLE001
        res["K-02"] = {"ok": False, "what": "exclusive file create (O_EXCL)", "error": repr(e)}
    # mkdir lock fallback
    try:
        m = d / "m.lockdir"
        os.mkdir(m)
        try:
            os.mkdir(m)
            ok = False
        except FileExistsError:
            ok = True
        res["MKDIR"] = {"ok": ok, "what": "mkdir refuses an existing folder (fallback lock)"}
    except Exception as e:  # noqa: BLE001
        res["MKDIR"] = {"ok": False, "what": "mkdir as a lock", "error": repr(e)}
    res["SHARED"] = {"ok": not is_shared(layout.root), "what": f"project folder not under Shared ({workspace_path(layout.root)})"}
    res["PYTHON"] = {"ok": sys.version_info >= (3, 10), "what": f"Python {sys.version.split()[0]} (needs 3.10+)"}
    for k in ("K-07", "K-08"):
        res[k] = {"ok": None, "what": {"K-07": "audit logs mark actions by Genie Code (check by hand)",
                                       "K-08": "workspace HTML may load a CDN script (check by hand; viewer works without)"}[k]}
    lock_mode = "o_excl" if res["K-02"]["ok"] else ("mkdir" if res["MKDIR"]["ok"] else "none")
    caps = {"lock_mode": lock_mode, "atomic_rename": bool(res["K-01"]["ok"]), "checked_at": now_iso(),
            "checked_in": workspace_path(layout.root)}
    if save and layout.project_yaml.exists():
        cfg = yaml.safe_load(layout.project_yaml.read_text(encoding="utf-8"))
        cfg["capabilities"] = {**(cfg.get("capabilities") or {}), **caps}
        atomic_write(layout.project_yaml, dump_yaml(cfg))
        emit_event(layout, "doctor_file_checks", extra={"results": res, "capabilities": caps})
    return {"results": res, "capabilities": caps}


def spark_checks(spark, layout: Layout, view: str | None = None, base: str | None = None) -> dict:  # pragma: no cover
    """Databricks only (notebook nb_doctor). Status: NOT RUN on a workspace yet."""
    res = {}
    for lib in ("yaml", "openpyxl", "jsonschema"):
        try:
            __import__(lib)
            res[f"K-06 {lib}"] = {"ok": True, "what": f"library {lib} in the serverless environment"}
        except ImportError:
            res[f"K-06 {lib}"] = {"ok": False, "what": f"library {lib} missing: add it to the notebook environment"}
    try:
        spark.sql("SELECT 1 FROM system.access.table_lineage LIMIT 1").collect()
        res["K-05"] = {"ok": True, "what": "lineage system tables readable"}
    except Exception as e:  # noqa: BLE001
        res["K-05"] = {"ok": False, "what": "lineage system tables readable", "error": type(e).__name__}
    if view and base:
        from pyspark.sql import functions as F
        from .baseline.readers import SparkReader
        r = SparkReader(spark)
        cols = [c for c, _ in r.columns(view)]
        h = lambda t: r._df(t).select(*[F.col(f"`{c}`") for c in cols]).where(  # noqa: E731
            F.abs(F.xxhash64(F.lit(42), *[F.col(f"`{c}`") for c in cols])) % 1000 < 100)
        same = h(view).exceptAll(h(base)).count() == 0 and h(base).exceptAll(h(view)).count() == 0
        res["K-04"] = {"ok": same, "what": f"hash sample is the same through {view} and {base}"}
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        st = w.workspace.get_status(str(layout.root))
        perms = w.workspace.get_permissions("directories", str(st.object_id))
        names = sorted({(a.group_name or a.user_name or a.service_principal_name) for a in perms.access_control_list or []})
        res["K-03"] = {"ok": True, "what": "folder permissions readable", "who_can_access": names}
    except Exception as e:  # noqa: BLE001
        res["K-03"] = {"ok": False, "what": "folder permissions readable", "error": type(e).__name__}
    emit_event(layout, "doctor_spark_checks", extra={"results": res})
    return res


def render(results: dict) -> str:
    lines = []
    for k, r in results.items():
        mark = "PASS" if r["ok"] else ("MANUAL" if r["ok"] is None else "FAIL")
        lines.append(f"{mark:<6} {k:<14} {r['what']}" + (f"  ({r['error']})" if r.get("error") else ""))
    return "\n".join(lines)

