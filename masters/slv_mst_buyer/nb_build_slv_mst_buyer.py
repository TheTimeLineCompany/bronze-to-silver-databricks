# Databricks notebook source
# MAGIC %md
# MAGIC # Master build: slv_mst_buyer  (entity Buyer)
# MAGIC Sources at generation time: S01_buyer_master (found again at run time).
# MAGIC Survivorship: `registry/key_normalisation.yaml` -> survivorship. Do not change GENERATED cells.
# COMMAND ----------
# GENERATED: parameters  [gen:c01a5bfa]
dbutils.widgets.text("catalog", "dev")
dbutils.widgets.text("silver_schema", "silver")
dbutils.widgets.text("batch_id", "")
catalog = dbutils.widgets.get("catalog")
silver_schema = dbutils.widgets.get("silver_schema")
batch_id = dbutils.widgets.get("batch_id") or None
ENTITY = "Buyer"
# COMMAND ----------
# GENERATED: imports  [gen:70be337f]
import sys, os
sys.path.insert(0, os.path.abspath('../..'))   # repo root (notebook is in masters/<table>/)
from lib.survivorship import build_master, feeding_sttms
from lib import qa_checks as qa
FEEDING = feeding_sttms(ENTITY, os.path.abspath('../..'))
assert FEEDING, f'no STTM maps {ENTITY}'
# COMMAND ----------
# GENERATED: build (staging tables -> survivorship -> master, unknown member seeded)  [gen:d7fd49eb]
TARGET, SPEC, expected_rows = build_master(spark, ENTITY, catalog, silver_schema, FEEDING, batch_id=batch_id, root=os.path.abspath('../..'))
# COMMAND ----------
# GENERATED: shared master tables for QA-05 (registry/entities.yaml)  [gen:387ec4c0]
ENTITY_TABLES = qa.entity_tables(catalog, silver_schema, os.path.abspath('../..'))
# COMMAND ----------
# GENERATED: QA (standards/qa_checklist.md) on the master  [gen:0979f4c8]
results = qa.run_table_checks(spark, SPEC, TARGET, bronze_count=expected_rows, entity_tables=ENTITY_TABLES, silver_prefix=f'{catalog}.{silver_schema}')
summary = qa.write_summary(results, os.path.abspath('qa_results/summary.json'), ENTITY)
display(spark.createDataFrame([(r['check'], r['status'], str(r['evidence'])) for r in results], 'check string, status string, evidence string'))
assert summary['all_passed'], 'QA failed: see qa_results'
