#!/usr/bin/env python3
"""P2.2 Bronze discovery - orchestrator.

Finds, for one source system, WITHOUT reading all data:
  tables     row counts, columns, types                                       (catalog, metadata only)
  columns    null %, approx distinct, min/max, lengths, shapes, top values     (profile, on a sample)
  keys       minimal unique column combinations = grain candidates            (keys, exact check on full table)
  links      column-to-column value containment = FK candidates, cardinality  (links, distinct-set checks)
  domains    low-cardinality columns that share code values across tables
  model      table role (master, reference, transaction header/line, event, snapshot, bridge,
             aggregate/derived, staging), grain sentence, lineage level, derived-from, ontology mapping
  cards      small task cards for the cases code cannot decide -> one agent (sub-agent) per card
  merge      agent answers -> final decisions

Work is split into independent TASKS so they can run in parallel:
  catalog -> profile[table] x N -> keys[table] x N -> plan-links -> links[batch] x M -> model -> cards -> (agents) -> merge
  - Code tasks run as a Databricks Job with for_each tasks (see `job`), or one by one in a notebook.
  - Judgement tasks (cards) run as separate agent chats: one card per chat, `@p2-2-bronze-discovery card <file>`.
Each task writes its own part file (no write conflicts); `model` combines them.
State: sources/<id>/02_evidence/discovery/tasks.jsonl (one line per finished task).

Usage (in a Databricks notebook or locally with a SparkSession):
    python tools/p2_2_discover.py plan   S07_container_moves                 # task plan + job.json
    python tools/p2_2_discover.py run    S07_container_moves --stage catalog
    python tools/p2_2_discover.py run    S07_container_moves --stage profile --table bronze.container_track.legs
    python tools/p2_2_discover.py run    S07_container_moves --stage all       # small sources: everything in one go
    python tools/p2_2_discover.py status S07_container_moves
    python tools/p2_2_discover.py merge  S07_container_moves                  # after agents answered the cards
    python tools/p2_2_discover.py evidence S07_container_moves                # bronze facts -> evidence register
Outputs: sources/<id>/02_evidence/discovery/ (summary.md is the ONLY file an agent reads first).
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import os
import sys
from datetime import datetime, timezone

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from discovery import core  # noqa: E402

STAGES = ["catalog", "meta", "profile", "keys", "plan-links", "links", "model", "wider", "cards"]
PER_TABLE = {"profile", "keys"}


def _y(p):
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def ddir(sid, root=None):
    return os.path.join(root or ROOT, "sources", sid, "02_evidence", "discovery")


def budgets(root=None):
    info = _y(os.path.join(root or ROOT, "registry", "ontology", "information.yaml"))
    return info.get("discovery_budgets", {})


def source_cfg(sid, root=None):
    reg = _y(os.path.join(root or ROOT, "registry", "sources.yaml"))
    s = next(s for s in reg["sources"] if s["id"] == sid)
    return s


def _w_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)


def _r_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _w_csv(path, rows, cols=None):
    cols = cols or (list(rows[0].keys()) if rows else ["empty"])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()})


def _log(sid, task, status, note="", root=None):
    p = os.path.join(ddir(sid, root), "tasks.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "task": task, "status": status, "note": note}) + "\n")


def _safe(t):
    return t.replace(".", "__")


# ----------------------------------------------------------------------------- stages
def st_catalog(spark, sid, root=None, **_):
    from discovery import spark_io
    s = source_cfg(sid, root)
    dc = s.get("discovery", {}) or {}
    tabs = spark_io.list_tables(spark, s["bronze_schema"], dc.get("include"), dc.get("exclude"))
    tabs += [t for t in (dc.get("extra_tables") or []) if t not in tabs]      # accepted on R-/D- cards (other schemas)
    b = budgets(root)
    if len(tabs) > b.get("max_tables", 200):
        raise RuntimeError(f"{len(tabs)} tables > max_tables {b.get('max_tables')}: narrow with sources.yaml discovery.include")
    rows = [spark_io.catalog_entry(spark, t) for t in tabs]
    _w_json(os.path.join(ddir(sid, root), "parts", "catalog.json"), rows)
    _log(sid, "catalog", "done", f"{len(rows)} tables", root)
    return rows


def st_meta(spark, sid, root=None, **_):
    """Unity Catalog metadata + lineage for the source tables (no data read). Never fails: see metadata/availability.csv."""
    from discovery import uc
    tabs = [r["table"] for r in _catalog(sid, root)]
    m = uc.harvest(spark, tabs, budgets(root))
    _w_json(os.path.join(ddir(sid, root), "parts", "meta.json"), m)
    md = os.path.join(ddir(sid, root), "metadata")
    os.makedirs(md, exist_ok=True)
    _w_csv(os.path.join(md, "availability.csv"), [{"section": k, "available": v.get("available"), "rows": len(v.get("rows") or []),
                                                   "reason": v.get("reason", "")} for k, v in m.items()])
    for k, v in m.items():
        rows = v.get("rows") or []
        if rows:
            _w_csv(os.path.join(md, f"{k}.csv"), rows, sorted({c for r in rows for c in r}))
    _log(sid, "meta", "done", ", ".join(f"{k}={'ok' if v.get('available') else 'n/a'}" for k, v in m.items()), root)
    return m


def _meta(sid, root=None):
    p = os.path.join(ddir(sid, root), "parts", "meta.json")
    return _r_json(p) if os.path.exists(p) else {}


def _rows_of(meta, section):
    return (meta.get(section) or {}).get("rows") or []


def _short(t):
    return ".".join(str(t).lower().split(".")[-2:])


def _catalog(sid, root=None):
    return _r_json(os.path.join(ddir(sid, root), "parts", "catalog.json"))


def st_profile(spark, sid, table, root=None, **_):
    from discovery import spark_io
    rc = next(r["row_count"] for r in _catalog(sid, root) if r["table"] == table)
    p = spark_io.profile(spark, table, budgets(root), rc)
    p = core.apply_stats(p, [r for r in _rows_of(_meta(sid, root), "column_stats")
                             if _short(r["table"]) == _short(table)])   # exact NDV / nulls from Unity Catalog statistics, if any
    meta = _meta(sid, root)
    tags = {}
    for r in _rows_of(meta, "tags"):
        if _short(table).endswith(str(r.get("table_name", "")).lower()) and r.get("column_name"):
            tags.setdefault(str(r["column_name"]).lower(), []).append(f"{r.get('tag_name')}={r.get('tag_value')}")
    masked = {str(r.get("column_name", "")).lower() for r in _rows_of(meta, "masks_and_filters")
              if r.get("kind") == "column_mask" and _short(table).endswith(str(r.get("table_name", "")).lower())}
    p = core.redact_values(p, tags, masked)                 # personal data, secrets, log values never reach a file
    _w_json(os.path.join(ddir(sid, root), "parts", "profile", _safe(table) + ".json"), p)
    _log(sid, f"profile:{table}", "done", f"{p['sample_rows']} sample rows", root)
    return p


def st_keys(spark, sid, table, root=None, **_):
    from discovery import spark_io
    p = _r_json(os.path.join(ddir(sid, root), "parts", "profile", _safe(table) + ".json"))
    shared = set()
    try:                                               # column names that also exist in another table of this source
        cat = _catalog(sid, root)
        names = {r["table"]: {c.split(":")[0] for c in r["columns"].split(", ")} for r in cat}
        shared = {c for t, cs in names.items() if t != table for c in cs} & names.get(table, set())
    except (OSError, KeyError):
        pass
    declared = core.declared_keys(_rows_of(_meta(sid, root), "constraints")).get(table.split(".")[-1].lower(), [])
    res = core.find_keys(p["columns"], p["row_count"], lambda cols: spark_io.verify_unique(spark, table, cols), budgets(root), shared, declared)
    res["declared_keys"] = declared
    _w_json(os.path.join(ddir(sid, root), "parts", "keys", _safe(table) + ".json"), {"table": table, **res})
    _log(sid, f"keys:{table}", "done", f"best={res['best']} checks={res['checks']}", root)
    return res


def _load_parts(sid, root=None):
    tables, keys = {}, {}
    for f in glob.glob(os.path.join(ddir(sid, root), "parts", "profile", "*.json")):
        p = _r_json(f)
        tables[p["table"]] = p
    for f in glob.glob(os.path.join(ddir(sid, root), "parts", "keys", "*.json")):
        k = _r_json(f)
        keys[k["table"]] = k
    return tables, keys


def _abbr(root=None):
    return (_y(os.path.join(root or ROOT, "registry", "ontology", "business.yaml")) or {}).get("abbreviations", {}) or {}


def st_plan_links(spark, sid, root=None, **_):
    tables, keys = _load_parts(sid, root)
    b = budgets(root)
    ours = {_short(t): t for t in tables}
    declared = []
    for c in core.declared_links(_rows_of(_meta(sid, root), "constraints"), ".".join(next(iter(tables)).split(".")[:-1]) if tables else ""):
        ref = ours.get(_short(c["ref_table"]))
        dep = ours.get(_short(c["dep_table"]))
        if ref and dep:                                  # declared FKs inside the source are tested first
            declared.append({**c, "ref_table": ref, "dep_table": dep})
    cands = declared + core.link_candidates(tables, keys, b, _abbr(root)) + core.composite_link_candidates(tables, keys, b, _abbr(root))
    seen, uniq = set(), []
    for c in cands:
        k = (c["dep_table"], c["dep_column"], c["ref_table"], c["ref_column"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    cands = uniq
    n = b.get("link_batch_size", 25)
    batches = [cands[i:i + n] for i in range(0, len(cands), n)]
    for i, bt in enumerate(batches):
        _w_json(os.path.join(ddir(sid, root), "parts", "link_plan", f"batch_{i:03d}.json"), bt)
    _log(sid, "plan-links", "done", f"{len(cands)} candidates in {len(batches)} batches", root)
    return batches


def st_links(spark, sid, batch, root=None, **_):
    from discovery import spark_io
    b = budgets(root)
    cands = _r_json(os.path.join(ddir(sid, root), "parts", "link_plan", f"batch_{int(batch):03d}.json"))
    _, keys = _load_parts(sid, root)
    out = []
    for c in cands:
        m = spark_io.containment(spark, c, b)
        dcols = core.link_cols(c["dep_column"])
        dep_unique = any(set(k) <= set(dcols) for k in keys.get(c["dep_table"], {}).get("keys", []))   # dep side holds a key -> 1:1
        out.append({**core.judge_link(m, dep_unique, b), "dep_unique": dep_unique})
    _w_json(os.path.join(ddir(sid, root), "parts", "links", f"batch_{int(batch):03d}.json"), out)
    _log(sid, f"links:{batch}", "done", f"{len(out)} checked", root)
    return out


def st_model(spark, sid, root=None, **_):
    """Combine parts -> CSVs, roles, grain, lineage, ontology mapping, summary. Pure code."""
    root = root or ROOT
    d = ddir(sid, root)
    b = budgets(root)
    business = _y(os.path.join(root, "registry", "ontology", "business.yaml"))
    tables, keys = _load_parts(sid, root)
    links = sum((_r_json(f) for f in sorted(glob.glob(os.path.join(d, "parts", "links", "*.json")))), [])
    fks = [l for l in links if l["status"] in ("fk", "fk_partial")]
    # keep the best referenced column per dependent column
    best = {}
    for l in sorted(fks, key=lambda x: (-max(x["containment_raw"], x["containment_norm"]), -x["score"])):
        best.setdefault((l["dep_table"], l["dep_column"]), l)
    fks = list(best.values())
    pref = source_cfg(sid, root).get("business_objects", [])
    roles, trows = {}, []
    for t, info in tables.items():
        out_l = [l for l in fks if l["dep_table"] == t and l["ref_table"] != t]
        in_l = [l for l in fks if l["ref_table"] == t and l["dep_table"] != t]
        k = keys.get(t, {}).get("best")
        roles[t] = core.classify(t.split(".")[-1], info, k, out_l, in_l, b)
    # staging tables (copies, backups) never shape the model: drop their links from the graph
    fks = [l for l in fks if roles[l["dep_table"]]["role"] != "staging"]
    # transitive composite links: schedule(MANDT+EBELN) -> header is implied by schedule(MANDT+EBELN+EBELP) -> line -> header
    def _implied(l1):
        c1 = set(core.link_cols(l1["dep_column"]))
        for l2 in fks:
            if l2 is not l1 and l2["dep_table"] == l1["dep_table"] and c1 < set(core.link_cols(l2["dep_column"])) and \
                    any(l3["dep_table"] == l2["ref_table"] and l3["ref_table"] == l1["ref_table"] for l3 in fks):
                return True
        return False
    fks = [l for l in fks if not _implied(l)]
    for t in tables:
        if roles[t]["role"] == "staging":
            continue
        in_l = [l for l in fks if l["ref_table"] == t and l["dep_table"] != t]
        out_l = [l for l in fks if l["dep_table"] == t and l["ref_table"] != t]
        roles[t] = core.classify(t.split(".")[-1], tables[t], keys.get(t, {}).get("best"), out_l, in_l, b)
    lv = core.lineage_levels([t for t in tables if roles[t]["role"] != "staging"], fks)
    der = core.derived_candidates(tables, roles, keys)
    # Unity Catalog metadata and lineage (st_meta); everything is optional
    meta = _meta(sid, root)
    lin = core.lineage_view(_rows_of(meta, "lineage"), _rows_of(meta, "column_lineage"), list(tables))
    for tgt, src in lin["derived"]:
        if not any(x["table"] == tgt and x["derived_from"] == src for x in der):
            der.append({"table": tgt, "derived_from": src, "shared_columns": "", "evidence": "Unity Catalog column lineage"})
    tmeta = {_short(r.get("table_name", "")): r for r in _rows_of(meta, "tables")}
    tmeta = {k.split(".")[-1]: v for k, v in tmeta.items()}
    det = {_short(r["table"]): r for r in _rows_of(meta, "detail_history")}
    ttags, ctags = {}, {}
    for r in _rows_of(meta, "tags"):
        if r.get("level") == "table":
            ttags.setdefault(str(r["table_name"]).lower(), []).append(f"{r['tag_name']}={r.get('tag_value') or ''}")
        else:
            ctags.setdefault((str(r["table_name"]).lower(), str(r.get("column_name")).lower()), []).append(f"{r['tag_name']}={r.get('tag_value') or ''}")
    masked = {(str(r["table_name"]).lower(), str(r.get("column_name") or "*").lower()) for r in _rows_of(meta, "masks_and_filters")}
    ccom = {(str(r["table_name"]).lower(), str(r["column_name"]).lower()): r.get("comment") for r in _rows_of(meta, "columns")}
    for t, info in tables.items():
        r = roles[t]
        cands = core.map_ontology(t.split(".")[-1], info, r, business, pref) if r["role"] != "staging" else []
        oc = core.ontology_confidence(cands)
        k = keys.get(t, {}).get("best")
        trows.append({"table": t, "rows": info["row_count"], "columns": len(info["columns"]),
                      "key": " + ".join(k) if k else "", "other_keys": "; ".join(" + ".join(x) for x in keys.get(t, {}).get("keys", []) if x != k),
                      "grain": core.grain(t.split(".")[-1], k, r["role"]), "role": r["role"], "role_confidence": r["role_confidence"],
                      "role_reasons": r["role_reasons"], "role_alternatives": r["alternatives"], "data_class": r["data_class"],
                      "lineage_level": lv.get(t, "-"), "derived_from": ", ".join(x["derived_from"] for x in der if x["table"] == t),
                      "business_object": cands[0]["business_object"] if cands else "", "ontology_confidence": oc,
                      "ontology_alternatives": ", ".join(f"{c['business_object']}({c['score']})" for c in cands[1:]),
                      "decided_by": "code",
                      "uc_comment": (tmeta.get(t.split(".")[-1].lower()) or {}).get("comment") or "",
                      "uc_owner": (tmeta.get(t.split(".")[-1].lower()) or {}).get("table_owner") or "",
                      "uc_tags": "; ".join(ttags.get(t.split(".")[-1].lower(), [])),
                      "masked": "; ".join(sorted(c for (tt, c) in masked if tt == t.split(".")[-1].lower())),
                      "written_by": "; ".join(lin["writers"].get(t, [])),
                      "read_by": "; ".join(lin["readers"].get(t, [])),
                      "last_write": (det.get(_short(t)) or {}).get("last_write") or (det.get(_short(t)) or {}).get("last_modified") or "",
                      "change_data_feed": (det.get(_short(t)) or {}).get("change_data_feed", "")})
    allowed = _allowed_objects(sid, root)
    for r in trows:
        r["scope"], r["scope_reason"] = core.scope(r, allowed)
    trows.sort(key=lambda r: (r["lineage_level"] if isinstance(r["lineage_level"], int) and r["lineage_level"] >= 0 else 99, r["table"]))
    def _ck(t, c):
        return (t.split(".")[-1].lower(), c.lower())
    cols = [{k: v for k, v in p.items() if k not in ("topk",)} | {"top_values": "; ".join(f"{v}:{n}" for v, n in p.get("topk", [])[:10]),
             "uc_comment": ccom.get(_ck(t, p["column"])) or "", "uc_tags": "; ".join(ctags.get(_ck(t, p["column"]), [])),
             "masked": _ck(t, p["column"]) in masked or (t.split(".")[-1].lower(), "*") in masked}
            for t, info in tables.items() for p in info["columns"]]
    krows = [{"table": t, "key": " + ".join(x), "is_best": x == k.get("best"), "checks_used": k.get("checks")}
             for t, k in keys.items() for x in k.get("keys", [])] or [{"table": "", "key": "", "is_best": "", "checks_used": ""}]
    # columns joined by a link are one value domain (union-find); shared code domains already explained by links are not repeated
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for l in fks:
        for dc, rc in zip(core.link_cols(l["dep_column"]), core.link_cols(l["ref_column"])):
            parent[find((l["dep_table"], dc))] = find((l["ref_table"], rc))
    doms = [x for x in core.shared_domains({t: v for t, v in tables.items() if roles[t]["role"] != "staging"}, b)
            if find((x["table_a"], x["column_a"])) != find((x["table_b"], x["column_b"]))]
    _w_csv(os.path.join(d, "tables.csv"), trows)
    _w_csv(os.path.join(d, "columns.csv"), cols, ["table", "column", "type", "family", "null_pct", "approx_distinct", "stats_distinct",
                                                     "distinct_ratio", "min", "max", "min_len", "max_len", "avg_len", "patterns", "top_values",
                                                     "uc_comment", "uc_tags", "masked", "column_class", "suggested_use", "class_reasons",
                                                     "sample_rows"])
    # column classes (names + content + UC tags) and column scope; earlier human/agent decisions are kept
    fk_by = {}
    for l in fks:
        fk_by.setdefault(l["dep_table"], set()).update(core.link_cols(l["dep_column"]))
    cs_p = os.path.join(d, "column_scope.csv")
    prev = {(r["table"], r["column"]): r for r in csv.DictReader(open(cs_p, encoding="utf-8"))} if os.path.exists(cs_p) else {}
    scope_of = {"map": "in_scope", "technical_only": "technical", "out_of_scope": "out_of_scope", "drop": "out_of_scope", "review": "review"}
    cscope, cls_by = [], {}
    for t, info in tables.items():
        kcols = set(keys.get(t, {}).get("best") or [])
        nlog = core.log_name_count(info["columns"])
        for p_ in info["columns"]:
            c = core.classify_column(p_, kcols, fk_by.get(t, set()), ctags.get(_ck(t, p_["column"]), []),
                                     _ck(t, p_["column"]) in masked or (t.split(".")[-1].lower(), "*") in masked, nlog)
            cls_by[(t, p_["column"])] = c
            old = prev.get((t, p_["column"]))
            if old and old.get("decided_by", "code") != "code":
                cscope.append(old)
            else:
                cscope.append({"table": t, "column": p_["column"], "column_class": c["column_class"], "scope": scope_of[c["use"]],
                               "reason": c["reasons"], "decided_by": "code"})
    for row in cols:
        c = cls_by.get((row.get("table"), row.get("column")), {})
        row["column_class"], row["suggested_use"], row["class_reasons"] = c.get("column_class"), c.get("use"), c.get("reasons")
    _w_csv(cs_p, cscope, ["table", "column", "column_class", "scope", "reason", "decided_by"])
    for r in trows:
        mine = [x for x in cscope if x["table"] == r["table"]]
        r["columns_out_of_scope"] = ", ".join(x["column"] for x in mine if x["scope"] == "out_of_scope")
        r["columns_review"] = ", ".join(x["column"] for x in mine if x["scope"] == "review")
    _w_csv(os.path.join(d, "tables.csv"), trows)            # again: now with the column scope summary per table
    gaps = _doc_gaps(sid, tables, root)
    _w_csv(os.path.join(d, "doc_gaps.csv"),
           [{"kind": "documented_not_in_bronze", "item": x} for x in gaps["documented_not_in_bronze"]]
           + [{"kind": "in_bronze_not_documented", "item": x} for x in gaps["in_bronze_not_documented"]]
           + [{"kind": "column_documented_not_in_bronze", "item": f"{g['bronze_table']}.{g['column']}"} for g in gaps["columns"]],
           ["kind", "item"])
    overlap = _overlap(sid, trows, root)
    _w_csv(os.path.join(d, "overlap.csv"), overlap, ["business_object", "this_table", "other_source", "other_table"])
    _w_json(os.path.join(d, "lineage_view.json"), lin)
    _w_csv(os.path.join(d, "keys.csv"), krows)
    lcols = ["dep_table", "dep_column", "ref_table", "ref_column", "status", "cardinality", "containment_raw", "containment_norm",
             "coverage", "dep_distinct", "ref_distinct", "score", "missing_examples", "note"]
    links = [l for l in links if roles[l["dep_table"]]["role"] != "staging" and roles[l["ref_table"]]["role"] != "staging"]
    _w_csv(os.path.join(d, "links.csv"), sorted(links, key=lambda l: (l["status"] != "fk", l["dep_table"])), lcols)
    _w_csv(os.path.join(d, "domains.csv"), doms, ["table_a", "column_a", "table_b", "column_b", "jaccard", "shared_values"])
    _w_csv(os.path.join(d, "derived.csv"), der, ["table", "derived_from", "shared_columns", "evidence"])
    graph = {"nodes": [{"table": r["table"], "role": r["role"], "level": r["lineage_level"], "business_object": r["business_object"]} for r in trows],
             "edges": [{"from": f"{l['dep_table']}.{l['dep_column']}", "to": f"{l['ref_table']}.{l['ref_column']}", "kind": "fk",
                        "cardinality": l["cardinality"], "containment": max(l["containment_raw"], l["containment_norm"])} for l in fks]
             + [{"from": x["table"], "to": x["derived_from"], "kind": "derived_from"} for x in der]}
    _w_json(os.path.join(d, "graph.json"), graph)
    _write_mermaid(d, trows, fks, der)
    _write_summary(d, sid, trows, fks, der, doms, b)
    _log(sid, "model", "done", f"{len(trows)} tables, {len(fks)} links, {len(gaps['documented_not_in_bronze'])} doc gaps, "
                               f"{len(overlap)} cross-source overlaps", root)
    return trows


def _allowed_objects(sid, root=None):
    """Business objects this source may provide: sources.yaml business_objects + objects of its processes (process_objects)."""
    s = source_cfg(sid, root)
    bus = _y(os.path.join(root or ROOT, "registry", "ontology", "business.yaml")) or {}
    out = set(s.get("business_objects") or [])
    for p in s.get("processes") or []:
        po = (bus.get("process_objects") or {}).get(p) or {}
        out |= set(po.get("C") or []) | set(po.get("U") or [])
    return out


def _doc_gaps(sid, tables, root=None):
    """Tables and columns named in the documents (client profiling workbooks + evidence register) vs bronze."""
    sdir = os.path.join(root or ROOT, "sources", sid)
    doc_t, doc_c = set(), {}
    p = os.path.join(sdir, "02_evidence", "profiling", "doc_profiles.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r.get("table"):
                doc_t.add(r["table"])
                doc_c.setdefault(r["table"], set()).add(r["column"])
    p = os.path.join(sdir, "02_evidence", "evidence_register.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r.get("origin") == "document" and r.get("about_type") in ("table", "column", "key", "grain"):
                tok = str(r.get("about", "")).split("->")[0].strip().split(".")[0].strip()
                if tok and tok.replace("_", "").isalnum():
                    doc_t.add(tok)
    bronze = {t: {c["column"] for c in info["columns"]} for t, info in tables.items()}
    return core.doc_gaps(doc_t, doc_c, bronze)


def _overlap(sid, trows, root=None):
    """The same business object found in other sources (input for survivorship / CP3). Raises one upstream item per object."""
    import x_feedback as fb
    root = root or ROOT
    mine = {r["business_object"]: r["table"] for r in trows
            if r.get("business_object") and not str(r["business_object"]).startswith("NEW:") and r["role"] != "staging"
            and r["business_object"] != "none"}
    out = []
    for p in glob.glob(os.path.join(root, "sources", "*", "02_evidence", "discovery", "tables.csv")):
        other = p.split(os.sep)[-4]
        if other == sid:
            continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r.get("business_object") in mine and r.get("role") != "staging":
                out.append({"business_object": r["business_object"], "this_table": mine[r["business_object"]],
                            "other_source": other, "other_table": r["table"]})
    existing = {(d.get("checkpoint"), d.get("comment")) for d in fb.all_feedback(root)}
    for bo in sorted({o["business_object"] for o in out}):
        srcs = sorted({sid} | {o["other_source"] for o in out if o["business_object"] == bo})
        text = f"Business object {bo} is found in several sources {srcs}: check survivorship rules and key conformance (CP3b)."
        if ("CP3_central_model", text) not in existing:
            fb.raise_item("global", "CP3_central_model", "p2-2-bronze-discovery", text, root=root)
    return out


def _write_mermaid(d, trows, fks, der):
    def n(t):
        return t.split(".")[-1]
    L = ["erDiagram"]
    for l in fks:
        if l["dep_table"] == l["ref_table"]:
            continue
        rel = "}o--||" if l["cardinality"] == "N:1" else "|o--||"
        L.append(f'  {n(l["dep_table"])} {rel} {n(l["ref_table"])} : "{l["dep_column"]}"')
    for x in der:
        L.append(f'  {n(x["table"])} }}o..o{{ {n(x["derived_from"])} : "derived from"')
    for r in trows:
        L.append(f'  {n(r["table"])} {{ string role "{r["role"]}" }}')
    with open(os.path.join(d, "bronze_er.mmd"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def _extra_sections(d, trows):
    """Unity Catalog metadata, platform lineage, documentation gaps, related tables, and cross-source overlap."""
    def rd(n):
        p = os.path.join(d, n)
        return list(csv.DictReader(open(p, encoding="utf-8"))) if os.path.exists(p) else []
    L = []
    av = rd(os.path.join("metadata", "availability.csv"))
    if av:
        L += ["", "## Unity Catalog metadata", "",
              "Sections: " + ", ".join(f"{r['section']} {'ok (' + r['rows'] + ')' if r['available'] == 'True' else 'not available'}" for r in av) + "."]
        no_comment = [r["table"].split(".")[-1] for r in trows if r["role"] != "staging" and not r.get("uc_comment")]
        if no_comment:
            L.append(f"Tables without a comment: {', '.join(no_comment)}.")
        m = [f"{r['table'].split('.')[-1]} ({r['masked']})" for r in trows if r.get("masked")]
        if m:
            L.append(f"**Masked or filtered (profiling results are not complete):** {', '.join(m)}.")
        t = [f"{r['table'].split('.')[-1]}: {r['uc_tags']}" for r in trows if r.get("uc_tags")]
        if t:
            L.append("Table tags: " + "; ".join(t) + ".")
        for r in rd(os.path.join("metadata", "constraints.csv"))[:20]:
            L.append(f"- declared {r.get('type')} on {r.get('table')}: {r.get('columns')}" + (f" -> {r.get('ref_table')}" if r.get("ref_table") else ""))
    lv_p = os.path.join(d, "lineage_view.json")
    if os.path.exists(lv_p):
        lv = json.load(open(lv_p, encoding="utf-8"))
        if lv.get("writers") or lv.get("readers") or lv.get("upstream_outside"):
            L += ["", "## Platform lineage (system.access)", ""]
            L += [f"- {t.split('.')[-1]} written by: {', '.join(w)}" for t, w in lv.get("writers", {}).items()]
            if lv.get("upstream_outside"):
                L.append(f"- Upstream tables outside this source: {', '.join(lv['upstream_outside'])}")
            L += [f"- {t.split('.')[-1]} read by: {', '.join(r[:5])}" for t, r in lv.get("readers", {}).items()]
    g = rd("doc_gaps.csv")
    if g:
        L += ["", "## Documents vs bronze", ""]
        for kind, label in (("documented_not_in_bronze", "Named in documents, NOT in bronze"), ("in_bronze_not_documented", "In bronze, NOT in documents"),
                            ("column_documented_not_in_bronze", "Documented columns missing in bronze")):
            items = [r["item"] for r in g if r["kind"] == kind]
            if items:
                L.append(f"- {label}: {', '.join(items[:20])}")
    rel = rd("related.csv")
    if rel:
        L += ["", "## Related tables outside this schema (cards R-xxx)", ""]
        L += [f"- {r['table']} (score {r['score']}): {r['why']}" + (f"; value overlap {r.get('overlap')}" if r.get("overlap") else "") for r in rel]
    ov = rd("overlap.csv")
    if ov:
        L += ["", "## Same business object in other sources (raised to CP3)", ""]
        L += [f"- {r['business_object']}: {r['this_table'].split('.')[-1]} ~ {r['other_source']} {r['other_table'].split('.')[-1]}" for r in ov]
    return L


def _write_summary(d, sid, trows, fks, der, doms, b):
    L = [f"# Bronze discovery: {sid}", "",
         "Read this file first. Full detail: tables.csv, columns.csv, keys.csv, links.csv, domains.csv, derived.csv, graph.json.", "",
         "## Tables (lineage level 0 = root)", "", "| lvl | table | role (conf) | grain key | business object (conf) | scope |", "|---|---|---|---|---|---|"]
    for r in trows:
        L.append(f"| {r['lineage_level']} | {r['table'].split('.')[-1]} | {r['role']} ({r['role_confidence']}) | {r['key'] or '-'} | "
                 f"{r['business_object'] or '-'} ({r['ontology_confidence']}) | {r.get('scope', '')} |")
    L += ["", "Confidence 'agent' = decided on a card (see tables.csv decided_by)."]
    L += ["", "## Links (foreign-key candidates)", "", "| from | to | card. | containment raw / normalised | note |", "|---|---|---|---|---|"]
    for l in fks:
        L.append(f"| {l['dep_table'].split('.')[-1]}.{l['dep_column']} | {l['ref_table'].split('.')[-1]}.{l['ref_column']} | {l['cardinality']} | "
                 f"{l['containment_raw']} / {l['containment_norm']} | {l['note']} |")
    if der:
        L += ["", "## Derived tables", ""] + [f"- {x['table'].split('.')[-1]} <- {x['derived_from'].split('.')[-1]}: {x['evidence']}" for x in der]
    if doms:
        L += ["", "## Shared code domains", ""] + [f"- {x['table_a'].split('.')[-1]}.{x['column_a']} ~ {x['table_b'].split('.')[-1]}.{x['column_b']} (Jaccard {x['jaccard']})" for x in doms[:15]]
    L += _extra_sections(d, trows)
    L += ["", f"Budgets: sample {b.get('sample_rows')} rows/table, max {b.get('max_key_checks')} key checks/table, max {b.get('max_link_checks')} link checks."]
    with open(os.path.join(d, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def st_wider(spark, sid, root=None, **_):
    """Look OUTSIDE the source schema for tables that may belong to this source (Unity Catalog search + lineage),
    then check value overlap on a shared key column for the best candidates. Writes related.csv (cards R-xxx)."""
    from discovery import spark_io, uc
    root = root or ROOT
    d = ddir(sid, root)
    b = budgets(root)
    s = source_cfg(sid, root)
    tables, keys = _load_parts(sid, root)
    business = _y(os.path.join(root, "registry", "ontology", "business.yaml")) or {}
    schema = s["bronze_schema"].split(".")[-1]
    cat = s["bronze_schema"].split(".")[0] if s["bronze_schema"].count(".") == 1 else None
    catalogs = (s.get("discovery") or {}).get("search_catalogs") or ([cat] if cat else [])
    tokens = set(core.tokens(schema)) | set(core.tokens(sid.split("_", 1)[-1]))
    for bo in s.get("business_objects") or []:
        o = (business.get("business_objects") or {}).get(bo) or {}
        tokens |= {bo.lower()} | {x.replace(" ", "_") for x in o.get("synonyms", [])}
    gaps_p = os.path.join(d, "doc_gaps.csv")
    if os.path.exists(gaps_p):
        tokens |= {r["item"].lower() for r in csv.DictReader(open(gaps_p, encoding="utf-8")) if r["kind"] == "documented_not_in_bronze"}
    tokens -= {"master", "data", "table", "tables", "bronze", "silver", "the", "and", "moves", "track"} if len(tokens) > 3 else set()
    key_cols = sorted({c.lower() for k in keys.values() for kk in (k.get("keys") or []) for c in kk})
    found = uc.related_candidates(spark, catalogs, schema, sorted(tokens), key_cols, b) if catalogs else \
        {"available": False, "reason": "no catalog: give bronze_schema as catalog.schema or discovery.search_catalogs", "rows": []}
    lv_p = os.path.join(d, "lineage_view.json")
    upstream = json.load(open(lv_p))["upstream_outside"] if os.path.exists(lv_p) else []
    ours = {_short(t) for t in tables}
    ranked = [r for r in core.score_related(found.get("rows"), upstream, b) if _short(r["table"]) not in ours]
    shared_by = {f"{r['table_catalog']}.{r['table_schema']}.{r['table_name']}": [c for c in (r.get("shared_columns") or []) if c]
                 for r in found.get("rows") or []}
    for r in ranked[: b.get("related_value_checks", 5)]:
        cols = shared_by.get(r["table"]) or []
        best = None
        for t, info in tables.items():
            for p in info["columns"]:
                if p["column"].lower() in {c.lower() for c in cols} and (not best or (p.get("approx_distinct") or 0) > best[2]):
                    best = (t, p["column"], p.get("approx_distinct") or 0)
        if best:
            try:
                other_col = next(c for c in cols if c.lower() == best[1].lower())
                m = spark_io.containment(spark, {"dep_table": r["table"], "dep_column": other_col, "ref_table": best[0], "ref_column": best[1]}, b)
                r["overlap"] = (f"{m['containment_norm']:.0%} of {r['table'].split('.')[-1]}.{other_col} values are in "
                                f"{best[0].split('.')[-1]}.{best[1]}; {m['coverage']:.0%} coverage")
            except Exception as e:  # noqa: BLE001
                r["overlap"] = f"not checked: {type(e).__name__}"
    _w_csv(os.path.join(d, "related.csv"), ranked, ["table", "score", "why", "overlap"])
    _log(sid, "wider", "done", f"{len(ranked)} related candidates; search {'ok' if found.get('available') else 'n/a: ' + found.get('reason', '')}", root)
    return ranked


CARD_SCHEMA = """```yaml
# write as cards/<card id>.result.yaml
card: <card id>
role: master | reference | transaction_header | transaction_line | event | snapshot | bridge | aggregate | technical | staging
business_object: <name from business.yaml> | NEW:<proposed name> | none
grain_key: [<col>, ...]
accept_links: [<from> -> <to>, ...]
reject_links: [<from> -> <to>, ...]
load_to_silver: yes | no | derive_instead      # logs/audit/sessions/config: no; aggregates: usually derive_instead
reason: <max 40 words>
evidence: [<file + row/column you used>]
raise_upstream: null | <comment for an earlier checkpoint>
columns: {<COLUMN>: keep | out_of_scope | mask}   # only for columns listed under "columns to confirm"
```"""


def _card_id(cdir, table):
    """Stable card id per table (cards/index.json), so re-running discovery never re-numbers answered cards."""
    p = os.path.join(cdir, "index.json")
    idx = _r_json(p) if os.path.exists(p) else {}
    if not idx:                                       # adopt ids of existing cards (older runs)
        for f in glob.glob(os.path.join(cdir, "T-*.md")):
            t = _card_table(f)
            if t:
                idx[t] = os.path.basename(f)[:-3]
    if table not in idx:
        n = max([int(v.split("-")[1]) for v in idx.values()] or [0]) + 1
        idx[table] = f"T-{n:03d}"
    _w_json(p, idx)
    return idx[table]


def _card_table(card_md):
    """Table named in the first line of a T-card: '# Card T-001: <table>'."""
    if not os.path.exists(card_md):
        return None
    first = open(card_md, encoding="utf-8").readline().strip()
    return first.split(": ", 1)[1].strip() if ": " in first else None


def st_cards(spark, sid, root=None, **_):
    """One card per decision code could not make. Each card is self-contained (one agent, one chat)."""
    root = root or ROOT
    d = ddir(sid, root)
    b = budgets(root)
    business = _y(os.path.join(root, "registry", "ontology", "business.yaml"))
    tables, keys = _load_parts(sid, root)
    with open(os.path.join(d, "tables.csv"), encoding="utf-8") as f:
        trows = list(csv.DictReader(f))
    with open(os.path.join(d, "links.csv"), encoding="utf-8") as f:
        links = list(csv.DictReader(f))
    cdir = os.path.join(d, "cards")
    os.makedirs(cdir, exist_ok=True)
    made = []
    for i, r in enumerate(trows, 1):
        why = []
        if r.get("scope") == "review":
            why.append(f"scope: {r.get('scope_reason')} -> load to silver, or out of scope?")
        if r.get("scope") in ("in_scope", "review") and (r.get("columns_review") or r.get("columns_out_of_scope")):
            why.append(f"columns to confirm: review [{r.get('columns_review') or '-'}], out of scope by default "
                       f"[{r.get('columns_out_of_scope') or '-'}] (see column_scope.csv for the reasons)")
        if r["role"] not in ("staging",) and r.get("scope") != "out_of_scope":
            if r["role_confidence"] != "high":
                why.append(f"role is '{r['role']}' with {r['role_confidence']} confidence (alternatives: {r['role_alternatives'] or 'none'})")
            if r["ontology_confidence"] in ("low", "none"):
                why.append(f"business object match is {r['ontology_confidence']}")
            if not r["key"]:
                why.append("no unique key found")
        t = r["table"]
        part = [l for l in links if (l["dep_table"] == t or l["ref_table"] == t) and l["status"] == "fk_partial"]
        if part:
            why.append(f"{len(part)} partial link(s) (some values have no parent)")
        if r["role"] == "aggregate":
            why.append(f"aggregate table (derived from: {r['derived_from'] or 'unknown'}): load it, or derive the numbers in silver/gold instead?")
        if not why:
            continue
        cid = _card_id(cdir, t)
        info = tables[t]
        colines = [f"| {p['column']} | {p['type']} | {p['null_pct']} | {p['approx_distinct']} | {', '.join(p.get('patterns') or [])} | "
                   f"{'; '.join(str(v) for v, _ in (p.get('topk') or [])[:5])} |" for p in info["columns"][: b.get("card_max_columns", 30)]]
        lks = [f"- {l['dep_table'].split('.')[-1]}.{l['dep_column']} -> {l['ref_table'].split('.')[-1]}.{l['ref_column']}: {l['status']}, "
               f"containment {l['containment_raw']}/{l['containment_norm']}, {l['note']}" for l in links if (l["dep_table"] == t or l["ref_table"] == t) and l["status"] != "no_link"]
        objs = ", ".join(f"{n} ({o['kind']})" for n, o in business["business_objects"].items())
        L = [f"# Card {cid}: {t}", "", f"Source: {sid}. Status: open. One card = one agent chat. Do not open other cards.", "",
             "## Decide", ""] + [f"- {w}" for w in why] + [
             "", "## Facts from code (do not re-profile; ask for a data check by feedback if needed)", "",
             f"Rows: {info['row_count']}. Sample rows: {info['sample_rows']}. Best key: {r['key'] or 'none'}. Other keys: {r['other_keys'] or 'none'}.",
             f"Code proposal: role **{r['role']}** ({r['role_reasons']}); business object **{r['business_object'] or 'none'}** "
             f"(alternatives: {r['ontology_alternatives'] or 'none'}); derived from: {r['derived_from'] or 'none'}.", "",
             "| column | type | null % | distinct | shapes | top values |", "|---|---|---|---|---|---|"] + colines + [
             "", "Links:"] + (lks or ["- none"]) + [
             "", "## Allowed values", "", f"Business objects: {objs}.", "",
             "Use only the source brief (01_intake/source_brief.md) and the evidence register as extra context.", "",
             "## Answer format", "", CARD_SCHEMA, ""]
        with open(os.path.join(cdir, f"{cid}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(L))
        made.append(cid)
    # R-cards: tables outside the schema that may belong to this source
    rel_p = os.path.join(d, "related.csv")
    if os.path.exists(rel_p):
        for i, r in enumerate(csv.DictReader(open(rel_p, encoding="utf-8")), 1):
            cid = f"R-{i:03d}"
            L = [f"# Card {cid}: does {r['table']} belong to {sid}?", "", "One card = one agent chat.", "",
                 f"Why code found it: {r['why']}.", f"Value overlap: {r.get('overlap') or 'not checked'}.", "",
                 "Look only at this table's metadata (comment, owner, columns) in Catalog Explorer and at the source brief.", "",
                 "## Answer format", "", "```yaml", f"card: {cid}", f"table: {r['table']}",
                 "decision: include | ignore | other_source:<source id>", "reason: <max 40 words>", "```", ""]
            open(os.path.join(cdir, f"{cid}.md"), "w", encoding="utf-8").write("\n".join(L))
            made.append(cid)
    # D-card: tables the documents name but bronze does not have
    gp = os.path.join(d, "doc_gaps.csv")
    miss = [r["item"] for r in csv.DictReader(open(gp, encoding="utf-8")) if r["kind"] == "documented_not_in_bronze"] if os.path.exists(gp) else []
    if miss:
        L = ["# Card D-001: tables named in the documents but not found in bronze", "", "One card = one agent chat (or the analyst).", "",
             "Tables: " + ", ".join(miss) + ".", "", "For each: where is it? Check related.csv, Catalog Explorer, and the source brief.", "",
             "## Answer format", "", "```yaml", "card: D-001", "items:",
             "  - {documented: <name>, decision: 'located:<catalog.schema.table>' | not_needed | ask_client}", "reason: <max 40 words>", "```", ""]
        open(os.path.join(cdir, "D-001.md"), "w", encoding="utf-8").write("\n".join(L))
        made.append("D-001")
    _log(sid, "cards", "done", f"{len(made)} cards", root)
    return made


def _add_question(sid, text, root=None):
    p = os.path.join(root or ROOT, "registry", "open_questions.yaml")
    doc = _y(p) or {"questions": []}
    qs = doc.setdefault("questions", []) or []
    if any(q.get("question") == text for q in qs):
        return None
    n = max([int(str(q["id"]).split("-")[-1]) for q in qs if str(q.get("id", "")).startswith("Q-") and str(q["id"]).split("-")[-1].isdigit()] or [0]) + 1
    qs.append({"id": f"Q-{n:04d}", "source_id": sid, "blocking": False, "status": "open", "raised_by": "p2-2-bronze-discovery",
               "owner": "client", "question": text, "evidence": "02_evidence/discovery/doc_gaps.csv", "answer": None, "answered_on": None})
    doc["questions"] = qs
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, sort_keys=False)
    return f"Q-{n:04d}"


def _apply_column_decisions(d, table, decisions, cid):
    p = os.path.join(d, "column_scope.csv")
    if not os.path.exists(p):
        return
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    m = {"keep": "in_scope", "out_of_scope": "out_of_scope", "mask": "in_scope_masked"}
    for r in rows:
        dec = (decisions or {}).get(r["column"])
        if r["table"] == table and dec in m:
            r["scope"], r["decided_by"], r["reason"] = m[dec], f"card {cid}", f"{dec} (card {cid})"
    _w_csv(p, rows, ["table", "column", "column_class", "scope", "reason", "decided_by"])


def merge(sid, root=None):
    root = root or ROOT
    d = ddir(sid, root)
    with open(os.path.join(d, "tables.csv"), encoding="utf-8") as f:
        trows = list(csv.DictReader(f))
    res = {}
    for f in glob.glob(os.path.join(d, "cards", "*.result.yaml")):
        x = _y(f)
        res[x["card"]] = x
    by_table = {}
    for cid, x in res.items():
        if cid.startswith("T-"):
            tbl = x.get("table") or _card_table(os.path.join(d, "cards", f"{cid}.md"))
            if tbl:
                x["table"] = tbl
                by_table[tbl] = (cid, x)
    applied = []
    for i, r in enumerate(trows, 1):
        cid, x = by_table.get(r["table"], (None, None))
        if not x:
            continue
        for k_from, k_to in (("role", "role"), ("business_object", "business_object")):
            if x.get(k_from):
                r[k_to] = x[k_from]
        if x.get("grain_key"):
            r["key"] = " + ".join(x["grain_key"])
        r["data_class"] = core.ROLE_TO_CLASS.get(r["role"]) or r["data_class"]
        r["role_confidence"] = r["ontology_confidence"] = "agent"
        r["decided_by"] = f"card {cid}: {x.get('reason', '')}"
        lts = x.get("load_to_silver", "")
        r["load_to_silver"] = ("yes" if lts else "no") if isinstance(lts, bool) else lts
        if r["load_to_silver"]:
            r["scope"] = {"yes": "in_scope", "no": "out_of_scope", "derive_instead": "derive_instead"}.get(r["load_to_silver"], r.get("scope", ""))
            r["scope_reason"] = f"card {cid}: {str(x.get('reason', ''))[:80]}"
        applied.append(cid)
        if x.get("columns"):
            _apply_column_decisions(d, r["table"], x["columns"], cid)
    allk = list(dict.fromkeys(k for r in trows for k in r))
    _w_csv(os.path.join(d, "tables.csv"), trows, allk + [k for k in ("load_to_silver", "scope", "scope_reason") if k not in allk])
    # upstream issues from card answers -> proposed feedback items (a person accepts or rejects them)
    import x_feedback as fb
    raised = []
    def _key(cp, text):                                   # card ids can change between runs: compare without them
        t = re.sub(r"^[TRD]-\d{3}: ", "", " ".join(str(text or "").split()))
        m = re.match(r"(new business object '[^']+' proposed for \S+?)\.?( |$)", t)
        return cp, (m.group(1) if m else t)
    existing = {_key(x.get("checkpoint"), x.get("comment")) for x in fb.all_feedback(root)}
    for cid, x in sorted(res.items()):
        bo = str(x.get("business_object") or "")
        items = []
        if bo.startswith("NEW:"):
            items.append(("global", "CP3_central_model", f"{cid}: new business object '{bo[4:]}' proposed for {x.get('table', cid)}. {x.get('reason', '')}"))
        if x.get("raise_upstream"):
            items.append((sid, "CP1_source_brief", f"{cid}: {x['raise_upstream']}"))
        for src, cp, text in items:
            if _key(cp, text) not in existing:
                existing.add(_key(cp, text))
                raised.append(fb.raise_item(src, cp, "p2-2-bronze-discovery", text, blocks="CP2_evidence" if src != "global" else None, root=root))
    # R- and D-cards: tables outside the schema to include, and documented tables to locate
    extra, notes = [], []
    for cid, x in sorted(res.items()):
        if cid.startswith("R-") and str(x.get("decision", "")) == "include" and x.get("table"):
            extra.append(x["table"])
        elif cid.startswith("R-") and str(x.get("decision", "")).startswith("other_source:"):
            notes.append(f"{x.get('table')} belongs to {x['decision'].split(':', 1)[1]}")
        if cid.startswith("D-"):
            for it in x.get("items") or []:
                dec = str(it.get("decision", ""))
                if dec.startswith("located:"):
                    extra.append(dec.split(":", 1)[1].strip())
                elif dec == "ask_client":
                    _add_question(sid, f"The documents name table {it.get('documented')}, but it is not in bronze. Where is it, and is it needed?", root)
    if extra:
        p_ = os.path.join(root, "registry", "sources.yaml")
        reg_ = _y(p_)
        for s_ in reg_["sources"]:
            if s_["id"] == sid:
                dc_ = s_.setdefault("discovery", {}) or {}
                s_["discovery"] = dc_
                dc_["extra_tables"] = sorted(set(dc_.get("extra_tables") or []) | set(extra))
        with open(p_, "w", encoding="utf-8") as f:
            yaml.safe_dump(reg_, f, sort_keys=False)
        notes.append(f"added to discovery.extra_tables: {extra}; run discovery again to profile them")

    def _rd(n):
        with open(os.path.join(d, n), encoding="utf-8") as f:
            return list(csv.DictReader(f))
    _write_summary(d, sid, trows, [l for l in _rd("links.csv") if l["status"] in ("fk", "fk_partial")], _rd("derived.csv"),
                   _rd("domains.csv"), budgets(root))
    _log(sid, "merge", "done", f"applied {applied}; raised {raised}" + (f"; {'; '.join(notes)}" if notes else ""), root)
    return applied


def to_evidence(sid, root=None):
    """Append bronze facts from discovery to 02_evidence/evidence_register.csv (idempotent).

    One claim per table grain key, per foreign-key link, and per key that needs normalisation.
    origin = bronze_profile, status = confirmed_by_bronze, location = the discovery file + item.
    """
    root = root or ROOT
    d = ddir(sid, root)
    reg_p = os.path.join(root, "sources", sid, "02_evidence", "evidence_register.csv")
    cols = ["evidence_id", "claim", "about_type", "about", "origin", "file_id", "location", "doc_type", "confidence", "status", "corroborated_by", "notes"]
    rows = []
    if os.path.exists(reg_p):
        with open(reg_p, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    have = {(r["about"], r["location"]) for r in rows}
    nxt = max([int(r["evidence_id"][2:]) for r in rows] or [0]) + 1
    with open(os.path.join(d, "tables.csv"), encoding="utf-8") as f:
        trows = list(csv.DictReader(f))
    with open(os.path.join(d, "links.csv"), encoding="utf-8") as f:
        links = [l for l in csv.DictReader(f) if l["status"] in ("fk", "fk_partial")]
    new = []

    def add(claim, about_type, about, loc, conf="high", notes=""):
        nonlocal nxt
        if (about, loc) in have:
            return
        new.append({"evidence_id": f"E-{nxt:04d}", "claim": claim, "about_type": about_type, "about": about, "origin": "bronze_profile",
                    "file_id": "", "location": loc, "doc_type": "", "confidence": conf, "status": "confirmed_by_bronze",
                    "corroborated_by": loc, "notes": notes})
        have.add((about, loc))
        nxt += 1
    for r in trows:
        if r["role"] == "staging" or not r["key"]:
            continue
        t = r["table"].split(".")[-1]
        add(f"{t}: {r['key']} is unique and not null in all {r['rows']} rows (role {r['role']}).", "grain", f"{t}.{r['key']}",
            f"02_evidence/discovery/keys.csv#{t}", notes=f"decided_by {r['decided_by'][:60]}")
    for l in links:
        dt, rt = l["dep_table"].split(".")[-1], l["ref_table"].split(".")[-1]
        best = max(float(l["containment_raw"] or 0), float(l["containment_norm"] or 0))
        add(f"{best:.1%} of distinct {dt}.{l['dep_column']} values exist in {rt}.{l['ref_column']} ({l['cardinality']}).",
            "relationship", f"{dt}.{l['dep_column']} -> {rt}.{l['ref_column']}", f"02_evidence/discovery/links.csv#{dt}.{l['dep_column']}",
            conf="high" if l["status"] == "fk" else "medium", notes=l["note"][:120])
    rows += new
    with open(reg_p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    _log(sid, "evidence", "done", f"{len(new)} claims added", root)
    return [n["evidence_id"] for n in new]


# ----------------------------------------------------------------------------- plan, job, status
def plan(sid, root=None):
    root = root or ROOT
    s = source_cfg(sid, root)
    repo_path = "{{job.parameters.repo_path}}"
    job = {"name": f"discover_{sid}", "max_concurrent_runs": 1,
           "parameters": [{"name": "repo_path", "default": "/Workspace/Repos/<user>/silver-modelling"}, {"name": "source_id", "default": sid}],
           "tasks": [
               {"task_key": "catalog", "notebook_task": {"notebook_path": f"{repo_path}/tools/discovery/run_task", "base_parameters": {"stage": "catalog+meta"}}},
               {"task_key": "list_tables", "depends_on": [{"task_key": "catalog"}],
                "notebook_task": {"notebook_path": f"{repo_path}/tools/discovery/run_task", "base_parameters": {"stage": "emit-tables"}}},
               {"task_key": "profile_and_keys", "depends_on": [{"task_key": "list_tables"}],
                "for_each_task": {"inputs": "{{tasks.list_tables.values.tables}}", "concurrency": 8,
                                  "task": {"task_key": "profile_and_keys_iter",
                                           "notebook_task": {"notebook_path": f"{repo_path}/tools/discovery/run_task",
                                                             "base_parameters": {"stage": "profile+keys", "table": "{{input}}"}}}}},
               {"task_key": "plan_links", "depends_on": [{"task_key": "profile_and_keys"}],
                "notebook_task": {"notebook_path": f"{repo_path}/tools/discovery/run_task", "base_parameters": {"stage": "plan-links"}}},
               {"task_key": "links", "depends_on": [{"task_key": "plan_links"}],
                "for_each_task": {"inputs": "{{tasks.plan_links.values.batches}}", "concurrency": 8,
                                  "task": {"task_key": "links_iter",
                                           "notebook_task": {"notebook_path": f"{repo_path}/tools/discovery/run_task",
                                                             "base_parameters": {"stage": "links", "batch": "{{input}}"}}}}},
               {"task_key": "model_and_cards", "depends_on": [{"task_key": "links"}],
                "notebook_task": {"notebook_path": f"{repo_path}/tools/discovery/run_task", "base_parameters": {"stage": "model+cards"}}}],
           "tags": {"phase": "P2", "source_id": sid}}
    d = ddir(sid, root)
    _w_json(os.path.join(d, "job.json"), job)
    pl = {"source_id": sid, "bronze_schema": s["bronze_schema"], "budgets": budgets(root),
          "stages": [{"stage": "catalog", "runs": "once", "kind": "code"},
                     {"stage": "meta", "runs": "once (Unity Catalog metadata + lineage, no data read)", "kind": "code"},
                     {"stage": "profile", "runs": "per table (parallel)", "kind": "code"},
                     {"stage": "keys", "runs": "per table (parallel)", "kind": "code"},
                     {"stage": "plan-links", "runs": "once", "kind": "code"},
                     {"stage": "links", "runs": "per batch (parallel)", "kind": "code"},
                     {"stage": "model", "runs": "once", "kind": "code"},
                     {"stage": "wider", "runs": "once (tables outside the schema, value overlap)", "kind": "code"},
                     {"stage": "cards", "runs": "once; then one agent per card (parallel)", "kind": "agent"},
                     {"stage": "merge", "runs": "once after all cards answered", "kind": "code"}]}
    with open(os.path.join(d, "plan.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(pl, f, sort_keys=False)
    return pl


def status(sid, root=None):
    d = ddir(sid, root)
    p = os.path.join(d, "tasks.jsonl")
    done = [json.loads(x) for x in open(p, encoding="utf-8")] if os.path.exists(p) else []
    cards = sorted(os.path.basename(f)[:-3] for f in glob.glob(os.path.join(d, "cards", "[TRD]-*.md")))
    answered = {os.path.basename(f).split(".")[0] for f in glob.glob(os.path.join(d, "cards", "*.result.yaml"))}
    return {"tasks_done": len(done), "last": done[-1] if done else None,
            "cards_open": [c for c in cards if c not in answered], "cards_answered": sorted(answered)}


def run(spark, sid, stage, table=None, batch=None, root=None):
    if stage == "all":
        cat = st_catalog(spark, sid, root)
        st_meta(spark, sid, root)
        for r in cat:
            st_profile(spark, sid, r["table"], root)
            st_keys(spark, sid, r["table"], root)
        for i, _ in enumerate(st_plan_links(spark, sid, root)):
            st_links(spark, sid, i, root)
        st_model(spark, sid, root)
        st_wider(spark, sid, root)
        st_model(spark, sid, root)          # again, so summary.md also lists the related tables
        return st_cards(spark, sid, root)
    if stage == "catalog+meta":
        st_catalog(spark, sid, root)
        return st_meta(spark, sid, root)
    if stage == "profile+keys":
        st_profile(spark, sid, table, root)
        return st_keys(spark, sid, table, root)
    if stage == "model+cards":
        st_model(spark, sid, root)
        st_wider(spark, sid, root)
        st_model(spark, sid, root)
        return st_cards(spark, sid, root)
    fn = {"catalog": st_catalog, "meta": st_meta, "profile": st_profile, "keys": st_keys, "plan-links": st_plan_links,
          "links": st_links, "model": st_model, "wider": st_wider, "cards": st_cards}[stage]
    kw = {"table": table} if stage in PER_TABLE else {"batch": batch} if stage == "links" else {}
    return fn(spark, sid, root=root, **kw)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["plan", "run", "status", "merge", "evidence"])
    ap.add_argument("source_id")
    ap.add_argument("--stage", choices=STAGES + ["all", "catalog+meta", "profile+keys", "model+cards"])
    ap.add_argument("--table")
    ap.add_argument("--batch")
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        print(yaml.safe_dump(plan(a.source_id), sort_keys=False))
    elif a.cmd == "status":
        print(json.dumps(status(a.source_id), indent=2))
    elif a.cmd == "merge":
        print("applied:", merge(a.source_id))
    elif a.cmd == "evidence":
        print("added:", to_evidence(a.source_id))
    else:
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        r = run(spark, a.source_id, a.stage, a.table, a.batch)
        print(json.dumps(r, indent=2, default=str)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
