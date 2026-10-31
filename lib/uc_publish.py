"""Publish silver metadata to Unity Catalog after a load: comments, tags, privacy, and informational keys.

Why: Catalog Explorer then shows what each silver table and column means, which source and business object it
comes from, which columns hold personal data, and the PK/FK diagram. BI tools, Genie spaces, and the query
optimizer can use the declared keys (Databricks PK/FK constraints are informational: not enforced, QA enforces them).

    from lib.uc_publish import publish
    report = publish(spark, TARGET, T, source_id, parents={"Location": "dev.silver.slv_mst_location", ...})

`statements()` is pure (testable); `publish()` runs each statement and reports, it never fails the load.
"""
from __future__ import annotations

import os

import yaml

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _q(s):
    return "'" + str(s or "").replace("\\", "\\\\").replace("'", "\\'") + "'"


def _privacy_cfg(root=None):
    p = os.path.join(root or _ROOT, "standards", "privacy.yaml")
    return yaml.safe_load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def statements(fqn: str, t: dict, source_id: str, parents: dict | None = None, root: str | None = None) -> list:
    """SQL statements (in order) for one silver table. parents: {entity or same-STTM table name: parent fqn}."""
    pc = _privacy_cfg(root)
    name = fqn.split(".")[-1]
    out = [f"COMMENT ON TABLE {fqn} IS {_q(t.get('grain'))}"]
    tags = {"business_object": t.get("business_object"), "data_class": t.get("data_class"), "source_id": source_id,
            "load_pattern": t.get("load_pattern")}
    out.append(f"ALTER TABLE {fqn} SET TAGS (" + ", ".join(f"{_q(k)} = {_q(v)}" for k, v in tags.items() if v) + ")")
    for c in t["columns"]:
        col = c["target"]
        if c.get("description"):
            out.append(f"ALTER TABLE {fqn} ALTER COLUMN {col} COMMENT {_q(c['description'])}")
        pv = c.get("privacy") or {}
        if pv.get("handling"):
            ptags = (pc.get("tags") or {}).get(pv.get("class"), {"pii": "true"})
            out.append(f"ALTER TABLE {fqn} ALTER COLUMN {col} SET TAGS (" + ", ".join(f"{_q(k)} = {_q(v)}" for k, v in ptags.items()) + ")")
            if pv["handling"] == "mask":
                fn = pc.get("mask_function")
                out.append(f"ALTER TABLE {fqn} ALTER COLUMN {col} SET MASK {fn}" if fn else
                           f"-- SKIPPED mask on {col}: standards/privacy.yaml has no mask_function")
    pk = t.get("primary_key") or []
    if pk:
        for c in pk:
            out.append(f"ALTER TABLE {fqn} ALTER COLUMN {c} SET NOT NULL")
        out.append(f"ALTER TABLE {fqn} DROP CONSTRAINT IF EXISTS pk_{name}")
        out.append(f"ALTER TABLE {fqn} ADD CONSTRAINT pk_{name} PRIMARY KEY ({', '.join(pk)})")
    for c in t["columns"]:
        fk = c.get("fk") or {}
        parent = (parents or {}).get(fk.get("entity") or fk.get("table") or "")
        if fk and parent:
            cn = f"fk_{name}_{c['target']}"[:120]
            out.append(f"ALTER TABLE {fqn} DROP CONSTRAINT IF EXISTS {cn}")
            out.append(f"ALTER TABLE {fqn} ADD CONSTRAINT {cn} FOREIGN KEY ({c['target']}) REFERENCES {parent} ({fk['column']})")
    return out


def publish(spark, fqn: str, t: dict, source_id: str, parents: dict | None = None, root: str | None = None) -> list:
    """Run the statements; return [{statement, status, error}]. Never raises (metadata must not fail a load)."""
    rep = []
    for sql in statements(fqn, t, source_id, parents, root):
        if sql.startswith("--"):
            rep.append({"statement": sql, "status": "skipped", "error": None})
            continue
        try:
            spark.sql(sql)
            rep.append({"statement": sql, "status": "ok", "error": None})
        except Exception as e:  # noqa: BLE001
            rep.append({"statement": sql, "status": "error", "error": f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"})
    return rep
