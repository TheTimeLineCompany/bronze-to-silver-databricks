"""Bronze discovery: the only module that touches data (PySpark). Read-only.

Cost rules (budgets in registry/ontology/information.yaml -> discovery_budgets):
  - Profiles run on a SAMPLE (sample_rows). Approximate distinct counts (HyperLogLog).
  - Patterns and top values only for a limited number of short / low-cardinality columns.
  - Exact checks run on the FULL table, but only for key candidates that survived the sample.
  - Foreign-key containment: dependent side may be sampled (a subset of an FK is still contained);
    referenced side uses its full distinct key set.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import core


def _f():
    from pyspark.sql import functions as F
    return F


def list_tables(spark, schema: str, include=None, exclude=None) -> list:
    rows = spark.sql(f"SHOW TABLES IN {schema}").collect()
    names = [f"{schema}.{r['tableName']}" for r in rows if not r["isTemporary"]]
    if include:
        names = [n for n in names if n.split(".")[-1] in include]
    if exclude:
        names = [n for n in names if n.split(".")[-1] not in exclude]
    return sorted(names)


def catalog_entry(spark, table: str) -> dict:
    df = spark.table(table)
    return {"table": table, "row_count": df.count(), "n_columns": len(df.columns),
            "columns": ", ".join(f"{f.name}:{f.dataType.simpleString()}" for f in df.schema.fields)}


def profile(spark, table: str, budget: dict, row_count: int | None = None) -> dict:
    F = _f()
    df = spark.table(table)
    n = row_count if row_count is not None else df.count()
    sample_rows = budget.get("sample_rows", 200000)
    sdf = df.sample(False, min(1.0, sample_rows / n), seed=42) if n > sample_rows else df
    sn = sdf.count()
    fields = [f for f in df.schema.fields]
    aggs = []
    for f in fields:
        c = F.col(f"`{f.name}`")
        aggs += [F.count(c).alias(f"{f.name}__nn"), F.approx_count_distinct(c, 0.03).alias(f"{f.name}__d"),
                 F.min(c).cast("string").alias(f"{f.name}__min"), F.max(c).cast("string").alias(f"{f.name}__max")]
        if core.family(f.dataType.simpleString()) == "str":
            aggs += [F.min(F.length(c)).alias(f"{f.name}__minl"), F.max(F.length(c)).alias(f"{f.name}__maxl"),
                     F.avg(F.length(c)).alias(f"{f.name}__avgl")]
    r = sdf.agg(*aggs).collect()[0].asDict() if fields else {}
    cols = []
    for f in fields:
        fam = core.family(f.dataType.simpleString())
        nn = r.get(f"{f.name}__nn") or 0
        cols.append({"table": table, "column": f.name, "type": f.dataType.simpleString(), "family": fam,
                     "sample_rows": sn, "null_pct": round(100.0 * (sn - nn) / sn, 3) if sn else None,
                     "approx_distinct": r.get(f"{f.name}__d"), "distinct_ratio": round((r.get(f"{f.name}__d") or 0) / nn, 4) if nn else 0,
                     "min": r.get(f"{f.name}__min"), "max": r.get(f"{f.name}__max"),
                     "min_len": r.get(f"{f.name}__minl"), "max_len": r.get(f"{f.name}__maxl"),
                     "avg_len": round(r[f"{f.name}__avgl"], 1) if r.get(f"{f.name}__avgl") is not None else None,
                     "patterns": [], "topk": []})
    # patterns: letter/digit shape of short string columns (key-like first)
    shape_cols = [p for p in cols if p["family"] == "str" and (p["max_len"] or 0) <= 40 and not core.is_technical(p["column"])]
    shape_cols.sort(key=lambda p: -core.key_likeness(p))
    for p in shape_cols[: budget.get("max_pattern_columns", 12)]:
        c = F.col(f"`{p['column']}`")
        shape = F.regexp_replace(F.regexp_replace(F.regexp_replace(c, "[A-Z]", "A"), "[a-z]", "a"), "[0-9]", "9")
        top = sdf.where(c.isNotNull()).groupBy(shape.alias("s")).count().orderBy(F.desc("count")).limit(3).collect()
        p["patterns"] = [t["s"] for t in top]
    # value kinds: share of values that LOOK LIKE an IP, email, UUID, URL, JSON, user agent, phone, hash/token, or text timestamp.
    # One aggregation over the sample for all string columns. Only ratios are kept, never the values (personal data).
    str_cols = [p for p in cols if p["family"] == "str"][: budget.get("max_kind_columns", 80)]
    if str_cols:
        aggs = []
        for p in str_cols:
            c = F.col(f"`{p['column']}`")
            nn = F.sum(c.isNotNull().cast("int"))
            aggs.append(nn.alias(f"{p['column']}__nn"))
            for kind, rx in core.VALUE_KINDS.items():
                aggs.append(F.sum(c.rlike(rx).cast("int")).alias(f"{p['column']}__{kind}"))
        kr = sdf.agg(*aggs).first().asDict()
        for p in str_cols:
            nn = kr.get(f"{p['column']}__nn") or 0
            if nn:
                p["kinds"] = {k: round((kr.get(f"{p['column']}__{k}") or 0) / nn, 3) for k in core.VALUE_KINDS
                              if (kr.get(f"{p['column']}__{k}") or 0) / nn >= 0.05}
    # top values: only low-cardinality columns
    low = [p for p in cols if 0 < (p["approx_distinct"] or 0) <= budget.get("low_cardinality_max", 50) and not core.is_technical(p["column"])]
    for p in low[: budget.get("max_topk_columns", 15)]:
        c = F.col(f"`{p['column']}`")
        top = sdf.where(c.isNotNull()).groupBy(c.cast("string").alias("v")).count().orderBy(F.desc("count")).limit(budget.get("topk", 20)).collect()
        p["topk"] = [[t["v"], t["count"]] for t in top]
    return {"table": table, "row_count": n, "sample_rows": sn, "profiled_at": datetime.now(timezone.utc).isoformat(), "columns": cols}


def verify_unique(spark, table: str, cols: list) -> bool:
    """Exact on the full table: no NULL in any key column and no duplicate combination."""
    F = _f()
    df = spark.table(table).select(*[F.col(f"`{c}`") for c in cols])
    if df.where(" OR ".join(f"`{c}` IS NULL" for c in cols)).limit(1).count():
        return False
    return df.groupBy(*cols).count().where("count > 1").limit(1).count() == 0


def _norm(c):
    F = _f()
    return F.upper(F.regexp_replace(F.trim(c.cast("string")), r"[\s\-_./]", ""))


def containment(spark, cand: dict, budget: dict) -> dict:
    """Distinct-value containment of dep.col in ref.col, raw and after normalisation, plus reverse coverage."""
    F = _f()
    dep = spark.table(cand["dep_table"])
    dn = budget.get("link_dep_sample_rows", 500000)
    total = dep.count()
    if total > dn:
        dep = dep.sample(False, dn / total, seed=7)
    dcols = [c for c in cand["dep_column"].split("+") if c]
    rcols = [c for c in cand["ref_column"].split("+") if c]
    SEP = "\u001f"                                   # unit separator: cannot occur in normal key values

    def tup(df, cols, norm=False):
        parts = [(_norm(F.col(f"`{c}`")) if norm else F.col(f"`{c}`").cast("string")) for c in cols]
        nn = None
        for c in cols:                                # a composite FK with any NULL part references nothing (MATCH SIMPLE)
            x = F.col(f"`{c}`").isNotNull()
            nn = x if nn is None else (nn & x)
        return df.where(nn).select(F.concat_ws(SEP, *parts).alias("v")).distinct()
    d = tup(dep, dcols)
    r = tup(spark.table(cand["ref_table"]), rcols)
    nd, nr = d.count(), r.count()
    raw = d.join(r, "v", "left_semi").count()
    dN = tup(dep, dcols, norm=True)
    rN = tup(spark.table(cand["ref_table"]), rcols, norm=True)
    ndN = dN.count()
    norm = dN.join(rN, "v", "left_semi").count()
    cover = r.join(d, "v", "left_semi").count()
    miss = [x["v"].replace(SEP, "|") for x in d.join(r, "v", "left_anti").limit(5).collect()]
    return {**cand, "dep_distinct": nd, "ref_distinct": nr, "containment_raw": round(raw / nd, 4) if nd else 0,
            "containment_norm": round(norm / ndN, 4) if ndN else 0, "coverage": round(cover / nr, 4) if nr else 0,
            "missing_examples": ", ".join(map(str, miss))}
