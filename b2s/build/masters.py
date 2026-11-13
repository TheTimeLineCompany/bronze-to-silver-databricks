"""P5.4 Master build notebooks for shared masters (port of V1.1 tools/p5_4_gen_master_build.py).

One notebook per entity, at project level: <project>/masters/<table>/nb_build_<table>.vNNN.py. It reads the staging
tables of every application that maps the entity (found from their CP4-approved STTMs at generation time), applies
the survivorship rules of _project/key_normalisation.yaml, loads the master and seeds the unknown member.
An entity fed by two or more applications needs survivorship rules (problem otherwise).
"""
from __future__ import annotations

import json

from .. import FRAMEWORK_ROOT, versions
from ..layout import Layout
from ..project import ontology
from ..steps import save_output
from .codegen import SEP, build_settings, join_cells, merge_cells, split_cells, stamp
from .spec import approved_sttm, runtime_tables


def _feeding(layout: Layout, entity: str) -> dict:
    out = {}
    for app in layout.apps():
        sv = approved_sttm(layout, app)
        if sv:
            for t in runtime_tables(layout, app, versions.read(sv)):
                if t.get("conformed_entity") == entity:
                    out[app] = t
    return out


def render(entity: str, ent: dict, feeding: dict, b: dict, project_root: str) -> str:
    tbl = ent["target_table"]
    cells = [
        "# Databricks notebook source\n# MAGIC %md\n"
        f"# MAGIC # Master build: {tbl}  (entity {entity})\n"
        f"# MAGIC Applications: {', '.join(feeding) or 'none'}. Survivorship: `_project/key_normalisation.yaml`. "
        "Writes to the DEV silver schema only. Do not change GENERATED cells.",
        "\n".join(["# GENERATED: parameters", "import os, sys, json",
                   f'DEV_CATALOG, DEV_SCHEMA = "{b["dev_catalog"]}", "{b["dev_silver_schema"]}"   # project settings.build',
                   f"PROD_MARKERS = {list(b['prod_markers'])!r}",
                   'assert not any(m in f"{DEV_CATALOG}.{DEV_SCHEMA}".lower() for m in PROD_MARKERS), "dev schema only"',
                   f'FRAMEWORK = os.environ.get("B2S_FRAMEWORK", r"{FRAMEWORK_ROOT}")',
                   f'PROJECT = os.environ.get("B2S_PROJECT", r"{project_root}")',
                   'dbutils.widgets.text("batch_id", "")', 'batch_id = dbutils.widgets.get("batch_id") or None',
                   f'ENTITY = "{entity}"']),
        "\n".join(["# GENERATED: imports and feeding applications", "sys.path.insert(0, FRAMEWORK)",
                   'os.environ["B2S_REGISTRY_DIR"] = os.path.join(PROJECT, "_project")',
                   "from lib.survivorship import build_master",
                   f"FEEDING = json.loads(r'''{json.dumps(feeding, sort_keys=True)}''')"]),
        "\n".join(["# GENERATED: build (staging tables -> survivorship -> master, unknown member seeded)",
                   "TARGET, SPEC, expected_rows = build_master(spark, ENTITY, DEV_CATALOG, DEV_SCHEMA, FEEDING, batch_id=batch_id, root=PROJECT)",
                   "spark.sql(f\"ALTER TABLE {TARGET} SET TBLPROPERTIES ('b2s.expected_rows' = '{expected_rows}')\")"]),
        "\n".join(["# GENERATED: publish metadata to Unity Catalog",
                   "from lib.uc_publish import publish", "from lib import qa_checks as qa",
                   "publish_report = publish(spark, TARGET, SPEC, 'conformed', qa.entity_tables(DEV_CATALOG, DEV_SCHEMA, PROJECT), FRAMEWORK)"]),
    ]
    return SEP.join(cells) + "\n"


def generate_masters(layout: Layout, app: str, *, reason: str = "generate (P5.4)") -> versions.Version:
    """Master build notebooks for every entity this application maps; saves build/masters (with problems)."""
    from lib.survivorship import rules
    from lib.paths import registry_file
    idx = versions.read(versions.latest(layout.stem(app, "build/index"), "json"))
    ents = {e["name"]: e for e in (ontology(layout, "entities").get("entities") or [])}
    b = build_settings(layout)
    out = {}
    for entity in sorted({n["entity"] for n in idx["notebooks"].values() if n.get("entity")}):
        ent = ents[entity]
        feeding = _feeding(layout, entity)
        problems = []
        surv = rules(entity, registry_file("key_normalisation.yaml", str(layout.root)))
        if len(feeding) >= 2 and not surv:
            problems.append(f"{entity} is fed by {len(feeding)} applications but has no survivorship rules "
                            "(_project/key_normalisation.yaml -> survivorship)")
        stem = layout.root / "masters" / ent["target_table"] / f"nb_build_{ent['target_table']}"
        cells = [stamp(c) for c in split_cells(render(entity, ent, feeding, b, str(layout.root)))]
        cur = versions.latest(stem, "py")
        if cur:
            cells, _ = merge_cells(cur.path.read_text(encoding="utf-8"), cells)
        v = versions.save(layout, stem, "py", join_cells(cells), reason=reason, step="P5.4", app=app)
        out[entity] = {"table": ent["target_table"], "notebook": layout.rel(v.path), "version": v.tag,
                       "feeding": sorted(feeding), "survivorship": bool(surv), "problems": problems}
    return save_output(layout, app, "build/masters", {"app": app, "masters": out}, reason=reason)
