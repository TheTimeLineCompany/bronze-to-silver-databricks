"""QA checks for silver tables, driven by the STTM.

Each function maps to one item in standards/qa_checklist.md (QA-01, QA-02 ...).
Replace or extend the checks so that every item of the client's checklist has
one function here. Then the checklist is enforced by code, not by memory.

Every check returns a dict:
    {"check": "QA-03 pk_unique", "table": ..., "status": "pass"|"fail"|"error",
     "metric": <number>, "threshold": <number>, "evidence": "<short text or SQL>"}
A check never hides a failure: an exception becomes status "error" with the message.

Typical use in a notebook (see tools/p5_1_gen_notebook.py):
    from lib import qa_checks as qa
    results = qa.run_table_checks(spark, sttm_table, silver_fqn, bronze_count=n_in)
    qa.write_summary(results, "sources/<source_id>/05_build/qa_results/<table>.json")
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import yaml

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _naming():
    with open(os.path.join(_ROOT, "standards", "naming.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def _res(check, table, ok, metric=None, threshold=None, evidence=""):
    return {"check": check, "table": table, "status": "pass" if ok else "fail",
            "metric": metric, "threshold": threshold, "evidence": evidence}


def entity_tables(catalog: str, schema: str, root: str | None = None) -> dict:
    """{entity name: catalog.schema.target_table} for every shared master in registry/entities.yaml."""
    with open(os.path.join(root or _ROOT, "registry", "entities.yaml"), encoding="utf-8") as f:
        return {e["name"]: f"{catalog}.{schema}.{e['target_table']}" for e in yaml.safe_load(f)["entities"]}


def _real(spark, sttm_table, table):
    """The table without the unknown-member row (it has NULLs and '#UNKNOWN' keys by design)."""
    from lib.keys import UNKNOWN_SK
    df = spark.table(table)
    sk = (sttm_table.get("surrogate_key") or {}).get("column")
    if sk and sk in df.columns:
        from pyspark.sql import functions as F
        df = df.where(F.col(sk).isNull() | (F.col(sk) != F.lit(UNKNOWN_SK)))
    return df


def _safe(fn):
    def wrap(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:  # noqa: BLE001  report, never hide
            label = (fn.__doc__ or fn.__name__).split(":")[0].strip() + " " + fn.__name__.split("_", 1)[-1]
            return {"check": label, "table": k.get("table") or (a[2] if len(a) > 2 else None),
                    "status": "error", "metric": None, "threshold": None, "evidence": f"{type(e).__name__}: {e}"}
    return wrap


@_safe
def qa01_row_count_reconciliation(spark, sttm_table, table, bronze_count, tolerance_pct=0.0):
    """QA-01: silver rows vs. bronze rows after the STTM filter and dedup (for 1 row in = 1 row out grains)."""
    df = _real(spark, sttm_table, table)
    n = df.count() if sttm_table["load_pattern"] != "scd2" else df.where("is_current = true").count()
    diff = abs(n - bronze_count)
    pct = 0.0 if bronze_count == 0 else 100.0 * diff / bronze_count
    return _res("QA-01 row_count_reconciliation", table, pct <= tolerance_pct, round(pct, 4), tolerance_pct,
                f"silver={n} bronze_after_filter={bronze_count}")


@_safe
def qa02_schema_matches_sttm(spark, sttm_table, table):
    """QA-02: every STTM column exists with the declared type; audit columns exist."""
    actual = {f.name: f.dataType.simpleString().upper() for f in spark.table(table).schema.fields}
    missing, wrong = [], []
    for c in sttm_table["columns"]:
        if c["target"] not in actual:
            missing.append(c["target"])
            continue
        want = c["type"].split("(")[0].upper().replace("INT", "INT")
        got = actual[c["target"]].split("(")[0]
        alias = {"STRING": "STRING", "INT": "INT", "INTEGER": "INT", "BIGINT": "BIGINT", "DECIMAL": "DECIMAL",
                 "DOUBLE": "DOUBLE", "BOOLEAN": "BOOLEAN", "DATE": "DATE", "TIMESTAMP": "TIMESTAMP"}
        if alias.get(got, got) != alias.get(want, want):
            wrong.append(f"{c['target']}: {got} != {want}")
    missing += [a for a in _naming().get("audit_columns", []) if a not in actual]
    return _res("QA-02 schema_matches_sttm", table, not missing and not wrong, len(missing) + len(wrong), 0,
                f"missing={missing} wrong_type={wrong}")


@_safe
def qa03_pk_unique(spark, sttm_table, table):
    """QA-03: primary key is unique and not null."""
    pk = sttm_table["primary_key"]
    df = spark.table(table)
    nulls = df.where(" OR ".join(f"{c} IS NULL" for c in pk)).count()
    dups = df.groupBy(*pk).count().where("count > 1").count()
    return _res("QA-03 pk_unique", table, nulls == 0 and dups == 0, dups + nulls, 0,
                f"duplicate_keys={dups} null_keys={nulls} pk={pk}")


@_safe
def qa04_not_null(spark, sttm_table, table):
    """QA-04: columns declared nullable: false have no nulls."""
    cols = [c["target"] for c in sttm_table["columns"] if not c["nullable"]]
    df = _real(spark, sttm_table, table)
    bad = {c: df.where(f"{c} IS NULL").count() for c in cols}
    bad = {k: v for k, v in bad.items() if v}
    return _res("QA-04 not_null", table, not bad, sum(bad.values()), 0, f"null_counts={bad}")


@_safe
def qa05_fk_integrity(spark, sttm_table, table, entity_tables: dict, max_orphan_pct=0.0, silver_prefix: str | None = None):
    """QA-05: every FK value exists in its shared master (or is the unknown member, if allowed)."""
    from lib.keys import UNKNOWN_SK
    details, worst, misuse = {}, 0.0, {}
    total = spark.table(table).count() or 1
    for c in sttm_table["columns"]:
        fk = c.get("fk")
        if not fk:
            continue
        if fk.get("table"):                                    # FK to another table of the same STTM (e.g. line -> header)
            if not silver_prefix:
                raise KeyError(f"no silver_prefix given for table FK '{fk['table']}' (column {c['target']})")
            parent = f"{silver_prefix}.{fk['table']}"
        elif fk.get("entity") not in entity_tables:
            raise KeyError(f"no silver table given for entity '{fk.get('entity')}' (column {c['target']}); add it to ENTITY_TABLES")
        else:
            parent = entity_tables[fk["entity"]]
        q = (f"SELECT count(*) AS n FROM {table} t LEFT ANTI JOIN {parent} p "
             f"ON t.{c['target']} = p.{fk['column']} WHERE t.{c['target']} IS NOT NULL")
        orphans = spark.sql(q).first()["n"]
        unknown = spark.sql(f"SELECT count(*) AS n FROM {table} WHERE {c['target']} = '{UNKNOWN_SK}'").first()["n"]
        pct = 100.0 * orphans / total
        worst = max(worst, pct)
        details[c["target"]] = {"orphans": orphans, "unknown_member": unknown}
        if unknown and fk.get("orphan_policy") != "unknown_member":
            misuse[c["target"]] = unknown                 # rows point to the unknown member without permission
    return _res("QA-05 fk_integrity", table, worst <= max_orphan_pct and not misuse, round(worst, 4), max_orphan_pct,
                f"fk={details}" + (f" unknown_member_not_allowed={misuse}" if misuse else ""))


@_safe
def qa06_scd2_validity(spark, sttm_table, table):
    """QA-06: SCD2 history is valid: one current row per key, the current row is the latest, no inverted,
    overlapping, or gapped periods, closed rows have effective_to, current rows do not."""
    if sttm_table["load_pattern"] != "scd2":
        return _res("QA-06 scd2_validity", table, True, 0, 0, "not an scd2 table")
    bk = ", ".join(sttm_table["business_key"])
    r = spark.sql(f"""
        WITH v AS (
          SELECT {bk}, effective_from, effective_to, is_current,
                 lead(effective_from) OVER (PARTITION BY {bk} ORDER BY effective_from) AS next_from,
                 max(effective_from)  OVER (PARTITION BY {bk})                          AS last_from
          FROM {table})
        SELECT
          sum(CASE WHEN effective_to IS NOT NULL AND effective_to <= effective_from THEN 1 ELSE 0 END) AS inverted,
          sum(CASE WHEN next_from IS NOT NULL AND (effective_to IS NULL OR effective_to <> next_from) THEN 1 ELSE 0 END) AS not_contiguous,
          sum(CASE WHEN is_current AND (effective_from <> last_from OR effective_to IS NOT NULL) THEN 1 ELSE 0 END) AS bad_current,
          sum(CASE WHEN NOT is_current AND effective_to IS NULL THEN 1 ELSE 0 END) AS open_not_current
        FROM v""").first().asDict()
    r = {k: int(v or 0) for k, v in r.items()}
    multi = spark.sql(f"""SELECT count(*) AS n FROM (SELECT {bk}, sum(CASE WHEN is_current THEN 1 ELSE 0 END) AS c
                          FROM {table} GROUP BY {bk}) WHERE c <> 1""").first()["n"]
    r["keys_without_one_current"] = int(multi)
    bad = sum(r.values())
    return _res("QA-06 scd2_validity", table, bad == 0, bad, 0, " ".join(f"{k}={v}" for k, v in r.items()))


@_safe
def qa07_key_patterns(spark, sttm_table, table):
    """QA-07: normalised business keys match their key rule pattern."""
    from lib.keys import key_pattern_ok
    from pyspark.sql import functions as F
    df = _real(spark, sttm_table, table)
    bad = {}
    for c in sttm_table["columns"]:
        if c["rule"] == "normalised_key" and c.get("key_rule"):
            n = df.where(F.col(c["target"]).isNotNull() & ~key_pattern_ok(c["key_rule"], F.col(c["target"]))).count()
            if n:
                bad[c["target"]] = n
    return _res("QA-07 key_patterns", table, not bad, sum(bad.values()), 0, f"bad_keys={bad}")


def _not_run(check, table, why):
    return {"check": check, "table": table, "status": "error", "metric": None, "threshold": None, "evidence": f"not run: {why}"}


def run_table_checks(spark, sttm_table, table, bronze_count=None, entity_tables=None, tolerance_pct=0.0, silver_prefix=None):
    """Run every check that applies to this table (lib/qa_rules.py). A check that cannot run is an ERROR,
    never a silent skip: CP5 then fails until the notebook gives the missing input."""
    from lib.qa_rules import required_checks
    req = set(required_checks(sttm_table))
    out = []
    if "QA-01" in req:
        out.append(qa01_row_count_reconciliation(spark, sttm_table, table, bronze_count, tolerance_pct) if bronze_count is not None
                   else _not_run("QA-01 row_count_reconciliation", table, "bronze_count is not set (row count after filter + dedup)"))
    out += [qa02_schema_matches_sttm(spark, sttm_table, table), qa03_pk_unique(spark, sttm_table, table),
            qa04_not_null(spark, sttm_table, table)]
    if "QA-05" in req:
        fk_entities = {c["fk"]["entity"] for c in sttm_table["columns"] if c.get("fk") and c["fk"].get("entity")}
        has_table_fk = any(c.get("fk") and c["fk"].get("table") for c in sttm_table["columns"])
        missing = sorted(fk_entities - set(entity_tables or {}))
        if missing:
            out.append(_not_run("QA-05 fk_integrity", table, f"ENTITY_TABLES has no table for {missing}"))
        elif has_table_fk and not silver_prefix:
            out.append(_not_run("QA-05 fk_integrity", table, "silver_prefix (catalog.schema) is not set for table FKs"))
        else:
            out.append(qa05_fk_integrity(spark, sttm_table, table, entity_tables or {}, silver_prefix=silver_prefix))
    if "QA-06" in req:
        out.append(qa06_scd2_validity(spark, sttm_table, table))
    if "QA-07" in req:
        out.append(qa07_key_patterns(spark, sttm_table, table))
    known = {"QA-01", "QA-02", "QA-03", "QA-04", "QA-05", "QA-06", "QA-07"}
    for extra in sorted(req - known):
        out.append(_not_run(extra, table, "checklist item has no function in lib/qa_checks.py yet"))
    return out


def write_summary(results: list, path: str, source_id: str | None = None):
    """Write one result file (combine_summaries builds summary.json for CP5). All checks must have status 'pass'."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = {"source_id": source_id, "generated_at": datetime.now(timezone.utc).isoformat(),
           "all_passed": all(r["status"] == "pass" for r in results), "checks": results}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, default=str)
    return doc


def combine_summaries(folder: str, source_id: str | None = None):
    """Merge every per-table result file in `folder` into summary.json (read by checkpoint CP5)."""
    checks = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".json") and name != "summary.json":
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                checks += json.load(f).get("checks", [])
    return write_summary(checks, os.path.join(folder, "summary.json"), source_id)
