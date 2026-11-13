"""Canonical STTM (b2s.sttm) -> runtime table specs in the format lib/ uses (load_patterns, keys, qa_checks,
survivorship, uc_publish). Pure Python; deterministic."""
from __future__ import annotations

from .. import versions
from ..layout import Layout
from ..project import ontology

RULE_MAP = {"direct": "direct", "normalised_key": "normalised_key", "surrogate_key": "technical",
            "lookup_fk": "lookup", "derived": "derived", "constant": "constant", "technical": "technical"}


def _load_pattern(data_class: str, data: dict) -> str:
    allowed = ((data.get("data_classes") or {}).get(data_class) or {}).get("allowed_load_patterns") or ["merge"]
    if data_class == "master" and "scd2" in allowed:
        return "scd2"
    return "merge" if "merge" in allowed else allowed[0]


def approved_sttm(layout: Layout, app: str):
    """Latest STTM version approved at CP4 (or None)."""
    from ..approve import approved_versions
    tags = sorted(approved_versions(layout, app, "CP4").get("sttm/sttm", set()))
    return versions.get(layout.stem(app, "sttm/sttm"), int(tags[-1][1:]), "json") if tags else None


def runtime_tables(layout: Layout, app: str, sttm: dict) -> list[dict]:
    data = ontology(layout, "data")
    ents = {e["business_object"]: e for e in (ontology(layout, "entities").get("entities") or [])}
    by_name = {t["target_table"]: t for t in sttm["tables"]}

    def entity_of(t):
        e = ents.get(t.get("business_object"))
        return e if e and t.get("data_class") in ("master", "reference") else None

    out = []
    for t in sttm["tables"]:
        ent = entity_of(t)
        lp = t.get("load_pattern") or (ent or {}).get("load_pattern") or _load_pattern(t.get("data_class", "event"), data)
        pk, bk = list(t.get("primary_key") or []), list(t.get("business_key") or [])
        cols, sk = [], None
        for c in t["columns"]:
            rule = RULE_MAP.get(c.get("rule"), "derived")
            if c.get("rule") == "surrogate_key":
                sk = {"column": c["target_column"], "of": c.get("derived_from") or bk}
            col = {"target": c["target_column"], "type": str(c.get("type", "string")).upper(), "rule": rule,
                   "key_role": "PK" if c["target_column"] in pk else ("FK" if c.get("rule") == "lookup_fk" else
                                                                     ("BK" if c["target_column"] in bk else None)),
                   "nullable": c["target_column"] not in pk + bk, "status": c.get("status", "known")}
            src = c.get("source") or {}
            if src.get("columns"):
                col["source"] = src["columns"][0] if len(src["columns"]) == 1 else src["columns"]
            for k in ("key_rule", "privacy", "business_rule", "question", "assumption"):
                if c.get(k):
                    col[k] = c[k]
            fk = c.get("fk") or {}
            if fk.get("table"):
                parent = by_name.get(fk["table"], {})
                pent = entity_of(parent) if parent else None
                pbk = list((pent or {}).get("business_key") or parent.get("business_key") or [])
                psk = (pent or {}).get("surrogate_key") or next((x["target_column"] for x in parent.get("columns", [])
                                                                  if x.get("rule") == "surrogate_key"), None)
                col["fk"] = {**({"entity": pent["name"]} if pent else {"table": fk["table"]}),
                             "lookup_on": [x.split(".")[-1] for x in fk.get("lookup_on") or []],
                             "column": psk, "parent_bk": pbk, "cardinality": "N:1",
                             "orphan_policy": c.get("orphan_policy", "unknown_member" if pent else "reject")}
            cols.append(col)
        if lp == "scd2":
            for name in ("effective_from", "effective_to", "is_current"):
                if name not in {c["target"] for c in cols}:
                    cols.append({"target": name, "type": "TIMESTAMP" if name != "is_current" else "BOOLEAN",
                                 "rule": "technical", "key_role": None, "nullable": name != "effective_from"})
        out.append({
            "target_table": ent["target_table"] if ent else t["target_table"], "sttm_table": t["target_table"],
            "business_object": t.get("business_object"), "data_class": t.get("data_class"), "grain": t.get("grain"),
            "target_kind": "master" if ent else "process", "conformed_entity": ent["name"] if ent else None,
            "load_pattern": lp, "scd_type": 2 if lp == "scd2" else 1, "primary_key": pk, "business_key": bk,
            "surrogate_key": sk, "sources": [{"alias": "src" if i == 0 else f"src{i + 1}", "table": s}
                                             for i, s in enumerate(t.get("sources") or [])],
            "columns": cols})
    return out
