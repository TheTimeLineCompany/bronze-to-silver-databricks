#!/usr/bin/env python3
"""P5.1 Generate a PySpark notebook SKELETON for each target table in an approved STTM.

Deterministic scaffolding: the same STTM always gives the same skeleton.
Genie Code (skill p5-1-pyspark-codegen) then completes the cells marked `# TODO(genie)`
and keeps every cell marked `# GENERATED` unchanged.

SAFE TO RE-RUN. When the notebook already exists, the generator MERGES instead of overwriting:
  - GENERATED cells are refreshed from the STTM. A GENERATED cell that was edited by hand is detected
    (its [gen:hash] no longer matches); the old file is saved as <name>.py.bak and the edit is reported.
  - TODO(genie) cells are KEPT as written. If the STTM changed what a TODO cell must do (its [spec:hash] changed),
    a "# REVIEW(STTM changed)" block with the new specification is put at the top of the cell. The CP5 pack
    reports every open REVIEW block until a person or agent removes it.
  - TODO cells the STTM no longer needs are kept at the end, marked "# REVIEW(not in STTM)".
  --dry-run   report what would change, write nothing
  --force     regenerate from scratch (old file saved as .bak) - this discards TODO work

Usage:
    python tools/p5_1_gen_notebook.py sources/S07_container_moves/04_mapping/sttm.yaml [--dry-run | --force]
    -> sources/S07_container_moves/05_build/nb_slv_S07_container_moves_slv_cnt_shipment_leg.py
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lib.survivorship import staging_table  # noqa: E402
SEP = "\n# COMMAND ----------\n"


def _naming():
    with open(os.path.join(ROOT, "standards", "naming.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def _col_expr(c):
    t = c["target"]
    rule = c["rule"]
    if rule == "normalised_key":
        return f'df = df.withColumn("{t}", normalise("{c["key_rule"]}", F.expr("{c["source"]}")))', None
    if rule == "direct":
        expr = c.get("transform") or c["source"]
        return f'df = df.withColumn("{t}", F.expr("""{expr}""").cast("{c["type"]}"))', None
    if rule == "constant":
        return f'df = df.withColumn("{t}", F.lit({c.get("transform")!r}).cast("{c["type"]}"))', None
    if rule == "derived":
        return None, f'{t}: derived -> {c.get("transform")}  (source: {c.get("source")})' + (
            f"  [BUSINESS LOGIC {c.get('business_rule')}: must match CP4b sign-off]" if c.get("business_logic") else "")
    if rule == "lookup" and (c.get("fk") or {}).get("lookup_on"):
        return None, None                      # generated in the 'fk' cell (lib.keys.lookup_sk)
    if rule == "lookup":
        return None, f'{t}: lookup -> {c.get("transform")}'
    if rule == "technical" and t == "effective_from":
        return None, f'{t}: change timestamp for SCD2 history -> {c.get("transform")}  (must be set on every row)'
    return None, None  # other technical columns are added later


def _entities():
    with open(os.path.join(ROOT, "registry", "entities.yaml"), encoding="utf-8") as f:
        return {e["name"]: e for e in yaml.safe_load(f)["entities"]}


def _fk_cell(t, doc_tables=None):
    """GENERATED cell: every FK with fk.lookup_on is resolved by lib.keys.lookup_sk (single or composite keys)."""
    ents = _entities()
    out = ["# GENERATED: fk lookups (fk.lookup_on in the STTM -> lib.keys.lookup_sk; composite keys supported)",
           "rejected_count = 0"]
    for c in t["columns"]:
        fk = c.get("fk") or {}
        if not fk.get("lookup_on"):
            continue
        if fk.get("entity"):
            e = ents.get(fk["entity"], {})
            parent = f"spark.table(ENTITY_TABLES['{fk['entity']}'])"
            bk = list(e.get("business_key", []))
        else:
            pt = next((x for x in (doc_tables or []) if x["target_table"] == fk["table"]), {})
            parent = f"spark.table(f'{{catalog}}.{{silver_schema}}.{fk['table']}')"
            bk = list(pt.get("business_key", []))
        pol = fk.get("orphan_policy", "reject")
        out += [f"# {c['target']} -> {fk.get('entity') or fk.get('table')} on {bk} ({fk.get('cardinality')}, orphans: {pol})",
                f"df, n = lookup_sk(df, {parent}, FK['{c['target']}']['lookup_on'], {bk!r}, '{fk['column']}', '{c['target']}',",
                f"                  orphan_policy='{pol}', quarantine=f'{{TARGET}}_quarantine')",
                "rejected_count += n"]
    return "\n".join(out)


def render(doc, t):
    nm = _naming()
    sid = doc["source_id"]
    is_master = t.get("target_kind") == "master"
    lines = []
    lines.append("# Databricks notebook source")
    lines.append(f"# MAGIC %md\n# MAGIC # {t['target_table']}  (source {sid})\n# MAGIC Grain: {t['grain']}\n"
                 f"# MAGIC Business object: `{t.get('business_object')}`  Data class: `{t.get('data_class')}`\n"
                 f"# MAGIC Load pattern: `{t['load_pattern']}`  SCD: `{t['scd_type']}`\n"
                 f"# MAGIC Generated from `sources/{sid}/04_mapping/sttm.yaml` v{doc['version']}. Do not change GENERATED cells.")
    body = [
        "# GENERATED: parameters",
        'dbutils.widgets.text("catalog", "dev")',
        'dbutils.widgets.text("silver_schema", "silver")',
        'dbutils.widgets.text("batch_id", "")',
        'catalog = dbutils.widgets.get("catalog")',
        'silver_schema = dbutils.widgets.get("silver_schema")',
        'batch_id = dbutils.widgets.get("batch_id") or None',
        (f'TARGET = f"{{catalog}}.{{silver_schema}}.{staging_table(t["target_table"], sid)}"   # shared master: this source writes its STAGING table'
         if is_master else f'TARGET = f"{{catalog}}.{{silver_schema}}.{t["target_table"]}"'),
    ]
    lines.append("\n".join(body))
    lines.append("\n".join([
        "# GENERATED: imports and STTM",
        "import sys, os, yaml",
        "sys.path.insert(0, os.path.abspath('../../..'))   # repo root (notebook is in sources/<id>/05_build/)",
        "from pyspark.sql import functions as F, Window",
        "from lib.keys import normalise, lookup_sk, UNKNOWN_SK   # UNKNOWN_SK: FK value for orphans when orphan_policy is unknown_member",
        "from lib.load_patterns import load",
        "from lib import qa_checks as qa",
        "with open(os.path.abspath('../04_mapping/sttm.yaml')) as f:",
        "    STTM = yaml.safe_load(f)",
        f"T = next(x for x in STTM['tables'] if x['target_table'] == '{t['target_table']}')",
        "FK = {c['target']: c['fk'] for c in T['columns'] if c.get('fk')}",
        "ENTITY_TABLES = qa.entity_tables(catalog, silver_schema, os.path.abspath('../../..'))   # shared masters (registry/entities.yaml)",
    ]))
    reads = ["# GENERATED: read bronze sources (filters from STTM)"]
    for s in t["sources"]:
        reads.append(f'{s["alias"]} = spark.table("{s["table"]}").alias("{s["alias"]}")' + (f'.where("""{s["filter"]}""")' if s.get("filter") else ""))
    lines.append("\n".join(reads))
    dedup = ["# TODO(genie): dedup rules from STTM (keep this cell short and explicit)"]
    for s in t["sources"]:
        if s.get("dedup"):
            dedup.append(f"# {s['alias']}: {s['dedup']}")
    dedup.append("bronze_count = None  # TODO(genie): row count after filter + dedup, for QA-01")
    lines.append("\n".join(dedup))
    if t.get("joins"):
        j = ["# TODO(genie): joins from STTM. Check the row count does not change for N:1 joins."]
        for x in t["joins"]:
            j.append(f"# {x['left']} {x['type'].upper()} JOIN {x['right']} ON {x['condition']}  [{x['cardinality']}]")
        lines.append("\n".join(j))
    sel, todo = [], []
    for c in t["columns"]:
        e, td = _col_expr(c)
        if e:
            sel.append(e)
        if td:
            todo.append(f"#   {td}")
    first = t["sources"][0]["alias"]
    lines.append("\n".join(["# GENERATED: direct and key columns (raw source columns stay available for the TODO cell)", f"df = {first}"] + sel))
    lines.append("\n".join(["# TODO(genie): derived and lookup columns. Follow standards/coding.md.",
                            "# Use lib.keys.normalise for every key used in a lookup join."] + todo + ["df = df  # replace"]))
    lines.append(_fk_cell(t, doc["tables"]))
    tech = ["# GENERATED: technical columns"]
    sk = t.get("surrogate_key")
    if is_master:
        tech.append("# shared master: no surrogate key here; the master build (masters/) adds keys and history after survivorship")
        sk = None
    if sk:
        parts = ", ".join(f"F.col('{c}').cast('string')" for c in sk["of"])
        tech.append(f"df = df.withColumn('{sk['column']}', F.sha2(F.concat_ws('|', {parts}), 256))")
    drop = {"effective_to", "is_current"} | ({(t.get("surrogate_key") or {}).get("column")} if is_master else set())
    keep = [c["target"] for c in t["columns"] if c["target"] not in drop]
    tech.append(f"df = df.select(*{keep!r})")
    lines.append("\n".join(tech))
    src_tab = t['sources'][0]['table'].split('.')[-1]
    if is_master:
        lines.append("\n".join([
            "# GENERATED: load (shared master -> this source's staging table; run the master build in masters/ afterwards)",
            "from lib.survivorship import load_staging, staging_spec",
            f"load_staging(spark, df, TARGET, T, source_id=STTM['source_id'], batch_id=batch_id, src_system=STTM['source_system'], src_table='{src_tab}')",
            "QT = staging_spec(T)   # QA runs on the staging table",
        ]))
    else:
        lines.append("\n".join([
            "# GENERATED: load",
            f"load(spark, df, TARGET, T, batch_id=batch_id, src_system=STTM['source_system'], src_table='{src_tab}')",
            "QT = T",
        ]))
        lines.append("\n".join([
            "# GENERATED: publish metadata to Unity Catalog (comments, tags, privacy tags/masks, informational PK/FK)",
            "from lib.uc_publish import publish",
            "PARENTS = {**ENTITY_TABLES, **{x['target_table']: f'{catalog}.{silver_schema}.' + x['target_table'] for x in STTM['tables']}}",
            "publish_report = publish(spark, TARGET, T, STTM['source_id'], PARENTS, os.path.abspath('../../..'))",
            "display(spark.createDataFrame([(r['status'], r['statement'][:120], r['error'] or '') for r in publish_report], 'status string, statement string, error string'))",
        ]))
    lines.append("\n".join([
        "# GENERATED: QA (standards/qa_checklist.md). The job fails if any check fails or cannot run.",
        "expected = None if bronze_count is None else bronze_count - rejected_count   # rows rejected by FK lookups are in quarantine",
        "results = qa.run_table_checks(spark, QT, TARGET, bronze_count=expected, entity_tables=ENTITY_TABLES, silver_prefix=f'{catalog}.{silver_schema}')",
        f"summary = qa.write_summary(results, os.path.abspath('qa_results/{t['target_table']}.json'), '{sid}')",
        f"qa.combine_summaries(os.path.abspath('qa_results'), '{sid}')   # checkpoint CP5 reads qa_results/summary.json",
        "display(spark.createDataFrame([(r['check'], r['status'], str(r['evidence'])) for r in results], 'check string, status string, evidence string'))",
        "assert summary['all_passed'], 'QA failed: see qa_results'",
    ]))
    return lines[0] + "\n" + SEP.join(lines[1:]) + "\n"


MARK = re.compile(r"^# (GENERATED|TODO\(genie\)): (\S+)")
STAMP = re.compile(r"\s*\[(gen|spec):[0-9a-f]{8}\]\s*$")


def _h(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def _key(cell):
    first = cell.split("\n", 1)[0]
    m = MARK.match(first)
    if m:
        return ("G:" if m.group(1) == "GENERATED" else "T:") + m.group(2)
    return "HEADER" if "Databricks notebook source" in first else "OTHER:" + _h(cell)


def _body(cell):
    """Cell body without the marker line, normalised (Databricks may add blank lines or trailing spaces on save)."""
    b = cell.split("\n", 1)[1] if "\n" in cell else ""
    return "\n".join(ln.rstrip() for ln in b.strip("\n").split("\n"))


def _spec(cell):
    """What a TODO cell must do = its generated comment lines (not REVIEW blocks, not code)."""
    return "\n".join(ln for ln in _body(cell).split("\n") if ln.startswith("#") and not ln.startswith("# REVIEW") and not ln.startswith("#  >"))


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


def fresh(doc, t):
    return [stamp(c) for c in split_cells(render(doc, t))]


def merge_cells(old_text, new_cells):
    """Merge a regenerated notebook into an existing one. Returns (cells, report)."""
    old = split_cells(old_text)
    old_by = {_key(c): c for c in old}
    rep = {"generated_refreshed": [], "generated_hand_edited": [], "todo_kept": [], "todo_review": [], "todo_new": [], "todo_orphan": []}
    out = []
    for c in new_cells:
        k = _key(c)
        o = old_by.get(k)
        if k == "HEADER" or k.startswith("G:"):
            if o is not None and k.startswith("G:"):
                m = re.search(r"\[gen:([0-9a-f]{8})\]", o.split("\n", 1)[0])
                if m and m.group(1) != _h(_body(o)):
                    rep["generated_hand_edited"].append(k[2:])
                if o != c:
                    rep["generated_refreshed"].append(k[2:])
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
            out.insert(-2, first + "\n" + rest)        # before the load and QA cells
    return out, rep


def write_notebook(doc, t, path, force=False, dry_run=False):
    cells = fresh(doc, t)
    rep = {"action": "created"}
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as f:
            old_text = f.read()
        cells, rep = merge_cells(old_text, cells)
        rep["action"] = "merged"
        new_text = cells[0] + "\n" if len(cells) == 1 else SEP.join(cells) + "\n"
        if new_text == old_text:
            rep["action"] = "unchanged"
            return rep
        if rep["generated_hand_edited"] and not dry_run:
            shutil.copyfile(path, path + ".bak")
            rep["backup"] = os.path.basename(path) + ".bak"
    elif os.path.exists(path) and force and not dry_run:
        shutil.copyfile(path, path + ".bak")
        rep = {"action": "forced", "backup": os.path.basename(path) + ".bak"}
    if not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            f.write(SEP.join(cells) + "\n")
    return rep


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    force, dry = "--force" in argv, "--dry-run" in argv
    argv = [a for a in argv if not a.startswith("--")]
    if not argv:
        print(__doc__)
        return 2
    with open(argv[0], encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    nm = _naming()
    out_dir = os.path.join(ROOT, "sources", doc["source_id"], "05_build")
    os.makedirs(out_dir, exist_ok=True)
    warn = False
    for t in doc["tables"]:
        name = nm["notebook_name"].format(source_id=doc["source_id"], target_table=t["target_table"])
        path = os.path.join(out_dir, name + ".py")
        rep = write_notebook(doc, t, path, force, dry)
        print(("[dry-run] " if dry else "") + f"{rep.pop('action')}: {os.path.relpath(path, ROOT)}")
        for k, v in rep.items():
            if v:
                print(f"  {k}: {v}")
        warn |= bool(rep.get("generated_hand_edited"))
    if warn:
        print("WARNING: GENERATED cells were edited by hand. Their edits were replaced; see the .bak file. "
              "Put custom code in TODO(genie) cells or change the STTM.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
