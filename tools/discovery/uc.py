"""Bronze discovery: Unity Catalog metadata and lineage (no data is read here).

Every function returns plain dicts and NEVER raises: when a view, system table, or privilege is missing,
the section is recorded as {"available": False, "reason": "..."} and discovery continues.

Sources (Databricks documentation):
  <catalog>.information_schema: TABLES, COLUMNS, TABLE_TAGS, COLUMN_TAGS, TABLE_CONSTRAINTS,
      KEY_COLUMN_USAGE, REFERENTIAL_CONSTRAINTS, ROW_FILTERS, COLUMN_MASKS        (per catalog)
  system.information_schema: the same views across all catalogs                    (wider search)
  DESCRIBE DETAIL / DESCRIBE HISTORY                                              (format, size, writers)
  SHOW STATISTICS <t> FOR ALL COLUMNS AS JSON                                    (exact NDV / nulls if collected)
  system.access.table_lineage, system.access.column_lineage                       (who writes / reads, derived-from)
Identifiers in information_schema are lower case.
"""
from __future__ import annotations

import json


def _rows(spark, sql):
    return [r.asDict(recursive=True) for r in spark.sql(sql).collect()]


def _safe(fn):
    def wrap(*a, **k):
        try:
            return {"available": True, "rows": fn(*a, **k)}
        except Exception as e:  # noqa: BLE001  never fail discovery on metadata
            return {"available": False, "reason": f"{type(e).__name__}: {str(e).splitlines()[0][:200]}", "rows": []}
    return wrap


def _parts(full):
    p = full.split(".")
    return (p[0], p[1], p[2]) if len(p) == 3 else (None, p[0], p[1])


def _in(values):
    return ", ".join("'" + str(v).lower().replace("'", "''") + "'" for v in values) or "''"


def _cols(spark, view):
    return {c.lower() for c in spark.table(view).columns}


@_safe
def tables_meta(spark, catalog, schema, names):
    v = f"{catalog}.information_schema.tables"
    have = _cols(spark, v)
    want = [c for c in ("table_name", "table_type", "comment", "table_owner", "created", "created_by", "last_altered",
                        "last_altered_by", "data_source_format", "storage_path") if c in have]
    return _rows(spark, f"SELECT {', '.join(want)} FROM {v} WHERE table_schema = '{schema.lower()}' AND table_name IN ({_in(names)})")


@_safe
def columns_meta(spark, catalog, schema, names):
    v = f"{catalog}.information_schema.columns"
    have = _cols(spark, v)
    want = [c for c in ("table_name", "column_name", "ordinal_position", "is_nullable", "full_data_type", "data_type", "comment") if c in have]
    return _rows(spark, f"SELECT {', '.join(want)} FROM {v} WHERE table_schema = '{schema.lower()}' AND table_name IN ({_in(names)})")


@_safe
def tags(spark, catalog, schema, names):
    out = []
    for kind, v in (("table", "table_tags"), ("column", "column_tags")):
        cols = _cols(spark, f"{catalog}.information_schema.{v}")
        colsel = "column_name" if "column_name" in cols else "NULL AS column_name"
        out += [{**r, "level": kind} for r in _rows(spark, f"SELECT table_name, {colsel}, tag_name, tag_value FROM {catalog}.information_schema.{v} "
                                                             f"WHERE schema_name = '{schema.lower()}' AND table_name IN ({_in(names)})")]
    return out


@_safe
def masks_and_filters(spark, catalog, schema, names):
    out = []
    for v, kind in (("row_filters", "row_filter"), ("column_masks", "column_mask")):
        cols = _cols(spark, f"{catalog}.information_schema.{v}")
        tcol = "table_schema" if "table_schema" in cols else "schema_name"
        sel = "column_name" if "column_name" in cols else "NULL AS column_name"
        out += [{**r, "kind": kind} for r in _rows(spark, f"SELECT table_name, {sel} FROM {catalog}.information_schema.{v} "
                                                           f"WHERE {tcol} = '{schema.lower()}' AND table_name IN ({_in(names)})")]
    return out


@_safe
def constraints(spark, catalog, schema, names):
    """Declared PRIMARY KEY / UNIQUE / FOREIGN KEY constraints on the source tables (informational in Databricks)."""
    tc = _rows(spark, f"SELECT constraint_name, table_name, constraint_type FROM {catalog}.information_schema.table_constraints "
                      f"WHERE table_schema = '{schema.lower()}' AND table_name IN ({_in(names)}) "
                      f"AND constraint_type IN ('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY')")
    if not tc:
        return []
    kcu = _rows(spark, f"SELECT constraint_name, table_name, column_name, ordinal_position FROM {catalog}.information_schema.key_column_usage "
                       f"WHERE table_schema = '{schema.lower()}' AND table_name IN ({_in(names)})")
    rc = _rows(spark, f"SELECT constraint_name, unique_constraint_catalog, unique_constraint_schema, unique_constraint_name "
                      f"FROM {catalog}.information_schema.referential_constraints WHERE constraint_schema = '{schema.lower()}'")
    rc_by = {r["constraint_name"]: r for r in rc}
    out = []
    for c in tc:
        cols = [k["column_name"] for k in sorted((k for k in kcu if k["constraint_name"] == c["constraint_name"]), key=lambda k: k["ordinal_position"])]
        item = {"table": c["table_name"], "type": c["constraint_type"], "name": c["constraint_name"], "columns": cols}
        if c["constraint_type"] == "FOREIGN KEY" and c["constraint_name"] in rc_by:
            u = rc_by[c["constraint_name"]]
            ref = _rows(spark, f"SELECT table_schema, table_name, column_name, ordinal_position FROM "
                               f"{u['unique_constraint_catalog']}.information_schema.key_column_usage "
                               f"WHERE constraint_name = '{u['unique_constraint_name']}' AND constraint_schema = '{u['unique_constraint_schema']}'")
            ref = sorted(ref, key=lambda k: k["ordinal_position"])
            if ref:
                item["ref_table"] = f"{u['unique_constraint_catalog']}.{ref[0]['table_schema']}.{ref[0]['table_name']}"
                item["ref_columns"] = [k["column_name"] for k in ref]
        out.append(item)
    return out


@_safe
def detail_and_history(spark, full_names, history_rows=20):
    out = []
    for t in full_names:
        d = spark.sql(f"DESCRIBE DETAIL {t}").first().asDict()
        props = d.get("properties") or {}
        h = []
        try:
            h = [r.asDict() for r in spark.sql(f"DESCRIBE HISTORY {t} LIMIT {int(history_rows)}").collect()]
        except Exception:  # noqa: BLE001  views and non-Delta tables have no history
            pass
        ops = {}
        for r in h:
            ops[r.get("operation")] = ops.get(r.get("operation"), 0) + 1
        jobs = sorted({str((r.get("job") or {}).get("jobId")) for r in h if r.get("job")} - {"None"})
        times = sorted(str(r.get("timestamp")) for r in h if r.get("timestamp"))
        out.append({"table": t, "format": d.get("format"), "size_bytes": d.get("sizeInBytes"), "num_files": d.get("numFiles"),
                    "last_modified": str(d.get("lastModified")), "partition_columns": ", ".join(d.get("partitionColumns") or []),
                    "clustering_columns": ", ".join(d.get("clusteringColumns") or []),
                    "change_data_feed": str(props.get("delta.enableChangeDataFeed", "false")).lower() == "true",
                    "recent_operations": ", ".join(f"{k}x{v}" for k, v in sorted(ops.items(), key=lambda x: -x[1])),
                    "writer_job_ids": ", ".join(jobs), "first_seen_in_history": times[0] if times else None,
                    "last_write": times[-1] if times else None})
    return out


@_safe
def column_stats(spark, full_names):
    """SHOW STATISTICS ... AS JSON: exact distinct_count / num_nulls when statistics were collected (ANALYZE or Auto Stats)."""
    out = []
    for t in full_names:
        try:
            js = json.loads(spark.sql(f"SHOW STATISTICS {t} FOR ALL COLUMNS AS JSON").first()[0])
        except Exception:  # noqa: BLE001
            continue
        st = js.get("statistics") or js
        cs = st.get("column_statistics") or {}
        items = cs.items() if isinstance(cs, dict) else ((c.get("column_name") or c.get("name"), c) for c in cs)
        for col, s in items:
            if s and s.get("distinct_count") is not None:
                out.append({"table": t, "column": col, "distinct_count": s.get("distinct_count"), "num_nulls": s.get("num_nulls"),
                            "min": s.get("min"), "max": s.get("max"), "num_rows": st.get("num_rows"),
                            "collection_source": st.get("collection_source")})
    return out


@_safe
def lineage(spark, full_names, days=90):
    """Table lineage around the source tables: who writes them (upstream) and what reads them (downstream)."""
    names = _in(full_names)
    return _rows(spark, f"""
        SELECT source_table_full_name, source_path, source_type, target_table_full_name, target_path, target_type,
               entity_type, CAST(entity_metadata.job_info.job_id AS STRING) AS job_id,
               CAST(entity_metadata.dlt_pipeline_info.dlt_pipeline_id AS STRING) AS pipeline_id,
               CAST(entity_metadata.notebook_id AS STRING) AS notebook_id,
               count(*) AS events, max(event_time) AS last_event
        FROM system.access.table_lineage
        WHERE event_date >= date_sub(current_date(), {int(days)})
          AND (lower(source_table_full_name) IN ({names}) OR lower(target_table_full_name) IN ({names}))
        GROUP BY ALL""")


@_safe
def column_lineage(spark, full_names, days=90):
    names = _in(full_names)
    return _rows(spark, f"""
        SELECT source_table_full_name, source_column_name, target_table_full_name, target_column_name,
               entity_type, count(*) AS events
        FROM system.access.column_lineage
        WHERE event_date >= date_sub(current_date(), {int(days)})
          AND lower(target_table_full_name) IN ({names}) AND source_table_full_name IS NOT NULL
        GROUP BY ALL""")


@_safe
def related_candidates(spark, catalogs, exclude_schema, tokens, key_columns, budget):
    """Tables OUTSIDE the source schema that may belong to this source: matching name tokens or sharing key column names.
    Uses system.information_schema.columns (all catalogs you can read), filtered to the given catalogs."""
    cats = _in(catalogs)
    tok = [t for t in tokens if len(t) >= 3][:20]
    name_like = " OR ".join(f"table_name LIKE '%{t.lower()}%'" for t in tok) or "false"
    keys = _in(key_columns)
    rows = _rows(spark, f"""
        SELECT table_catalog, table_schema, table_name,
               max(CASE WHEN {name_like} THEN 1 ELSE 0 END) AS name_hit,
               count(DISTINCT CASE WHEN lower(column_name) IN ({keys}) THEN lower(column_name) END) AS key_cols_shared,
               collect_set(CASE WHEN lower(column_name) IN ({keys}) THEN column_name END) AS shared_columns
        FROM system.information_schema.columns
        WHERE table_catalog IN ({cats}) AND table_schema <> '{exclude_schema.lower()}' AND table_schema <> 'information_schema'
        GROUP BY table_catalog, table_schema, table_name
        HAVING name_hit = 1 OR key_cols_shared >= {int(budget.get('related_min_shared_keys', 2))}""")
    return rows


def harvest(spark, full_names, budget):
    """All metadata sections for one source. Returns {section: {available, rows|reason}}."""
    if not full_names:
        return {}
    cat, sch, _ = _parts(full_names[0])
    cat = cat or spark.catalog.currentCatalog()
    names = [_parts(t)[2] for t in full_names]
    return {"tables": tables_meta(spark, cat, sch, names), "columns": columns_meta(spark, cat, sch, names),
            "tags": tags(spark, cat, sch, names), "masks_and_filters": masks_and_filters(spark, cat, sch, names),
            "constraints": constraints(spark, cat, sch, names), "detail_history": detail_and_history(spark, full_names),
            "column_stats": column_stats(spark, full_names),
            "lineage": lineage(spark, [f"{cat}.{sch}.{n}" for n in names], budget.get("lineage_days", 90)),
            "column_lineage": column_lineage(spark, [f"{cat}.{sch}.{n}" for n in names], budget.get("lineage_days", 90))}
