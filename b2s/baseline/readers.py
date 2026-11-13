"""Bronze readers. The engine sees only this interface; it never reads a whole table into an agent's context.

BronzeReader (every reader implements ALL of it; tests/test_reader_contract.py runs the same tests on each)
  list_tables(schemas) -> ["schema.table", ...]           tables and views, sorted
  columns(table) -> [(name, type), ...]
  row_count(table) -> int
  profile_columns(table, columns, cfg) -> (rows_profiled, [column profiles])
        computed where the data is (Spark: aggregations, only results reach the driver; never rows as Python lists)
  all_rows_unique(table, cols) -> bool        exact, on the FULL table: no NULL and no duplicate
  duplicate_count(table, cols) -> int         rows that break uniqueness (NULL key parts count); one pass
  content_hash(table, cols=None) -> str       order-independent hash of all rows over cols (copy detection)
  state(table) -> {"version", "view_text", "base_tables", "base_versions", "readable", "row_count"?}
        views are followed to their base tables with the shared parser (b2s.baseline.views); a table whose history
        cannot be read gets version None and its row count as the change signal

Feature support (feedback I-17 section 2). Status: LocalCsvReader verified locally; SparkReader NOT RUN on a workspace.
| Feature                                    | LocalCsvReader | SparkReader         |
|--------------------------------------------|----------------|---------------------|
| views -> base tables, views over views      | yes            | yes (not run)       |
| history not readable -> row_count signal    | n/a            | yes (not run)       |
| profile without collecting rows             | in memory      | yes (not run)       |
| names quoted with backticks                 | n/a            | yes (not run)       |
| one pass for duplicate_count                | yes            | yes (not run)       |
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
from pathlib import Path

from .profile import profile_columns as _profile_rows
from .views import base_tables, quote, split_name


class BronzeReader:  # pragma: no cover - interface
    def list_tables(self, schemas: list[str]) -> list[str]: ...
    def columns(self, table: str) -> list[tuple[str, str]]: ...
    def row_count(self, table: str) -> int: ...
    def profile_columns(self, table: str, columns: list, cfg: dict) -> tuple: ...
    def all_rows_unique(self, table: str, cols: list[str]) -> bool: ...
    def duplicate_count(self, table: str, cols: list[str]) -> int: ...
    def content_hash(self, table: str, cols: list | None = None) -> str: ...
    def state(self, table: str) -> dict: ...


def _typed(v: str, typ: str):
    if v == "" or v is None:
        return None
    t = typ.lower()
    try:
        if any(x in t for x in ("int", "long", "short", "byte")):
            return int(v)
        if any(x in t for x in ("double", "float", "decimal")):
            return float(v)
    except ValueError:
        return v
    return v


class LocalCsvReader(BronzeReader):
    """Reads the fake application written by b2s.demo.fake_app (bronze/schema.json + <schema>/<table>.csv)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.meta = json.loads((self.root / "schema.json").read_text(encoding="utf-8"))["tables"]
        self._cache: dict[str, list[dict]] = {}

    def list_tables(self, schemas):
        return sorted(t for t in self.meta if t.split(".")[0] in set(schemas))

    def columns(self, table):
        return [tuple(c) for c in self.meta[table]["columns"]]

    def _rows(self, table) -> list[dict]:
        if table in self._cache:
            return self._cache[table]
        view = self.meta[table].get("view")
        if view:
            base = self._rows(base_tables(view["text"], table.split(".")[0])[0])
            rows = [{c: r.get(c) for c in view["columns"]} for r in base]
        else:
            types = dict(self.columns(table))
            schema, t = table.split(".")
            with open(self.root / schema / f"{t}.csv", newline="", encoding="utf-8") as f:
                rows = [{k: _typed(v, types.get(k, "string")) for k, v in r.items()} for r in csv.DictReader(f)]
        self._cache[table] = rows
        return rows

    def row_count(self, table):
        return len(self._rows(table))

    def sample(self, table, n, seed):
        rows = self._rows(table)
        if len(rows) <= n:
            return list(rows)
        idx = sorted(random.Random(seed).sample(range(len(rows)), n))
        return [rows[i] for i in idx]

    def profile_columns(self, table, columns, cfg):
        rows = self.sample(table, int(cfg.get("sample_rows", 5_000_000)), int(cfg.get("seed", 42)))
        return len(rows), _profile_rows(rows, columns, topk=int(cfg.get("topk", 20)))

    def all_rows_unique(self, table, cols):
        return self.duplicate_count(table, cols) == 0

    def duplicate_count(self, table, cols):
        seen, dup = set(), 0
        for r in self._rows(table):
            k = tuple(r.get(c) for c in cols)
            if any(v is None for v in k) or k in seen:
                dup += 1
            seen.add(k)
        return dup

    def content_hash(self, table, cols=None):
        cols = cols or [c for c, _ in self.columns(table)]
        lines = sorted(json.dumps([r.get(c) for c in cols], default=str) for r in self._rows(table))
        return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()

    def state(self, table):
        view = self.meta[table].get("view")
        if view:
            bases = base_tables(view["text"], table.split(".")[0])
            return {"version": None, "view_text": view["text"], "base_tables": bases,
                    "base_versions": {b: self.state(b)["version"] for b in bases}, "readable": True}
        schema, t = table.split(".")
        data = (self.root / schema / f"{t}.csv").read_bytes()
        return {"version": hashlib.sha256(data).hexdigest()[:16], "view_text": None, "base_tables": [],
                "readable": True}


class SparkReader(BronzeReader):  # pragma: no cover - runs on Databricks only (status: NOT RUN on a workspace yet)
    """Databricks reader. Spark Connect safe: DataFrame API and SQL only (no sparkContext, RDD or JVM calls).
    Profiles are computed with aggregations in Spark; only the results reach the driver.

    check K-04: the hash sample must return the same rows through a view and its base table.
    """

    def __init__(self, spark, catalog: str | None = None):
        self.spark = spark
        self.catalog = catalog

    # ---- names
    def _cat(self):
        return self.catalog or self.spark.sql("SELECT current_catalog() c").collect()[0]["c"]

    def _fq(self, table):
        parts = split_name(table)
        if len(parts) == 2 and self.catalog:
            parts = [self.catalog] + parts
        return ".".join("`" + p.replace("`", "``") + "`" for p in parts)

    def _df(self, table):
        return self.spark.table(self._fq(table))

    def list_tables(self, schemas):
        out = []
        for s in schemas:
            fq = quote(f"{self.catalog}.{s}") if self.catalog else quote(s)
            for r in self.spark.sql(f"SHOW TABLES IN {fq}").collect():
                if not r["isTemporary"]:
                    out.append(f"{s}.{r['tableName']}")
        return sorted(out)

    def columns(self, table):
        return [(f.name, f.dataType.simpleString()) for f in self._df(table).schema.fields]

    def row_count(self, table):
        return self._df(table).count()

    def _declared_pk(self, table) -> list[str]:
        schema, t = split_name(table)[-2:]
        cat = quote(self._cat())
        try:
            rows = self.spark.sql(
                f"SELECT k.column_name FROM {cat}.information_schema.table_constraints c "
                f"JOIN {cat}.information_schema.key_column_usage k "
                f"USING (constraint_catalog, constraint_schema, constraint_name) "
                f"WHERE c.table_schema = '{schema}' AND c.table_name = '{t}' AND c.constraint_type = 'PRIMARY KEY' "
                f"ORDER BY k.ordinal_position").collect()
            return [r["column_name"] for r in rows]
        except Exception:
            return []

    def _sampled(self, table, n, seed):
        from pyspark.sql import functions as F
        df = self._df(table)
        total = df.count()
        if total <= n:
            return df, total
        cols = self._declared_pk(table) or df.columns
        h = F.abs(F.xxhash64(F.lit(seed), *[F.col(f"`{c}`") for c in cols])) % F.lit(1_000_000)
        return df.where(h < F.lit(int(1_000_000 * n / total) + 1)), total

    def profile_columns(self, table, columns, cfg):
        """One aggregation pass for counts, distincts, min/max, lengths and value kinds; small group-bys for the top
        values of low-cardinality columns and the shapes of short string columns. Nothing row-level is collected."""
        from pyspark.sql import functions as F
        from .rules import VALUE_KINDS, family
        sdf, _ = self._sampled(table, int(cfg.get("sample_rows", 5_000_000)), int(cfg.get("seed", 42)))
        aggs, fam = [F.count(F.lit(1)).alias("__n")], {}
        for i, (c, t) in enumerate(columns):
            col, fam[c] = F.col(f"`{c}`"), family(t)
            s = col.cast("string")
            aggs += [F.count(col).alias(f"nn{i}"), F.approx_count_distinct(col).alias(f"d{i}"),
                     F.min(col).alias(f"mi{i}"), F.max(col).alias(f"ma{i}"),
                     F.avg(F.length(s)).alias(f"al{i}"), F.max(F.length(s)).alias(f"ml{i}")]
            if fam[c] == "str":
                aggs += [F.sum(F.when(s.rlike(rx), 1).otherwise(0)).alias(f"k{i}_{k}") for k, rx in VALUE_KINDS.items()]
        r = sdf.agg(*aggs).collect()[0]
        n = r["__n"]
        profs = []
        for i, (c, t) in enumerate(columns):
            nn = r[f"nn{i}"] or 0
            p = {"column": c, "type": t, "family": fam[c],
                 "null_pct": round(100.0 * (n - nn) / n, 3) if n else 0.0,
                 "approx_distinct": r[f"d{i}"] or 0, "min": r[f"mi{i}"], "max": r[f"ma{i}"],
                 "avg_len": round(r[f"al{i}"], 2) if r[f"al{i}"] is not None else None, "max_len": r[f"ml{i}"],
                 "kinds": {}, "shapes": [], "topk": []}
            if fam[c] == "str" and nn:
                p["kinds"] = {k: round(r[f"k{i}_{k}"] / nn, 3) for k in VALUE_KINDS if r[f"k{i}_{k}"]}
            profs.append(p)
        low = int(cfg.get("low_cardinality_max", 50))
        for p in [p for p in profs if 0 < p["approx_distinct"] <= low][: int(cfg.get("max_topk_columns", 15))]:
            col = F.col(f"`{p['column']}`")
            p["topk"] = [[x[0], x[1]] for x in sdf.where(col.isNotNull()).groupBy(col).count()
                         .orderBy(F.desc("count")).limit(int(cfg.get("topk", 20))).collect()]
        shape_cols = [p for p in profs if p["family"] == "str" and (p["max_len"] or 99) <= 40]
        for p in shape_cols[: int(cfg.get("max_pattern_columns", 12))]:
            s = F.col(f"`{p['column']}`").cast("string")
            sh = F.regexp_replace(s, "[0-9]", "9")
            sh = F.regexp_replace(F.regexp_replace(sh, "[A-Z]", "A"), "[a-z]", "a")
            sh = F.regexp_replace(sh, "(.)\\1{5,}", "$1$1$1$1$1+")
            p["shapes"] = [x[0] for x in sdf.where(s.isNotNull()).groupBy(sh.alias("sh")).count()
                           .orderBy(F.desc("count")).limit(3).collect()]
        return n, profs

    def duplicate_count(self, table, cols):
        """One pass: rows minus distinct full (no NULL) key combinations. NULL key parts count as duplicates."""
        from pyspark.sql import functions as F
        r = self._df(table).agg(F.count(F.lit(1)).alias("n"),
                                F.countDistinct(*[F.col(f"`{c}`") for c in cols]).alias("d")).collect()[0]
        return r["n"] - r["d"]

    def all_rows_unique(self, table, cols):
        return self.duplicate_count(table, cols) == 0

    def content_hash(self, table, cols=None):
        from pyspark.sql import functions as F
        df = self._df(table)
        cols = cols or df.columns
        r = df.select(F.sum(F.xxhash64(*[F.col(f"`{c}`") for c in cols]).cast("decimal(38,0)")).alias("s"),
                      F.count("*").alias("n")).collect()[0]
        return f"xxhash64sum:{r['s']}:{r['n']}"

    def _view_text(self, table):
        """information_schema.views first; it can return nothing for some views, so fall back to DESCRIBE EXTENDED."""
        schema, t = split_name(table)[-2:]
        try:
            v = self.spark.sql(f"SELECT view_definition FROM {quote(self._cat())}.information_schema.views "
                               f"WHERE table_schema = '{schema}' AND table_name = '{t}'").collect()
            if v and v[0]["view_definition"]:
                return v[0]["view_definition"]
        except Exception:
            pass
        try:
            rows = {r["col_name"]: r["data_type"]
                    for r in self.spark.sql(f"DESCRIBE TABLE EXTENDED {self._fq(table)}").collect()}
            if (rows.get("Type") or "").upper() == "VIEW":
                return rows.get("View Text") or ""
        except Exception:
            pass
        return None

    def state(self, table, _seen=None):
        """Views: view text + the state of every base table (views over views followed). A table whose history the
        user cannot read (e.g. only the view is granted) gets version None and its row count as the change signal."""
        _seen = set(_seen or ())
        text = self._view_text(table)
        if text is not None:
            schema = split_name(table)[-2]
            bases = [b for b in base_tables(text, schema) if b not in _seen]
            _seen |= set(bases) | {table}
            bv = {b: self.state(b, _seen).get("version") for b in bases}
            st = {"version": None, "view_text": text, "base_tables": bases, "base_versions": bv, "readable": True}
            if any(v is None for v in bv.values()):
                st["row_count"] = self.row_count(table)
            return st
        try:
            hist = self.spark.sql(f"DESCRIBE HISTORY {self._fq(table)} LIMIT 1").collect()
            return {"version": hist[0]["version"] if hist else None, "view_text": None, "base_tables": [],
                    "readable": True}
        except Exception:
            return {"version": None, "view_text": None, "base_tables": [], "readable": False,
                    "row_count": self.row_count(table)}
