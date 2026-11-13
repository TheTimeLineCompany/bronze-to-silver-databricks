"""P5.1 PySpark notebook generation from the CP4-approved canonical STTM (port of V1.1 tools/p5_1_gen_notebook.py).

Safe to re-run. Notebooks are versioned files work/P5/build/notebooks/<name>.vNNN.py. A rerun merges with the latest
version: GENERATED cells are refreshed from the STTM (a hand edit is reported), TODO(genie) cells are kept, and a
TODO cell whose specification changed gets a "# REVIEW(STTM changed)" block. TODO cells the STTM no longer needs
get "# REVIEW(not in STTM)". Genie completes TODO cells and saves the notebook as a new version (save_notebook).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml

import sys

from .. import FRAMEWORK_ROOT, versions
from ..layout import Layout
from ..project import app_config, settings
from ..steps import MissingApproval, save_output
from ..store import emit_event
from .spec import approved_sttm, runtime_tables

if str(FRAMEWORK_ROOT) not in sys.path:          # runtime library lib/ lives at the framework root
    sys.path.insert(0, str(FRAMEWORK_ROOT))

SEP = "\n# COMMAND ----------\n"
MARK = re.compile(r"^# (GENERATED|TODO\(genie\)): (\S+)")
STAMP = re.compile(r"\s*\[(gen|spec):[0-9a-f]{8}\]\s*$")
PLACEHOLDERS = ("df = df  # replace", "bronze_count = None  # TODO(genie)")


def naming() -> dict:
    return yaml.safe_load((FRAMEWORK_ROOT / "standards" / "naming.yaml").read_text(encoding="utf-8"))


def build_settings(layout: Layout) -> dict:
    b = {"dev_catalog": "dev", "dev_silver_schema": "silver_dev", "prod_markers": ["prod", "prd"]}
    b.update(settings(layout).get("build") or {})
    return b


def notebook_name(app: str, spec: dict) -> str:
    return naming()["notebook_name"].format(source_id=app, target_table=spec["target_table"])


# ============================================================================ render
def _col_line(c, aliases):
    t, rule = c["target"], c["rule"]
    src = c.get("source")
    if rule == "normalised_key" and src and c.get("key_rule"):
        return f'df = df.withColumn("{t}", normalise("{c["key_rule"]}", F.col("{src}")))', None
    if rule in ("direct", "normalised_key") and isinstance(src, str):
        note = "  # no key_rule in the STTM: plain copy" if rule == "normalised_key" else ""
        return f'df = df.withColumn("{t}", F.col("{src}").cast("{c["type"].lower()}")){note}', None
    if rule == "constant":
        return None, f"{t}: constant (STTM gives no value)"
    if rule == "lookup":
        return None, None
    if rule == "technical":
        if t == "effective_from":
            return None, f"{t}: change timestamp for SCD2 history (must be set on every row)"
        return None, None
    why = c.get("question") or c.get("assumption") or c.get("business_rule") or ""
    return None, f"{t}: {rule} ({c.get('status', 'known')}{', ' + why if why else ''}) source: {src}"


def render(app: str, spec: dict, sttm_label: str, b: dict, project_root: str, bronze_catalog: str) -> str:
    is_master = spec["target_kind"] == "master"
    from lib.survivorship import staging_table          # runtime library (framework root on sys.path)
    target_name = staging_table(spec["target_table"], app) if is_master else spec["target_table"]
    cells = [
        "# Databricks notebook source\n"
        f"# MAGIC %md\n# MAGIC # {spec['target_table']}  (application {app})\n# MAGIC Grain: {spec.get('grain')}\n"
        f"# MAGIC Business object `{spec.get('business_object')}`, data class `{spec.get('data_class')}`, "
        f"load pattern `{spec['load_pattern']}`.\n"
        f"# MAGIC Generated from `{sttm_label}` (CP4). Writes to the DEV silver schema only. Do not change GENERATED cells.",
        "\n".join([
            "# GENERATED: parameters",
            "import os, sys, json",
            f'DEV_CATALOG, DEV_SCHEMA = "{b["dev_catalog"]}", "{b["dev_silver_schema"]}"   # project settings.build',
            f'TARGET = f"{{DEV_CATALOG}}.{{DEV_SCHEMA}}.{target_name}"'
            + ("   # shared master: this application writes its STAGING table" if is_master else ""),
            f"PROD_MARKERS = {list(b['prod_markers'])!r}",
            'assert not any(m in f"{DEV_CATALOG}.{DEV_SCHEMA}".lower() for m in PROD_MARKERS), '
            '"generated notebooks write to the dev schema only"',
            f'BRONZE_CATALOG = "{bronze_catalog}"',
            f'FRAMEWORK = os.environ.get("B2S_FRAMEWORK", r"{FRAMEWORK_ROOT}")',
            f'PROJECT = os.environ.get("B2S_PROJECT", r"{project_root}")',
            'dbutils.widgets.text("batch_id", "")',
            'batch_id = dbutils.widgets.get("batch_id") or None']),
        "\n".join([
            "# GENERATED: imports and spec",
            "sys.path.insert(0, FRAMEWORK)",
            'os.environ["B2S_REGISTRY_DIR"] = os.path.join(PROJECT, "_project")',
            "from pyspark.sql import functions as F",
            "from lib.keys import normalise, lookup_sk, UNKNOWN_SK",
            "from lib.load_patterns import load",
            "from lib import qa_checks as qa",
            f"SPEC = json.loads(r'''{json.dumps(spec, sort_keys=True)}''')",
            "ENTITY_TABLES = qa.entity_tables(DEV_CATALOG, DEV_SCHEMA, PROJECT)",
            "bronze = lambda t: f'{BRONZE_CATALOG}.{t}' if BRONZE_CATALOG else t"]),
        "\n".join(["# GENERATED: read bronze sources"]
                  + [f'{s["alias"]} = spark.table(bronze("{s["table"]}")).alias("{s["alias"]}")' for s in spec["sources"]]),
        "\n".join(["# TODO(genie): filters and dedup from the STTM; set the row count after filter + dedup (QA-01)",
                   f"# grain: {spec.get('grain')}", f"# business key: {spec['business_key']}",
                   "bronze_count = None  # TODO(genie): row count after filter + dedup"]),
    ]
    if len(spec["sources"]) > 1:
        cells.append("\n".join(["# TODO(genie): joins between the sources. Check the row count does not change for N:1 joins."]
                               + [f"# {s['alias']} = {s['table']}" for s in spec["sources"]]))
    sel, todo = [], []
    for c in spec["columns"]:
        e, td = _col_line(c, [s["alias"] for s in spec["sources"]])
        if e:
            sel.append(e)
        if td:
            todo.append(f"#   {td}")
    first = spec["sources"][0]["alias"] if spec["sources"] else "None"
    cells.append("\n".join(["# GENERATED: direct and key columns (raw source columns stay available)", f"df = {first}"] + sel))
    cells.append("\n".join(["# TODO(genie): derived, constant and open columns. Follow standards/coding.md;",
                            "# use lib.keys.normalise for every key used in a lookup join."] + todo + ["df = df  # replace"]))
    fk = ["# GENERATED: fk lookups (lib.keys.lookup_sk; composite keys supported)", "rejected_count = 0"]
    for c in spec["columns"]:
        f = c.get("fk") or {}
        if not f.get("lookup_on"):
            continue
        parent = (f"spark.table(ENTITY_TABLES['{f['entity']}'])" if f.get("entity")
                  else f"spark.table(f'{{DEV_CATALOG}}.{{DEV_SCHEMA}}.{f['table']}')")
        fk += [f"# {c['target']} -> {f.get('entity') or f.get('table')} on {f['parent_bk']} (orphans: {f['orphan_policy']})",
               f"df, n = lookup_sk(df, {parent}, {f['lookup_on']!r}, {f['parent_bk']!r}, '{f['column']}', '{c['target']}',",
               f"                  orphan_policy='{f['orphan_policy']}', quarantine=TARGET + '_quarantine')",
               "rejected_count += n"]
    cells.append("\n".join(fk))
    tech = ["# GENERATED: technical columns"]
    sk = spec.get("surrogate_key")
    if is_master:
        tech.append("# shared master: the master build (P5.4) adds the surrogate key and history after survivorship")
    elif sk:
        parts = ", ".join(f"F.col('{x}').cast('string')" for x in sk["of"])
        tech.append(f"df = df.withColumn('{sk['column']}', F.sha2(F.concat_ws('|', {parts}), 256))")
    drop = {"effective_to", "is_current"} | ({(sk or {}).get("column")} if is_master else set())
    tech.append(f"df = df.select(*{[c['target'] for c in spec['columns'] if c['target'] not in drop]!r})")
    cells.append("\n".join(tech))
    src_tab = spec["sources"][0]["table"] if spec["sources"] else ""
    if is_master:
        cells.append("\n".join([
            "# GENERATED: load (shared master -> this application's staging table; P5.4 builds the master)",
            "from lib.survivorship import load_staging",
            f"load_staging(spark, df, TARGET, SPEC, source_id='{app}', batch_id=batch_id, src_system='{app}', src_table='{src_tab}')"]))
    else:
        cells.append("\n".join([
            "# GENERATED: load",
            f"load(spark, df, TARGET, SPEC, batch_id=batch_id, src_system='{app}', src_table='{src_tab}')"]))
        cells.append("\n".join([
            "# GENERATED: publish metadata to Unity Catalog (comments, tags, privacy tags/masks, informational PK/FK)",
            "from lib.uc_publish import publish",
            "publish_report = publish(spark, TARGET, SPEC, SPEC['target_table'], ENTITY_TABLES, FRAMEWORK)"]))
    cells.append("\n".join([
        "# GENERATED: run statistics for QA (P5.2 reads them from the table properties)",
        "if bronze_count is not None:",
        "    spark.sql(f\"ALTER TABLE {TARGET} SET TBLPROPERTIES ('b2s.expected_rows' = '{bronze_count - rejected_count}')\")"]))
    return SEP.join(cells) + "\n"


# ============================================================================ merge (V1.1 logic)
def _h(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def _key(cell):
    first = cell.split("\n", 1)[0]
    m = MARK.match(first)
    if m:
        return ("G:" if m.group(1) == "GENERATED" else "T:") + m.group(2)
    return "HEADER" if "Databricks notebook source" in first else "OTHER:" + _h(cell)


def _body(cell):
    b = cell.split("\n", 1)[1] if "\n" in cell else ""
    return "\n".join(ln.rstrip() for ln in b.strip("\n").split("\n"))


def _spec(cell):
    return "\n".join(ln for ln in _body(cell).split("\n")
                     if ln.startswith("#") and not ln.startswith("# REVIEW") and not ln.startswith("#  >"))


def stamp(cell):
    k = _key(cell)
    first, rest = (cell.split("\n", 1) + [""])[:2]
    first = STAMP.sub("", first)
    if k.startswith("G:"):
        return f"{first}  [gen:{_h(_body(cell))}]\n{rest}"
    if k.startswith("T:"):
        return f"{first}  [spec:{_h(_spec(cell))}]\n{rest}"
    return cell


def split_cells(text):
    return [c.strip("\n") for c in re.split(r"\n+# COMMAND -+\n+", text.strip("\n"))]


def join_cells(cells):
    return SEP.join(cells) + "\n"


def merge_cells(old_text, new_cells):
    old = split_cells(old_text)
    old_by = {_key(c): c for c in old}
    rep = {"generated_hand_edited": [], "todo_kept": [], "todo_review": [], "todo_new": [], "todo_orphan": []}
    out = []
    for c in new_cells:
        k = _key(c)
        o = old_by.get(k)
        if k == "HEADER" or k.startswith("G:"):
            if o is not None and k.startswith("G:"):
                m = re.search(r"\[gen:([0-9a-f]{8})\]", o.split("\n", 1)[0])
                if m and m.group(1) != _h(_body(o)):
                    rep["generated_hand_edited"].append(k[2:])
            out.append(c)
        elif k.startswith("T:"):
            if o is None:
                rep["todo_new"].append(k[2:])
                out.append(c)
                continue
            m = re.search(r"\[spec:([0-9a-f]{8})\]", o.split("\n", 1)[0])
            new_spec = re.search(r"\[spec:([0-9a-f]{8})\]", c.split("\n", 1)[0]).group(1)
            if m and m.group(1) == new_spec:
                rep["todo_kept"].append(k[2:])
                out.append(o)
            else:
                lines = [ln for ln in _body(o).split("\n") if not (ln.startswith("# REVIEW(STTM changed)") or ln.startswith("#  > "))]
                review = ["# REVIEW(STTM changed): this cell's specification changed. Check the code below, then delete these REVIEW lines."]
                review += [f"#  > {ln.lstrip('#').strip()}" for ln in _spec(c).split("\n") if ln.strip("# ")]
                rep["todo_review"].append(k[2:])
                out.append(c.split("\n", 1)[0] + "\n" + "\n".join(review + lines))
    new_keys = {_key(c) for c in new_cells}
    for o in old:
        k = _key(o)
        if k not in new_keys and not k.startswith("G:") and k != "HEADER":
            rep["todo_orphan"].append(k)
            first, rest = (o.split("\n", 1) + [""])[:2]
            if "# REVIEW(not in STTM)" not in rest:
                rest = "# REVIEW(not in STTM): the STTM no longer needs this cell. Move or delete it after review.\n" + rest
            out.insert(-2, first + "\n" + rest)
    return out, rep


# ============================================================================ problems (CP5)
def notebook_problems(text: str, b: dict) -> list[str]:
    """Open REVIEW blocks, hand-edited GENERATED cells, unfinished TODO cells, a non-dev target."""
    out = []
    for c in split_cells(text):
        k = _key(c)
        first = c.split("\n", 1)[0]
        if k.startswith("G:"):
            m = re.search(r"\[gen:([0-9a-f]{8})\]", first)
            if m and m.group(1) != _h(_body(c)):
                out.append(f"GENERATED cell '{k[2:]}' was edited by hand")
        if "# REVIEW(" in c:
            out.append(f"open REVIEW block in '{k[2:] if ':' in k else k}'")
        for p in PLACEHOLDERS:
            if p in c:
                out.append(f"TODO cell not completed ('{p.split('#')[0].strip()}')")
    if f'DEV_CATALOG, DEV_SCHEMA = "{b["dev_catalog"]}", "{b["dev_silver_schema"]}"' not in text:
        out.append("target is not the dev silver schema from project settings")
    if any(m in f"{b['dev_catalog']}.{b['dev_silver_schema']}".lower() for m in b["prod_markers"]):
        out.append("settings.build points to a production schema")
    return out


# ============================================================================ API
def generate(layout: Layout, app: str, *, reason: str = "generate (P5.1)") -> dict:
    """Generate or merge one notebook per STTM table; save build/index. Needs the CP4-approved STTM."""
    sv = approved_sttm(layout, app)
    latest = versions.latest(layout.stem(app, "sttm/sttm"), "json")
    if not sv or not latest or sv.n != latest.n:
        raise MissingApproval("P5.1 needs the latest STTM version approved at CP4"
                              + (f" (latest {latest.label}, approved {sv.label if sv else 'none'})" if latest else ""))
    b = build_settings(layout)
    bronze_catalog = (app_config(layout, app).get("bronze") or {}).get("catalog") or ""
    specs = runtime_tables(layout, app, versions.read(sv))
    if any(m in f"{b['dev_catalog']}.{b['dev_silver_schema']}".lower() for m in b["prod_markers"]):
        raise ValueError("settings.build points to a production schema; generated notebooks write to dev only")
    nbs, reports = {}, {}
    for spec in specs:
        name = notebook_name(app, spec)
        stem = layout.stem(app, f"build/notebooks/{name}")
        cells = [stamp(c) for c in split_cells(render(app, spec, sv.label, b, str(layout.root), bronze_catalog))]
        cur = versions.latest(stem, "py")
        rep = {}
        if cur:
            cells, rep = merge_cells(cur.path.read_text(encoding="utf-8"), cells)
        v = versions.save(layout, stem, "py", join_cells(cells), reason=reason, step="P5.1", app=app,
                          inputs={"sttm/sttm": sv.tag})
        nbs[spec["target_table"]] = {"notebook": name, "version": v.tag, "kind": spec["target_kind"],
                                     "entity": spec.get("conformed_entity")}
        reports[name] = {k: x for k, x in rep.items() if x}
    index = {"app": app, "sttm_version": sv.tag, "target": f"{b['dev_catalog']}.{b['dev_silver_schema']}",
             "notebooks": nbs, "run_order": _run_order(specs)}
    iv = save_output(layout, app, "build/index", index, reason=reason)
    emit_event(layout, "notebooks_generated", app=app, step="P5.1", note=iv.label, extra={"reports": reports})
    return {"index": iv, "notebooks": nbs, "reports": reports}


def _run_order(specs):
    """Masters' staging first, then tables without FKs, then tables with FKs (parents before children)."""
    masters = [s["target_table"] for s in specs if s["target_kind"] == "master"]
    plain = [s["target_table"] for s in specs if s["target_kind"] != "master" and not any(c.get("fk") for c in s["columns"])]
    child = [s["target_table"] for s in specs if s["target_kind"] != "master" and any(c.get("fk") for c in s["columns"])]
    return {"1_staging_for_masters": masters, "2_master_build": sorted({s["conformed_entity"] for s in specs if s["conformed_entity"]}),
            "3_tables": plain, "4_tables_with_fks": child}


def save_notebook(layout: Layout, app: str, file: str | Path, *, reason: str, via: str | None = None) -> dict:
    """Genie completed TODO cells: save the notebook as a new version (GENERATED cells must be unchanged),
    then refresh build/index."""
    p = Path(file)
    name = p.name.split(".v")[0].removesuffix(".py")
    stem = layout.stem(app, f"build/notebooks/{name}")
    if not versions.latest(stem, "py"):
        raise FileNotFoundError(f"{name} is not a generated notebook of {app}")
    text = p.read_text(encoding="utf-8")
    edited = [x for x in notebook_problems(text, build_settings(layout)) if "edited by hand" in x]
    if edited:
        raise ValueError("not saved: " + "; ".join(edited) + ". Put custom code in TODO(genie) cells or change the STTM.")
    v = versions.save(layout, stem, "py", text, reason=reason, step="P5.1", app=app,
                      inputs=versions.latest(stem, "py").meta.get("inputs"), via=via)
    res = generate(layout, app, reason=f"index after {v.label}")
    return {"notebook": v.label, "index": res["index"].label}
