# Databricks notebook source
# MAGIC %md
# MAGIC # slv_cnt_shipment_leg  (source S07_container_moves)
# MAGIC Grain: One row per container per shipment leg (container_number + leg_seq).
# MAGIC Business object: `ShipmentLeg`  Data class: `event`
# MAGIC Load pattern: `merge`  SCD: `None`
# MAGIC Generated from `sources/S07_container_moves/04_mapping/sttm.yaml` v0.3. Do not change GENERATED cells.
# COMMAND ----------
# GENERATED: parameters  [gen:7fd050e7]
dbutils.widgets.text("catalog", "dev")
dbutils.widgets.text("silver_schema", "silver")
dbutils.widgets.text("batch_id", "")
catalog = dbutils.widgets.get("catalog")
silver_schema = dbutils.widgets.get("silver_schema")
batch_id = dbutils.widgets.get("batch_id") or None
TARGET = f"{catalog}.{silver_schema}.slv_cnt_shipment_leg"
# COMMAND ----------
# GENERATED: imports and STTM  [gen:f5423618]
import sys, os, yaml
sys.path.insert(0, os.path.abspath('../../..'))   # repo root (notebook is in sources/<id>/05_build/)
from pyspark.sql import functions as F, Window
from lib.keys import normalise, lookup_sk, UNKNOWN_SK   # UNKNOWN_SK: FK value for orphans when orphan_policy is unknown_member
from lib.load_patterns import load
from lib import qa_checks as qa
with open(os.path.abspath('../04_mapping/sttm.yaml')) as f:
    STTM = yaml.safe_load(f)
T = next(x for x in STTM['tables'] if x['target_table'] == 'slv_cnt_shipment_leg')
FK = {c['target']: c['fk'] for c in T['columns'] if c.get('fk')}
ENTITY_TABLES = qa.entity_tables(catalog, silver_schema, os.path.abspath('../../..'))   # shared masters (registry/entities.yaml)
# COMMAND ----------
# GENERATED: read bronze sources (filters from STTM)  [gen:cbff2526]
l = spark.table("bronze.container_track.legs").alias("l").where("""l.IS_DELETED = 'N'""")
# COMMAND ----------
# TODO(genie): dedup rules from STTM (keep this cell short and explicit)  [spec:62e17938]
# l: latest by l._ingest_ts per CNTR_NO, SHPMT_ID, LEG_NO
bronze_count = None  # TODO(genie): row count after filter + dedup, for QA-01
# COMMAND ----------
# GENERATED: direct and key columns (raw source columns stay available for the TODO cell)  [gen:ac1d1023]
df = l
df = df.withColumn("container_number", normalise("container_number", F.expr("l.CNTR_NO")))
df = df.withColumn("shipment_id", F.expr("""trim(l.SHPMT_ID)""").cast("STRING"))
df = df.withColumn("leg_seq", F.expr("""cast(l.LEG_NO as int)""").cast("INT"))
# COMMAND ----------
# TODO(genie): derived and lookup columns. Follow standards/coding.md.  [spec:038bad3d]
# Use lib.keys.normalise for every key used in a lookup join.
#   departure_date: derived -> to_date(from_unixtime(l.ATD_TS))  (source: l.ATD_TS)
#   eta_ts: derived -> parse epoch or 'dd/MM/yyyy HH:mm' (time zone pending Q-0001)  (source: l.ETA_TS)
#   transit_days: derived -> (l.ATA_TS - l.ATD_TS) / 86400.0  (source: l.ATD_TS, l.ATA_TS)  [BUSINESS LOGIC BR-LOGI-001: must match CP4b sign-off]
df = df  # replace
# COMMAND ----------
# GENERATED: fk lookups (fk.lookup_on in the STTM -> lib.keys.lookup_sk; composite keys supported)  [gen:f6a1433b]
rejected_count = 0
# container_sk -> Container on ['container_number'] (N:1, orphans: unknown_member)
df, n = lookup_sk(df, spark.table(ENTITY_TABLES['Container']), FK['container_sk']['lookup_on'], ['container_number'], 'container_sk', 'container_sk',
                  orphan_policy='unknown_member', quarantine=f'{TARGET}_quarantine')
rejected_count += n
# origin_location_sk -> Location on ['location_code'] (N:1, orphans: unknown_member)
df, n = lookup_sk(df, spark.table(ENTITY_TABLES['Location']), FK['origin_location_sk']['lookup_on'], ['location_code'], 'location_sk', 'origin_location_sk',
                  orphan_policy='unknown_member', quarantine=f'{TARGET}_quarantine')
rejected_count += n
# destination_location_sk -> Location on ['location_code'] (N:1, orphans: unknown_member)
df, n = lookup_sk(df, spark.table(ENTITY_TABLES['Location']), FK['destination_location_sk']['lookup_on'], ['location_code'], 'location_sk', 'destination_location_sk',
                  orphan_policy='unknown_member', quarantine=f'{TARGET}_quarantine')
rejected_count += n
# COMMAND ----------
# GENERATED: technical columns  [gen:31a8e3c4]
df = df.withColumn('shipment_leg_sk', F.sha2(F.concat_ws('|', F.col('container_number').cast('string'), F.col('shipment_id').cast('string'), F.col('leg_seq').cast('string')), 256))
df = df.select(*['shipment_leg_sk', 'container_number', 'shipment_id', 'leg_seq', 'container_sk', 'origin_location_sk', 'destination_location_sk', 'departure_date', 'eta_ts', 'transit_days'])
# COMMAND ----------
# GENERATED: load  [gen:6376ec98]
load(spark, df, TARGET, T, batch_id=batch_id, src_system=STTM['source_system'], src_table='legs')
QT = T
# COMMAND ----------
# GENERATED: QA (standards/qa_checklist.md). The job fails if any check fails or cannot run.  [gen:ff63449f]
expected = None if bronze_count is None else bronze_count - rejected_count   # rows rejected by FK lookups are in quarantine
results = qa.run_table_checks(spark, QT, TARGET, bronze_count=expected, entity_tables=ENTITY_TABLES, silver_prefix=f'{catalog}.{silver_schema}')
summary = qa.write_summary(results, os.path.abspath('qa_results/slv_cnt_shipment_leg.json'), 'S07_container_moves')
qa.combine_summaries(os.path.abspath('qa_results'), 'S07_container_moves')   # checkpoint CP5 reads qa_results/summary.json
display(spark.createDataFrame([(r['check'], r['status'], str(r['evidence'])) for r in results], 'check string, status string, evidence string'))
assert summary['all_passed'], 'QA failed: see qa_results'
