"""The same contract tests for every bronze reader (feedback I-17 §2): the fake reader must not pass where the real
one would fail. The Spark reader runs only with pyspark installed and RUN_SPARK=1 (second test level); on Databricks,
run notebooks/nb_doctor for the workspace checks."""
import os

import pytest

from b2s.baseline.readers import LocalCsvReader
from b2s.demo import fake_app

CFG = {"sample_rows": 1000, "seed": 42, "topk": 5, "low_cardinality_max": 50}


def _local(tmp_path):
    fake = fake_app.make_fake_app(tmp_path / "fake")
    return LocalCsvReader(fake["bronze_root"])


def _spark(tmp_path):  # pragma: no cover - second test level
    if os.environ.get("RUN_SPARK") != "1":
        pytest.skip("Spark contract tests: set RUN_SPARK=1 with pyspark installed")
    pyspark = pytest.importorskip("pyspark")
    from pyspark.sql import SparkSession
    from b2s.baseline.readers import SparkReader
    spark = SparkSession.builder.master("local[2]").config("spark.sql.warehouse.dir", str(tmp_path / "wh")).getOrCreate()
    local = _local(tmp_path)
    for t, meta in local.meta.items():
        schema, name = t.split(".")
        spark.sql(f"CREATE DATABASE IF NOT EXISTS {schema}")
        if meta.get("view"):
            continue
        rows = local._rows(t)
        cols = [c for c, _ in local.columns(t)]
        df = spark.createDataFrame([[r.get(c) for c in cols] for r in rows] or [], schema=", ".join(
            f"`{c}` {('bigint' if 'int' in ty else 'double' if ty in ('double', 'float') else 'string')}"
            for c, ty in local.columns(t)))
        df.write.mode("overwrite").saveAsTable(f"{schema}.{name}")
    for t, meta in local.meta.items():
        if meta.get("view"):
            spark.sql(f"CREATE OR REPLACE VIEW {t} AS {meta['view']['text']}")
    return SparkReader(spark)


@pytest.fixture(params=["local", "spark"])
def reader(request, tmp_path):
    return _local(tmp_path) if request.param == "local" else _spark(tmp_path)


def test_lists_tables_and_views(reader):
    ts = reader.list_tables(["yard"])
    assert "yard.cntr_mst" in ts and "yard.v_cntr" in ts


def test_view_state_follows_base_tables(reader):
    st = reader.state("yard.v_cntr")
    assert st["base_tables"] and st["base_tables"][0].endswith("yard.cntr_mst")
    assert st["view_text"] and all(v is not None for v in st["base_versions"].values())


def test_profile_without_rows_in_python(reader):
    n, profs = reader.profile_columns("yard.cntr_mst", reader.columns("yard.cntr_mst"), CFG)
    assert n == reader.row_count("yard.cntr_mst")
    p = {x["column"]: x for x in profs}
    assert p["cntr_no"]["null_pct"] == 0.0 and p["cntr_no"]["approx_distinct"] >= n * 0.9
    assert {"family", "min", "max", "avg_len", "max_len", "kinds", "shapes", "topk"} <= set(p["cntr_no"])


def test_duplicates_and_uniqueness(reader):
    assert reader.all_rows_unique("yard.mv_leg", ["plan_id", "leg_no"])
    assert reader.duplicate_count("yard.mv_plan", ["plan_id"]) == 2


def test_content_hash_finds_the_copy(reader):
    cols = [c for c, _ in reader.columns("yard.mv_leg")]
    assert reader.content_hash("yard.mv_leg", cols) == reader.content_hash("yard.mv_leg_bkp", cols)
