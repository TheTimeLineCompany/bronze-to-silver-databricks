#!/usr/bin/env python3
"""P5.4 Generate the build notebook for ONE shared master (survivorship across sources).

    python tools/p5_4_gen_master_build.py Buyer
    -> masters/slv_mst_buyer/nb_build_slv_mst_buyer.py

The notebook finds the feeding sources at run time (every STTM whose table has conformed_entity = <Entity>),
reads their staging tables, applies registry/key_normalisation.yaml -> survivorship.<Entity>, loads the master
(scd2 or merge), seeds the unknown member, and writes QA to masters/<table>/qa_results/summary.json.
Run it AFTER the source notebooks that feed the entity, and BEFORE process tables that point to the master.
Safe to re-run: the same merge rules as tools/p5_1_gen_notebook.py (TODO cells are kept).
"""
from __future__ import annotations

import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
import p5_1_gen_notebook as g  # noqa: E402
from lib.survivorship import feeding_sttms  # noqa: E402

SEP = g.SEP


def render(entity: str, ent: dict, sources: list) -> str:
    tbl = ent["target_table"]
    cells = [
        "# Databricks notebook source\n# MAGIC %md\n"
        f"# MAGIC # Master build: {tbl}  (entity {entity})\n"
        f"# MAGIC Sources at generation time: {', '.join(sources) or 'none yet'} (found again at run time).\n"
        "# MAGIC Survivorship: `registry/key_normalisation.yaml` -> survivorship. Do not change GENERATED cells.",
        "\n".join(["# GENERATED: parameters",
                   'dbutils.widgets.text("catalog", "dev")', 'dbutils.widgets.text("silver_schema", "silver")', 'dbutils.widgets.text("batch_id", "")',
                   'catalog = dbutils.widgets.get("catalog")', 'silver_schema = dbutils.widgets.get("silver_schema")',
                   'batch_id = dbutils.widgets.get("batch_id") or None', f'ENTITY = "{entity}"']),
        "\n".join(["# GENERATED: imports",
                   "import sys, os",
                   "sys.path.insert(0, os.path.abspath('../..'))   # repo root (notebook is in masters/<table>/)",
                   "from lib.survivorship import build_master, feeding_sttms",
                   "from lib import qa_checks as qa",
                   "FEEDING = feeding_sttms(ENTITY, os.path.abspath('../..'))",
                   "assert FEEDING, f'no STTM maps {ENTITY}'"]),
        "\n".join(["# GENERATED: build (staging tables -> survivorship -> master, unknown member seeded)",
                   "TARGET, SPEC, expected_rows = build_master(spark, ENTITY, catalog, silver_schema, FEEDING, batch_id=batch_id, root=os.path.abspath('../..'))"]),
        "\n".join(["# GENERATED: shared master tables for QA-05 (registry/entities.yaml)",
                   "ENTITY_TABLES = qa.entity_tables(catalog, silver_schema, os.path.abspath('../..'))"]),
        "\n".join(["# GENERATED: publish metadata to Unity Catalog (comments, tags, privacy tags/masks, informational PK/FK)",
                   "from lib.uc_publish import publish",
                   "publish_report = publish(spark, TARGET, SPEC, 'conformed', ENTITY_TABLES, os.path.abspath('../..'))",
                   "display(spark.createDataFrame([(r['status'], r['statement'][:120], r['error'] or '') for r in publish_report], 'status string, statement string, error string'))"]),
        "\n".join(["# GENERATED: QA (standards/qa_checklist.md) on the master",
                   "results = qa.run_table_checks(spark, SPEC, TARGET, bronze_count=expected_rows, entity_tables=ENTITY_TABLES, silver_prefix=f'{catalog}.{silver_schema}')",
                   "summary = qa.write_summary(results, os.path.abspath('qa_results/summary.json'), ENTITY)",
                   "display(spark.createDataFrame([(r['check'], r['status'], str(r['evidence'])) for r in results], 'check string, status string, evidence string'))",
                   "assert summary['all_passed'], 'QA failed: see qa_results'"]),
    ]
    return SEP.join(cells) + "\n"


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print(__doc__)
        return 2
    entity = argv[0]
    with open(os.path.join(ROOT, "registry", "entities.yaml"), encoding="utf-8") as f:
        ent = next((e for e in yaml.safe_load(f)["entities"] if e["name"] == entity), None)
    if not ent:
        print(f"entity {entity} is not in registry/entities.yaml")
        return 1
    sources = list(feeding_sttms(entity, ROOT))
    d = os.path.join(ROOT, "masters", ent["target_table"])
    os.makedirs(os.path.join(d, "qa_results"), exist_ok=True)
    path = os.path.join(d, f"nb_build_{ent['target_table']}.py")
    cells = [g.stamp(c) for c in g.split_cells(render(entity, ent, sources))]
    if os.path.exists(path) and "--force" not in argv:
        with open(path, encoding="utf-8") as f:
            cells, rep = g.merge_cells(f.read(), cells)
    with open(path, "w", encoding="utf-8") as f:
        f.write(SEP.join(cells) + "\n")
    print(f"wrote {os.path.relpath(path, ROOT)} (sources: {', '.join(sources) or 'none'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
