"""Bronze readers. The engine sees only this interface; it never reads a whole table into an agent's context.

BronzeReader
  list_tables(schemas) -> ["schema.table", ...]           tables and views, sorted
  columns(table) -> [(name, type), ...]
  row_count(table) -> int
  sample(table, n, seed) -> list[dict]                       deterministic for the same data and seed
  all_rows_unique(table, cols) -> bool                       exact, on the FULL table: no NULL and no duplicate
  duplicate_count(table, cols) -> int                        rows that break uniqueness (NULL key parts count)
  content_hash(table) -> str                                 order-independent hash of all rows (copy detection)
  state(table) -> {"version", "view_text", "base_tables"}    for fingerprints (DB-07)
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
from pathlib import Path


class BronzeReader:  # pragma: no cover - interface
    def list_tables(self, schemas: list[str]) -> list[str]: ...
    def columns(self, table: str) -> list[tuple[str, str]]: ...
    def row_count(self, table: str) -> int: ...
    def sample(self, table: str, n: int, seed: int) -> list[dict]: ...
    def all_rows_unique(self, table: str, cols: list[str]) -> bool: ...
    def duplicate_count(self, table: str, cols: list[str]) -> int: ...
    def content_hash(self, table: str) -> str: ...
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
            base = self._rows(view["base_tables"][0])
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

    def content_hash(self, table):
        cols = [c for c, _ in self.columns(table)]
        lines = sorted(json.dumps([r.get(c) for c in cols], default=str) for r in self._rows(table))
        return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()

    def state(self, table):
        view = self.meta[table].get("view")
        if view:
            return {"version": None, "view_text": view["text"], "base_tables": view["base_tables"],
                    "base_versions": {b: self.state(b)["version"] for b in view["base_tables"]}}
        schema, t = table.split(".")
        data = (self.root / schema / f"{t}.csv").read_bytes()
        return {"version": hashlib.sha256(data).hexdigest()[:16], "view_text": None, "base_tables": []}


class SparkReader(BronzeReader):  # pragma: no cover - runs on Databricks only
    """Databricks reader. Spark Connect safe: DataFrame API and SQL only (no sparkContext, RDD or JVM calls).

    check K-04: the hash sample must return the same rows through a view and its base table.
    check K-05: system lineage tables for base tables of views (here: information_schema view text only).
    """

    def __init__(self, spark, catalog: str | None = None):
        self.spark = spark
        self.catalog = catalog

    def _fq(self, table):
        return f"{self.catalog}.{table}" if self.catalog else table

    def list_tables(self, schemas):
        out = []
        for s in schemas:
            fq = f"{self.catalog}.{s}" if self.catalog else s
            for r in self.spark.sql(f"SHOW TABLES IN {fq}").collect():
                if not r["isTemporary"]:
                    out.append(f"{s}.{r['tableName']}")
        return sorted(out)

    def columns(self, table):
        return [(f.name, f.dataType.simpleString()) for f in self.spark.table(self._fq(table)).schema.fields]

    def row_count(self, table):
        return self.spark.table(self._fq(table)).count()

    def _declared_pk(self, table) -> list[str]:
        schema, t = table.split(".")
        cat = self.catalog or self.spark.sql("SELECT current_catalog() c").collect()[0]["c"]
        try:
            rows = self.spark.sql(
                f"SELECT k.column_name FROM {cat}.information_schema.table_constraints c "
                f"JOIN {cat}.information_schema.key_column_usage k USING (constraint_catalog, constraint_schema, constraint_name) "
                f"WHERE c.table_schema = '{schema}' AND c.table_name = '{t}' AND c.constraint_type = 'PRIMARY KEY' "
                f"ORDER BY k.ordinal_position").collect()
            return [r["column_name"] for r in rows]
        except Exception:
            return []

    def sample(self, table, n, seed):
        from pyspark.sql import functions as F
        df = self.spark.table(self._fq(table))
        total = df.count()
        if total <= n:
            return [r.asDict() for r in df.collect()]
        cols = self._declared_pk(table) or df.columns
        h = F.abs(F.xxhash64(F.lit(seed), *[F.col(c) for c in cols])) % F.lit(1_000_000)
        frac = int(1_000_000 * n / total) + 1
        return [r.asDict() for r in df.where(h < frac).limit(n).collect()]

    def duplicate_count(self, table, cols):
        from pyspark.sql import functions as F
        df = self.spark.table(self._fq(table))
        nulls = df.where(" OR ".join(f"`{c}` IS NULL" for c in cols)).count()
        total_nn = df.count() - nulls
        distinct = df.dropna(subset=cols).select(*cols).distinct().count()
        return nulls + (total_nn - distinct)

    def all_rows_unique(self, table, cols):
        return self.duplicate_count(table, cols) == 0

    def content_hash(self, table):
        from pyspark.sql import functions as F
        df = self.spark.table(self._fq(table))
        r = df.select(F.sum(F.xxhash64(*df.columns).cast("decimal(38,0)")).alias("s"), F.count("*").alias("n")).collect()[0]
        return f"xxhash64sum:{r['s']}:{r['n']}"

    def state(self, table):
        schema, t = table.split(".")
        cat = self.catalog or self.spark.sql("SELECT current_catalog() c").collect()[0]["c"]
        v = self.spark.sql(f"SELECT view_definition FROM {cat}.information_schema.views "
                           f"WHERE table_schema = '{schema}' AND table_name = '{t}'").collect()
        if v:
            return {"version": None, "view_text": v[0]["view_definition"], "base_tables": []}
        hist = self.spark.sql(f"DESCRIBE HISTORY {self._fq(table)} LIMIT 1").collect()
        return {"version": hist[0]["version"] if hist else None, "view_text": None, "base_tables": []}
