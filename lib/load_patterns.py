"""Standard Delta load patterns for silver tables.

One function per `load_pattern` in the STTM. Notebooks call these functions;
they do not write their own MERGE logic. This keeps every pipeline the same shape.

    from lib.load_patterns import load
    load(spark, df, target_fqn, sttm_table, batch_id=batch_id, src_system="CNTRK", src_table="legs")
"""
from __future__ import annotations

from datetime import datetime, timezone


def add_audit_columns(df, src_system: str, src_table: str, batch_id: str):
    from pyspark.sql import functions as F
    if "_ingest_ts" not in df.columns:
        df = df.withColumn("_ingest_ts", F.current_timestamp())
    return (df.withColumn("_src_system", F.lit(src_system))
              .withColumn("_src_table", F.lit(src_table))
              .withColumn("_load_ts", F.current_timestamp())
              .withColumn("_batch_id", F.lit(batch_id)))


def _table_exists(spark, fqn):
    try:
        return spark.catalog.tableExists(fqn)
    except Exception:  # noqa: BLE001
        return False


def append(spark, df, fqn, sttm_table, **_):
    df.write.format("delta").mode("append").saveAsTable(fqn)


def overwrite(spark, df, fqn, sttm_table, **_):
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "false").saveAsTable(fqn)


def merge(spark, df, fqn, sttm_table, **_):
    """Upsert on the business key (current-state table)."""
    if not _table_exists(spark, fqn):
        df.write.format("delta").saveAsTable(fqn)
        return
    from delta.tables import DeltaTable
    bk = sttm_table["business_key"]
    cond = " AND ".join(f"t.{k} <=> s.{k}" for k in bk)
    (DeltaTable.forName(spark, fqn).alias("t").merge(df.alias("s"), cond)
        .whenMatchedUpdateAll().whenNotMatchedInsertAll().execute())


TECH_COLS = {"effective_from", "effective_to", "is_current", "_src_system", "_src_table", "_ingest_ts", "_load_ts", "_batch_id"}


def scd2_timeline(existing, incoming, business_key, tracked, from_col="effective_from"):
    """Rebuild the SCD2 timeline for the business keys in `incoming`. Pure DataFrame logic (testable without Delta).

    existing: ALL stored versions of the affected business keys (any order). May be None.
    incoming: new rows with `from_col` set. Several versions per key, in any order, are allowed.
    Rules:
      - same key + same effective_from as a stored row -> correction: the incoming row replaces it;
      - an incoming row equal (on tracked columns) to the version just before it in time -> no change, dropped;
      - late-arriving rows are placed in time order: effective_to = next version's effective_from;
      - is_current = true only for the latest version of each key.
    Returns every version of the affected keys, with effective_to and is_current recomputed.
    Stored versions are never dropped, so MERGE on (business key, effective_from) gives a correct table.
    """
    from pyspark.sql import Window
    from pyspark.sql import functions as F
    if incoming.where(F.col(from_col).isNull()).limit(1).count():
        raise ValueError(f"scd2: incoming rows with NULL {from_col}; set the change timestamp before loading")
    cols = [c for c in incoming.columns if c not in ("effective_to", "is_current")]
    order_in = [F.col("_ingest_ts").desc()] if "_ingest_ts" in incoming.columns else [F.lit(1)]
    w_dup = Window.partitionBy(*business_key, from_col).orderBy(F.col("_src").desc(), *order_in)
    inc = incoming.select(*cols).withColumn("_src", F.lit(1))
    union = inc
    if existing is not None:
        ex = existing.select(*cols).withColumn("_src", F.lit(0))
        union = ex.unionByName(inc)
    # one row per (key, effective_from): incoming wins (correction)
    union = union.withColumn("_rn", F.row_number().over(w_dup)).where("_rn = 1").drop("_rn")
    w = Window.partitionBy(*business_key).orderBy(from_col)
    h = F.sha2(F.concat_ws("||", *[F.coalesce(F.col(c).cast("string"), F.lit("\u0000")) for c in tracked]), 256) if tracked else F.lit("")
    union = union.withColumn("_h", h).withColumn("_prev_h", F.lag("_h").over(w))
    # drop incoming versions that change nothing compared with the version before them
    union = union.where(~((F.col("_src") == 1) & F.col("_h").eqNullSafe(F.col("_prev_h"))))   # null-safe: first version has no previous
    out = (union.withColumn("effective_to", F.lead(from_col).over(w))
                .withColumn("is_current", F.col("effective_to").isNull())
                .drop("_h", "_prev_h", "_src"))
    # column order: business columns, then effective_from / effective_to / is_current, then audit columns
    audit = [c for c in out.columns if c.startswith("_")]
    scd = [from_col, "effective_to", "is_current"]
    return out.select(*[c for c in out.columns if c not in audit and c not in scd], *scd, *audit)


def scd2(spark, df, fqn, sttm_table, change_ts_col="effective_from", **_):
    """SCD Type 2 on the business key, safe for late-arriving and out-of-order history.

    Tracked columns = all non-key, non-technical columns. `effective_from` must be set on every incoming row.
    Only the affected business keys are read back; their timeline is rebuilt (scd2_timeline) and upserted
    with one MERGE on (business key, effective_from).
    """
    bk = sttm_table["business_key"]
    sk = (sttm_table.get("surrogate_key") or {}).get("column")
    tracked = [c["target"] for c in sttm_table["columns"] if c["target"] not in TECH_COLS | {sk} and c["target"] not in bk]
    if not _table_exists(spark, fqn):
        scd2_timeline(None, df, bk, tracked, change_ts_col).write.format("delta").saveAsTable(fqn)
        return
    from delta.tables import DeltaTable
    keys = df.select(*bk).distinct()
    existing = spark.table(fqn).join(keys, on=bk, how="left_semi")   # business keys are NOT NULL (validator + QA-04)
    rebuilt = scd2_timeline(existing, df, bk, tracked, change_ts_col)
    cond = " AND ".join(f"t.{k} <=> s.{k}" for k in bk) + f" AND t.{change_ts_col} = s.{change_ts_col}"
    (DeltaTable.forName(spark, fqn).alias("t").merge(rebuilt.alias("s"), cond)
        .whenMatchedUpdateAll().whenNotMatchedInsertAll().execute())


def unknown_member_row(schema, sttm_table):
    """One row for the unknown member, matching the target schema. Pure Python (testable)."""
    from datetime import datetime as _dt
    from lib.keys import UNKNOWN_BK, UNKNOWN_SK
    sk = (sttm_table.get("surrogate_key") or {}).get("column")
    row = {}
    for f in schema.fields:
        t = f.dataType.simpleString()
        if f.name == sk:
            v = UNKNOWN_SK
        elif f.name == "effective_from":
            v = _dt(1900, 1, 1)
        elif f.name == "effective_to":
            v = None
        elif f.name == "is_current":
            v = True
        elif f.name in ("_src_system", "_src_table", "_batch_id"):
            v = "#unknown_member"
        elif f.name in ("_ingest_ts", "_load_ts"):
            v = _dt(1900, 1, 1)
        elif t == "string":
            v = UNKNOWN_BK
        else:
            v = None                              # numbers, dates, booleans stay NULL; QA excludes this row
        row[f.name] = v
    return row


def ensure_unknown_member(spark, fqn, sttm_table):
    """Insert the unknown-member row into a master table if it is not there yet (idempotent MERGE on the SK)."""
    sk = (sttm_table.get("surrogate_key") or {}).get("column")
    if not sk:
        return False
    tgt = spark.table(fqn)
    row = spark.createDataFrame([unknown_member_row(tgt.schema, sttm_table)], tgt.schema)
    from delta.tables import DeltaTable
    (DeltaTable.forName(spark, fqn).alias("t").merge(row.alias("s"), f"t.{sk} = s.{sk}")
        .whenNotMatchedInsertAll().execute())
    return True


PATTERNS = {"append": append, "overwrite": overwrite, "merge": merge, "scd2": scd2}


def load(spark, df, fqn, sttm_table, batch_id=None, src_system="", src_table=""):
    batch_id = batch_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    df = add_audit_columns(df, src_system, src_table, batch_id)
    res = PATTERNS[sttm_table["load_pattern"]](spark, df, fqn, sttm_table)
    if sttm_table.get("target_kind") == "master":
        ensure_unknown_member(spark, fqn, sttm_table)      # FKs with orphan_policy unknown_member point here
    return res
