"""Profile one bronze table to confirm what the documents claim.

Run in a Databricks notebook cell (Genie Code agent mode can run it for you):

    import sys; sys.path.append('/Workspace/<repo>/tools')
    from p2_2_profile_table import profile_table, save_result
    res = profile_table(spark,
                        table="bronze.container_track.legs",
                        candidate_keys=[["CNTR_NO", "SHPMT_ID", "LEG_NO"]],
                        key_rules={"CNTR_NO": "container_number"},
                        fk_checks=[{"column": "FROM_LOC", "parent": "bronze.container_track.locations", "parent_column": "LOC_CD"}],
                        where="IS_DELETED = 'N'",
                        sample_limit=None)
    save_result(res, "sources/S07_container_moves/02_evidence/profiling/legs.json")

Output is structured. Every check has a status (ok / warn / fail / error) and evidence.
A check that cannot run reports 'error'. It never reports a silent pass.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone


def _check(name, status, evidence, **metrics):
    return {"check": name, "status": status, "evidence": evidence, **metrics}


def profile_table(spark, table, candidate_keys=None, key_rules=None, fk_checks=None,
                  where=None, sample_limit=None, top_n=5, low_cardinality_max=50, max_topk_columns=15):
    from pyspark.sql import functions as F

    out = {"table": table, "where": where, "profiled_at": datetime.now(timezone.utc).isoformat(), "checks": [], "columns": []}
    try:
        df = spark.table(table)
        if where:
            df = df.where(where)
        if sample_limit:
            df = df.limit(int(sample_limit))
        n = df.count()
        out["row_count"] = n
    except Exception as e:  # noqa: BLE001
        out["checks"].append(_check("read_table", "error", f"{type(e).__name__}: {e}"))
        return out

    # Column stats in ONE pass (one Spark job for all columns), then top values only for
    # low-cardinality columns (at most max_topk_columns extra jobs). A 100-column table is no longer 200 jobs.
    fields = list(df.schema.fields)
    try:
        aggs = []
        for f in fields:
            c = F.col(f"`{f.name}`")
            aggs += [F.sum(c.isNull().cast("int")).alias(f"{f.name}__nulls"), F.approx_count_distinct(c).alias(f"{f.name}__d")]
        stats = df.agg(*aggs).first().asDict() if fields else {}
    except Exception as e:  # noqa: BLE001
        out["checks"].append(_check("column_stats", "error", f"{type(e).__name__}: {e}"))
        stats = {}
    topk_done = 0
    for f in fields:
        col = {"name": f.name, "type": f.dataType.simpleString()}
        if f"{f.name}__d" in stats:
            col.update(null_pct=round(100.0 * (stats[f"{f.name}__nulls"] or 0) / n, 3) if n else None,
                       approx_distinct=stats[f"{f.name}__d"], top_values=[])
            if (stats[f"{f.name}__d"] or 0) <= low_cardinality_max and topk_done < max_topk_columns:
                try:
                    c = F.col(f"`{f.name}`")
                    top = df.groupBy(c.cast("string").alias("v")).count().orderBy(F.desc("count")).limit(top_n).collect()
                    col["top_values"] = [{"value": t["v"], "count": t["count"]} for t in top]
                    topk_done += 1
                except Exception as e:  # noqa: BLE001
                    col["top_values_error"] = f"{type(e).__name__}: {e}"
        out["columns"].append(col)

    # Candidate key uniqueness
    for keys in candidate_keys or []:
        try:
            dup = df.groupBy(*keys).count().where("count > 1").count()
            nulls = df.where(" OR ".join(f"`{k}` IS NULL" for k in keys)).count()
            status = "ok" if dup == 0 and nulls == 0 else "fail"
            out["checks"].append(_check(f"candidate_key {keys}", status,
                                        f"duplicate_groups={dup} rows_with_null_key={nulls}",
                                        duplicate_groups=dup, null_rows=nulls))
        except Exception as e:  # noqa: BLE001
            out["checks"].append(_check(f"candidate_key {keys}", "error", f"{type(e).__name__}: {e}"))

    # Key format patterns before/after normalisation
    if key_rules:
        try:
            import sys
            sys.path.insert(0, os.getcwd())
            from lib.keys import normalise, key_pattern_ok
            for col, rule in key_rules.items():
                raw_bad = df.where(F.col(col).isNotNull() & ~key_pattern_ok(rule, F.col(col).cast("string"))).count()
                norm = normalise(rule, F.col(col))
                norm_bad = df.where(norm.isNotNull() & ~key_pattern_ok(rule, norm)).count()
                became_null = df.where(F.col(col).isNotNull() & norm.isNull()).count()
                status = "ok" if norm_bad == 0 else ("warn" if norm_bad / max(n, 1) < 0.001 else "fail")
                out["checks"].append(_check(f"key_pattern {col} ({rule})", status,
                                            f"bad_raw={raw_bad} bad_after_normalise={norm_bad} null_tokens={became_null}",
                                            bad_raw=raw_bad, bad_after=norm_bad, null_tokens=became_null))
        except Exception as e:  # noqa: BLE001
            out["checks"].append(_check("key_pattern", "error", f"{type(e).__name__}: {e}"))

    # Foreign key overlap (cardinality and orphans)
    for fk in fk_checks or []:
        name = f"fk {fk['column']} -> {fk['parent']}.{fk['parent_column']}"
        try:
            parent = spark.table(fk["parent"])
            orphans = df.join(parent, df[fk["column"]] == parent[fk["parent_column"]], "left_anti") \
                        .where(F.col(fk["column"]).isNotNull()).count()
            parent_dups = parent.groupBy(fk["parent_column"]).count().where("count > 1").count()
            status = "ok" if orphans == 0 and parent_dups == 0 else "warn"
            out["checks"].append(_check(name, status,
                                        f"orphan_rows={orphans} parent_key_duplicates={parent_dups} "
                                        f"(parent dups mean the relation is not N:1)",
                                        orphan_rows=orphans, parent_key_duplicates=parent_dups))
        except Exception as e:  # noqa: BLE001
            out["checks"].append(_check(name, "error", f"{type(e).__name__}: {e}"))
    return out


def save_result(res, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, default=str)
    # A short markdown summary for people
    md = [f"# Profile: {res['table']}", "", f"Rows: {res.get('row_count')}  Filter: {res.get('where')}", "",
          "| check | status | evidence |", "|---|---|---|"]
    md += [f"| {c['check']} | {c['status']} | {c['evidence']} |" for c in res["checks"]]
    with open(path.replace(".json", ".md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    return path
