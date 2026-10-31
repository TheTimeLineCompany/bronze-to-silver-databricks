#!/usr/bin/env python3
"""Ontology coherence check across the three layers (business -> data -> information) and the registry.

Checks that the chain is unbroken from business meaning to bronze data:
  business.yaml   relationships, processes, process_objects, rules point to known objects/domains;
                  a synonym belongs to one object only and never equals another object's name
  data.yaml       data classes use valid business kinds
  entities.yaml   each entity names a known business_object and a conformed data_class whose kinds fit
  sources.yaml    each source names valid domains, processes, and business objects
  STTMs           each STTM passes tools/p4_2_validate_sttm.py (which checks business_object,
                  data_class, FK-relationship, business_rule, and evidence coherence)
  coverage        business objects that no source or entity covers (warning)

Usage:  python tools/x_ontology_check.py      Exit 0 = coherent, 1 = errors.
"""
from __future__ import annotations

import glob
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import p4_2_validate_sttm as vsttm  # noqa: E402


def _y(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return yaml.safe_load(f)


def check(root=ROOT):
    global ROOT
    ROOT = root
    errs, warns = [], []
    bus = _y("registry", "ontology", "business.yaml")
    data = _y("registry", "ontology", "data.yaml")
    info = _y("registry", "ontology", "information.yaml")
    ents = _y("registry", "entities.yaml")["entities"]
    srcs = _y("registry", "sources.yaml")["sources"]
    doms, procs, objs = bus["domains"], bus["processes"], bus["business_objects"]
    kinds = {o["kind"] for o in objs.values()}
    for n, o in objs.items():
        if o.get("domain") not in doms:
            errs.append(f"business object {n}: unknown domain {o.get('domain')}")
    seen = {}
    names = {n.lower() for n in objs}
    for n, o in objs.items():
        for syn in o.get("synonyms", []):
            k = syn.lower()
            if k in seen and seen[k] != n:
                errs.append(f"synonym '{syn}' used by both {seen[k]} and {n}")
            if k in names and k != n.lower():
                errs.append(f"synonym '{syn}' of {n} is the name of another business object")
            seen[k] = n
    for rid, r in bus.get("relationships", {}).items():
        for side in ("subject", "object"):
            if r[side] not in objs:
                errs.append(f"relationship {rid}: {side} '{r[side]}' is not a business object")
    for pid, p in procs.items():
        if p.get("domain") not in doms:
            errs.append(f"process {pid}: unknown domain {p.get('domain')}")
    for pid, po in bus.get("process_objects", {}).items():
        if pid not in procs:
            errs.append(f"process_objects: unknown process {pid}")
        for o in (po.get("C", []) + po.get("U", [])):
            if o not in objs:
                errs.append(f"process_objects {pid}: unknown object {o}")
    for bid, b in bus.get("business_rules", {}).items():
        if b.get("object") not in objs:
            errs.append(f"business rule {bid}: unknown object {b.get('object')}")
    dcs = data["data_classes"]
    for c, spec in dcs.items():
        for k in spec.get("business_kinds", []):
            if k not in kinds and k not in ("party", "thing", "place", "event", "agreement", "measure", "classification"):
                errs.append(f"data class {c}: unknown business kind {k}")
    for e in ents:
        bo, dc = e.get("business_object"), e.get("data_class")
        if bo not in objs:
            errs.append(f"entity {e['name']}: business_object '{bo}' not in business.yaml")
        if dc not in dcs:
            errs.append(f"entity {e['name']}: data_class '{dc}' not in data.yaml")
        elif not dcs[dc].get("conformed"):
            errs.append(f"entity {e['name']}: data_class '{dc}' is not a conformed class (use master or reference)")
        elif bo in objs and objs[bo]["kind"] not in dcs[dc]["business_kinds"]:
            errs.append(f"entity {e['name']}: kind '{objs[bo]['kind']}' does not fit data_class '{dc}'")
    covered = {e.get("business_object") for e in ents}
    for s in srcs:
        for d in s.get("domains", []):
            if d not in doms:
                errs.append(f"source {s['id']}: unknown domain {d}")
        for p in s.get("processes", []):
            if p not in procs:
                errs.append(f"source {s['id']}: unknown process {p}")
        for o in s.get("business_objects", []):
            if o not in objs:
                errs.append(f"source {s['id']}: unknown business object {o}")
            covered.add(o)
        for cp in s.get("checkpoints", {}):
            if cp not in info["checkpoints"]:
                errs.append(f"source {s['id']}: unknown checkpoint {cp}")
    ctx = vsttm.load_context(root)
    for f in sorted(glob.glob(os.path.join(root, "sources", "*", "04_mapping", "sttm.yaml"))):
        r = vsttm.validate(f, ctx, root)
        errs += [f"{r.file}: {e}" for e in r.errors]
        for t in (yaml.safe_load(open(f, encoding="utf-8")) or {}).get("tables", []):
            covered.add(t.get("business_object"))
    for o in objs:
        if o not in covered:
            warns.append(f"business object {o} is not yet covered by any source, entity, or STTM")

    # Shared masters fed by several sources: survivorship rules and consistent column types
    import glob as _g
    surv = (_y("registry", "key_normalisation.yaml") or {}).get("survivorship") or {}
    src_ids = {x["id"] for x in srcs}
    feed = {}
    for p in sorted(_g.glob(os.path.join(ROOT, "sources", "*", "04_mapping", "sttm.yaml"))):
        with open(p, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        for t in doc.get("tables", []):
            if t.get("conformed_entity"):
                feed.setdefault(t["conformed_entity"], []).append((doc.get("source_id"), t))
    for ent, lst in feed.items():
        if len(lst) > 1 and ent not in surv:
            errs.append(f"entity {ent} is mapped by {len(lst)} sources {[s for s, _ in lst]} but has no survivorship rules "
                        "in registry/key_normalisation.yaml (CP3b)")
        types = {}
        for sid, t in lst:
            for c in t["columns"]:
                types.setdefault(c["target"], set()).add(c["type"].upper())
        for col, ty in types.items():
            if len(ty) > 1:
                errs.append(f"entity {ent}: column {col} has different types across sources {sorted(ty)}")
        cols = set(types)
        for a, r in ((surv.get(ent) or {}).get("attributes") or {}).items():
            if a not in cols:
                warns.append(f"survivorship {ent}.{a}: no STTM maps this attribute yet")
    for ent, r in surv.items():
        for s_ in sorted(set(list((r or {}).get("source_priority") or []) + [x for a in ((r or {}).get("attributes") or {}).values() for x in (a or {}).get("priority", [])])):
            if s_ not in src_ids:
                warns.append(f"survivorship {ent}: source {s_} is not in registry/sources.yaml (yet)")
        if (r or {}).get("default") not in (None, "most_recent_update", "source_priority"):
            errs.append(f"survivorship {ent}: unknown default '{r.get('default')}'")
    return errs, warns


def main():
    errs, warns = check()
    for w in warns:
        print("warning ", w)
    for e in errs:
        print("ERROR   ", e)
    print("ONTOLOGY COHERENT" if not errs else f"ONTOLOGY CHECK FAILED ({len(errs)} errors)")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
