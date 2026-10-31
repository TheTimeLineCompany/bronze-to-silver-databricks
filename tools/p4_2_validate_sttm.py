#!/usr/bin/env python3
"""P4.2 Deterministic checks for one STTM file (sources/<id>/04_mapping/sttm.yaml).

This is the "guarantee in code" for checkpoint CP4. Skill p4-2-sttm-validate runs it,
and the PR check runs it again. A prompt cannot skip it.

Besides structure, keys, naming, and the central model, it checks ONTOLOGY COHERENCE:
  - each target table names a business_object (ontology/business.yaml) and a data_class (ontology/data.yaml)
  - the load pattern is allowed for the data class; conformed classes match registry/entities.yaml
  - every FK follows a business relationship between the two business objects
  - business-logic columns cite a business rule id (BR-...)
  - cited evidence ids exist in 02_evidence/evidence_register.csv, and keys / business logic do not
    rest only on low- or unknown-confidence evidence

Usage:
    python tools/p4_2_validate_sttm.py sources/S07_container_moves/04_mapping/sttm.yaml
    python tools/p4_2_validate_sttm.py --all            # every sources/*/04_mapping/sttm.yaml
    python tools/p4_2_validate_sttm.py FILE --json      # machine-readable result

Exit code 0 = no errors (warnings allowed). Exit code 1 = errors found.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field

import yaml

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class Result:
    file: str
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def err(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {msg}")

    @property
    def ok(self):
        return not self.errors

    def as_dict(self):
        return {"file": self.file, "ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def load_context(root=ROOT):
    ctx = {
        "entities": {e["name"]: e for e in _load(os.path.join(root, "registry/entities.yaml"))["entities"]},
        "keys": _load(os.path.join(root, "registry/key_normalisation.yaml")),
        "questions": {q["id"]: q for q in (_load(os.path.join(root, "registry/open_questions.yaml")) or {}).get("questions", [])},
        "naming": _load(os.path.join(root, "standards/naming.yaml")),
        "business": _load(os.path.join(root, "registry/ontology/business.yaml")),
        "data": _load(os.path.join(root, "registry/ontology/data.yaml")),
    }
    with open(os.path.join(root, "schemas/sttm.schema.json"), encoding="utf-8") as f:
        ctx["schema"] = json.load(f)
    return ctx


def _load_register(path):
    if not os.path.exists(path):
        return None
    import csv
    with open(path, newline="", encoding="utf-8") as f:
        return {row["evidence_id"]: row for row in csv.DictReader(f)}


def _column_scope(sttm_path: str) -> dict:
    """{(schema.table, column lower): row} from discovery column_scope.csv, or {}."""
    import csv
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(sttm_path))), "02_evidence", "discovery", "column_scope.csv")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return {(".".join(r["table"].lower().split(".")[-2:]), r["column"].lower()): r for r in csv.DictReader(f)}


def _discovery_scope(sttm_path: str) -> dict:
    """{schema.table (lower): (scope, reason)} from the source's discovery tables.csv, or {} if discovery has not run."""
    import csv
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(sttm_path))), "02_evidence", "discovery", "tables.csv")
    if not os.path.exists(p):
        return {}
    out = {}
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("scope"):
                out[".".join(r["table"].lower().split(".")[-2:])] = (r["scope"], r.get("scope_reason", ""))
    return out


def directed_pairs(relationships: dict) -> set:
    """(child, parent) pairs a foreign key may follow: the child holds the FK (N side).
    N:1 subject->object; 1:N object->subject; 1:1 both ways; N:M none (needs a bridge table)."""
    out = set()
    for v in relationships.values():
        card = str(v.get("cardinality", "")).upper().replace(" ", "")
        s, o = v["subject"], v["object"]
        if card in ("N:1", "M:1"):
            out.add((s, o))
        elif card in ("1:N", "1:M"):
            out.add((o, s))
        elif card == "1:1":
            out |= {(s, o), (o, s)}
    return out


def strong_evidence(e: dict) -> bool:
    """Evidence that may support a key or business-logic column (registry/ontology/information.yaml confidence rules)."""
    if e.get("status") in ("contradicted", "superseded"):
        return False
    if e.get("status") in ("confirmed_by_bronze", "corroborated"):
        return True
    if e.get("origin") in ("bronze_profile", "client_answer"):
        return True
    return e.get("confidence") == "high"          # medium needs corroboration; low/unknown never alone


def _profiling_exists(c: dict, sttm_path: str) -> bool:
    p = (c.get("provenance") or {}).get("profiling")
    if not p:
        return False
    sdir = os.path.dirname(os.path.dirname(os.path.abspath(sttm_path)))
    return os.path.exists(os.path.join(sdir, str(p).split("#")[0]))


def validate(path, ctx=None, root=ROOT) -> Result:
    ctx = ctx or load_context(root)
    r = Result(file=os.path.relpath(path, root))
    try:
        doc = _load(path)
    except Exception as e:  # noqa: BLE001
        r.err("file", f"cannot parse YAML: {e}")
        return r

    # 1. Structure (JSON Schema)
    if jsonschema is not None:
        v = jsonschema.Draft202012Validator(ctx["schema"])
        for e in sorted(v.iter_errors(doc), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in e.path) or "root"
            r.err(f"schema {loc}", e.message)
        if r.errors:
            return r  # semantic checks need a valid structure

    source_id = doc["source_id"]
    folder = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(path))))
    if folder != source_id:
        r.err("source_id", f"'{source_id}' does not match folder name '{folder}'")

    naming = ctx["naming"]
    t_pat = re.compile(naming["table_pattern"])
    c_pat = re.compile(naming["column_pattern"])
    allowed_types = {t.upper() for t in naming.get("allowed_types", [])}
    key_rules = ctx["keys"].get("rules", {})
    entities = ctx["entities"]
    questions = ctx["questions"]
    seen_tables = set()
    bus = ctx["business"]
    bobjs = bus.get("business_objects", {})
    brules = bus.get("business_rules", {})
    rel_pairs = directed_pairs(bus.get("relationships", {}))
    dclasses = ctx["data"].get("data_classes", {})
    reg = _load_register(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(path))), "02_evidence", "evidence_register.csv"))

    for ti, t in enumerate(doc["tables"]):
        tw = f"tables[{ti}] {t['target_table']}"
        if t["target_table"] in seen_tables:
            r.err(tw, "duplicate target_table")
        seen_tables.add(t["target_table"])
        if not t_pat.match(t["target_table"]):
            r.err(tw, f"table name breaks naming rule {naming['table_pattern']}")

        # Ontology coherence (business object + data class)
        bo = t["business_object"]
        dc = t["data_class"]
        if bo not in bobjs:
            r.err(tw, f"business_object '{bo}' is not in registry/ontology/business.yaml")
        if dc not in dclasses:
            r.err(tw, f"data_class '{dc}' is not in registry/ontology/data.yaml")
        else:
            spec = dclasses[dc]
            if t["load_pattern"] not in spec.get("allowed_load_patterns", []):
                r.err(tw, f"load_pattern '{t['load_pattern']}' is not allowed for data_class '{dc}' {spec.get('allowed_load_patterns')}")
            if bo in bobjs and bobjs[bo].get("kind") not in spec.get("business_kinds", []):
                r.warn(tw, f"business object kind '{bobjs[bo].get('kind')}' is unusual for data_class '{dc}'")
            if spec.get("conformed") and t["target_kind"] != "master":
                r.err(tw, f"data_class '{dc}' is conformed: use target_kind 'master' with a conformed_entity")
            if not spec.get("conformed") and t["target_kind"] == "master":
                r.err(tw, f"target_kind 'master' needs a conformed data_class (master or reference), not '{dc}'")
        ce0 = t.get("conformed_entity")
        if ce0 and ce0 in entities and entities[ce0].get("business_object") and entities[ce0]["business_object"] != bo:
            r.err(tw, f"business_object must be '{entities[ce0]['business_object']}' (registry entity {ce0})")

        cols = {c["target"]: c for c in t["columns"]}
        if len(cols) != len(t["columns"]):
            r.err(tw, "duplicate target column names")

        # Keys must exist as columns
        for k in t["primary_key"]:
            if k not in cols:
                r.err(tw, f"primary_key column '{k}' is not in columns")
            elif cols[k]["nullable"]:
                r.err(tw, f"primary_key column '{k}' must be nullable: false")
        for k in t["business_key"]:
            if k not in cols:
                r.err(tw, f"business_key column '{k}' is not in columns")
        # Key roles must agree with the key lists (a PK column cannot be key_role 'none', and so on)
        pk_set, bk_set = set(t["primary_key"]), set(t["business_key"])
        for name, c in cols.items():
            role = c.get("key_role")
            if name in pk_set and role not in ("PK", "PK_FK"):
                r.err(f"{tw}.{name}", f"column is in primary_key but key_role is '{role}' (use PK or PK_FK)")
            if role in ("PK", "PK_FK") and name not in pk_set:
                r.err(f"{tw}.{name}", f"key_role '{role}' but the column is not in primary_key")
            if name in bk_set and name not in pk_set and role not in ("BK", "FK"):
                r.err(f"{tw}.{name}", f"column is in business_key but key_role is '{role}' (use BK, or FK for a key part that is a foreign key)")
            if role == "BK" and name not in bk_set:
                r.err(f"{tw}.{name}", "key_role 'BK' but the column is not in business_key")
        sk0 = t.get("surrogate_key")
        if sk0 and sk0.get("column") in cols and sk0["column"] not in pk_set:
            r.warn(tw, f"surrogate key '{sk0['column']}' is not the primary key (data.yaml: SK is the primary key in silver)")
        sk = t.get("surrogate_key")
        if sk:
            if sk["column"] not in cols:
                r.err(tw, f"surrogate_key column '{sk['column']}' is not in columns")
            if not sk["column"].endswith(naming.get("surrogate_key_suffix", "_sk")):
                r.err(tw, f"surrogate key '{sk['column']}' must end with {naming.get('surrogate_key_suffix')}")
            for c in sk["of"]:
                if c not in cols:
                    r.err(tw, f"surrogate_key.of column '{c}' is not in columns")

        # History rule consistency
        if t["load_pattern"] == "scd2" or t["scd_type"] == 2:
            if not (t["load_pattern"] == "scd2" and t["scd_type"] == 2):
                r.err(tw, "load_pattern 'scd2' and scd_type 2 must be used together")
            for c in naming.get("scd2_columns", []):
                if c not in cols:
                    r.err(tw, f"scd_type 2 needs column '{c}'")

        # Conformed entity
        ce = t.get("conformed_entity")
        if t["target_kind"] == "master":
            if not ce:
                r.err(tw, "master tables must name a conformed_entity from registry/entities.yaml")
            elif ce not in entities:
                r.err(tw, f"conformed_entity '{ce}' is not in registry/entities.yaml")
            else:
                ent = entities[ce]
                if ent["target_table"] != t["target_table"]:
                    r.err(tw, f"master target_table must be '{ent['target_table']}' (registry)")
                if sorted(ent["business_key"]) != sorted(t["business_key"]):
                    r.err(tw, f"business_key must match registry {ent['business_key']}")
                if ent.get("scd_type") is not None and ent["scd_type"] != t["scd_type"]:
                    r.err(tw, f"scd_type must match registry ({ent['scd_type']})")

        # Scope: bronze tables that discovery marked out_of_scope (logs, audit, sessions, config, copies) or
        # derive_instead (aggregates) cannot feed silver without an explicit, reviewed scope_override
        disc = _discovery_scope(path)
        for si, src in enumerate(t.get("sources") or []):
            sc = disc.get(".".join(str(src["table"]).lower().split(".")[-2:]))
            if sc is None:
                if disc:
                    r.warn(f"{tw} sources[{si}]", f"{src['table']} is not in 02_evidence/discovery/tables.csv: run discovery so its scope is known")
                continue
            if sc[0] in ("out_of_scope", "derive_instead") and not (src.get("scope_override") or {}).get("reason"):
                r.err(f"{tw} sources[{si}]", f"{src['table']} is '{sc[0]}' in discovery ({sc[1]}); it cannot feed silver. "
                                              "Remove it, or add scope_override: {reason: ...} for review")
            elif sc[0] == "review":
                r.warn(f"{tw} sources[{si}]", f"{src['table']}: discovery scope not decided yet (answer its card)")

        # Column scope from discovery (column_scope.csv): out-of-scope columns (application logs, secrets, empty) need a
        # scope_override; personal data needs a privacy declaration (handling: keep_tagged | mask | hash)
        cscope = _column_scope(path)
        if cscope:
            alias_tab = {s_["alias"]: ".".join(str(s_["table"]).lower().split(".")[-2:]) for s_ in t.get("sources") or []}
            for c in t["columns"]:
                srcs = set()
                for al, col in re.findall(r"\b([A-Za-z]\w*)\.([A-Za-z_]\w*)", str(c.get("source") or "") + " " + str(c.get("transform") or "")):
                    if al in alias_tab:
                        srcs.add((alias_tab[al], col.lower()))
                for (tb, col) in sorted(srcs):
                    sc = cscope.get((tb, col))
                    if not sc:
                        continue
                    cw2 = f"{tw}.{c['target']}"
                    if sc["scope"] == "out_of_scope" and not (c.get("scope_override") or {}).get("reason"):
                        r.err(cw2, f"uses {tb}.{col}, which discovery marked out of scope ({sc['column_class']}: {sc['reason'][:80]}); "
                                   "remove it, or add scope_override: {reason: ...}")
                    if sc["column_class"] == "secret_or_token":
                        r.err(cw2, f"uses {tb}.{col}, which looks like a password, token, or hash: never map secrets to silver")
                    if sc["column_class"] == "personal_data" or sc["scope"] == "in_scope_masked":
                        pv = c.get("privacy") or {}
                        if not pv.get("handling"):
                            r.err(cw2, f"uses personal data {tb}.{col}: add privacy: {{class: personal, handling: keep_tagged | mask | hash}}")
                        elif sc["scope"] == "in_scope_masked" and pv["handling"] == "keep_tagged":
                            r.err(cw2, f"{tb}.{col} was decided 'mask' at CP2; privacy.handling must be mask or hash")
                        elif pv["handling"] == "hash" and "sha2" not in str(c.get("transform") or "").lower():
                            r.err(cw2, "privacy.handling 'hash' needs a sha2(...) transform")
                    if sc["scope"] == "review":
                        r.warn(cw2, f"uses {tb}.{col}: discovery column scope not decided yet ({sc['column_class']})")

        # Joins: aliases must exist
        aliases = {s["alias"] for s in t["sources"]}
        for ji, j in enumerate(t.get("joins") or []):
            for side in ("left", "right"):
                if j[side] not in aliases:
                    r.err(f"{tw} joins[{ji}]", f"{side} alias '{j[side]}' is not in sources")
            if j["cardinality"] == "N:M":
                r.warn(f"{tw} joins[{ji}]", "N:M join can multiply rows; confirm the grain is still correct")

        # Columns
        for c in t["columns"]:
            cw = f"{tw}.{c['target']}"
            if not c_pat.match(c["target"]):
                r.err(cw, f"column name breaks naming rule {naming['column_pattern']}")
            base_type = c["type"].split("(")[0].upper()
            if allowed_types and base_type not in allowed_types:
                r.err(cw, f"type '{c['type']}' is not in standards allowed_types")
            if c["rule"] in ("direct", "normalised_key", "derived", "lookup") and not c.get("source"):
                r.err(cw, f"rule '{c['rule']}' needs a source column or expression")
            if c["rule"] in ("derived", "lookup") and not c.get("transform"):
                r.err(cw, f"rule '{c['rule']}' needs a transform")
            if c["rule"] == "normalised_key":
                kr = c.get("key_rule")
                if not kr:
                    r.err(cw, "normalised_key needs key_rule")
                elif kr not in key_rules:
                    r.err(cw, f"key_rule '{kr}' is not in registry/key_normalisation.yaml")
            if c["key_role"] in ("FK", "PK_FK"):
                fk = c.get("fk")
                tables_by = {x["target_table"]: x for x in doc["tables"]}
                if not fk:
                    r.err(cw, "FK column needs an fk block (entity or table, column, cardinality)")
                elif bool(fk.get("entity")) == bool(fk.get("table")):
                    r.err(cw, "fk needs exactly one of 'entity' (shared master) or 'table' (a target_table in this STTM)")
                elif fk.get("entity") and fk["entity"] not in entities:
                    r.err(cw, f"fk.entity '{fk['entity']}' is not in registry/entities.yaml")
                elif fk.get("table") and fk["table"] not in tables_by:
                    r.err(cw, f"fk.table '{fk['table']}' is not a target_table in this STTM")
                else:
                    if fk.get("entity"):
                        e_ = entities[fk["entity"]]
                        want, parent_bo, parent_bk = e_["surrogate_key"], e_.get("business_object", fk["entity"]), list(e_["business_key"])
                        parent_name = f"entity {fk['entity']}"
                    else:
                        pt = tables_by[fk["table"]]
                        want = (pt.get("surrogate_key") or {}).get("column")
                        parent_bo, parent_bk = pt.get("business_object"), list(pt.get("business_key") or [])
                        parent_name = f"table {fk['table']}"
                        if fk.get("orphan_policy") == "unknown_member":
                            r.err(cw, "orphan_policy 'unknown_member' is only for shared masters (they have an unknown row); use reject or allow_null")
                    if fk["column"] != want:
                        r.err(cw, f"fk.column must be the surrogate key of {parent_name}: '{want}'")
                    child_bo = bo
                    if child_bo != parent_bo and (child_bo, parent_bo) not in rel_pairs:
                        if (parent_bo, child_bo) in rel_pairs:
                            r.err(cw, f"FK points the wrong way: in business.yaml '{parent_bo}' is the child (N side) of '{child_bo}'; "
                                      f"put the FK on the {parent_bo} table, or fix the relationship cardinality (CP3)")
                        else:
                            r.err(cw, f"no N:1 or 1:1 business relationship from '{child_bo}' to '{parent_bo}' in ontology/business.yaml; "
                                      "add one (CP3) or fix the FK (N:M needs a bridge table)")
                    lk = fk.get("lookup_on")
                    if lk is not None and len(lk) != len(parent_bk):
                        r.err(cw, f"fk.lookup_on has {len(lk)} item(s) but {parent_name} has business key {parent_bk} ({len(parent_bk)} column(s)); "
                                  "give one expression per key column, in order")
                    elif lk is None and len(parent_bk) > 1:
                        r.err(cw, f"{parent_name} has a composite business key {parent_bk}: give fk.lookup_on (one expression per key column)")
                    elif lk is None:
                        r.warn(cw, "no fk.lookup_on: the lookup stays a TODO cell; with lookup_on the code is generated")
                    for it in lk or []:
                        kr = it.get("key_rule") if isinstance(it, dict) else None
                        if kr and kr not in key_rules:
                            r.err(cw, f"fk.lookup_on key_rule '{kr}' is not in registry/key_normalisation.yaml")
                    if not fk.get("orphan_policy"):
                        r.warn(cw, "no orphan_policy; default will be 'reject'")
            elif c.get("fk"):
                r.err(cw, "fk block given but key_role is not FK")
            # Business logic must cite a catalogued business rule
            if c.get("business_logic"):
                br = c.get("business_rule")
                if not br:
                    r.err(cw, "business_logic column needs business_rule (BR-...) from ontology/business.yaml")
                elif br not in brules:
                    r.err(cw, f"business_rule '{br}' is not in ontology/business.yaml")
            # Evidence ids and confidence rules
            ev = ((c.get("provenance") or {}).get("evidence")) or []
            for e in ev:
                if reg is None:
                    r.err(cw, f"cites {e} but 02_evidence/evidence_register.csv is missing")
                    break
                if e not in reg:
                    r.err(cw, f"evidence {e} is not in 02_evidence/evidence_register.csv")
            critical = c["key_role"] in ("PK", "BK", "FK", "PK_FK") or c.get("business_logic") \
                or c["target"] in set(t["primary_key"]) | set(t["business_key"])
            if critical and c["rule"] != "technical" and reg is not None:
                strong = [e for e in ev if e in reg and strong_evidence(reg[e])]
                weak = [e for e in ev if e in reg and reg[e]["status"] in ("contradicted", "superseded")]
                if weak:
                    r.warn(cw, f"cites contradicted/superseded evidence {weak}; it does not count as support")
                if not strong and not _profiling_exists(c, path):
                    r.err(cw, "key or business-logic column has no valid support: needs evidence that is confirmed_by_bronze, "
                              "corroborated, high-confidence and unverified, or a client answer (never contradicted or superseded), "
                              "or an existing profiling file; confirm in bronze (P2.2) or ask the client")
            # Provenance: every non-technical column must cite evidence
            if c["rule"] != "technical":
                p = c.get("provenance") or {}
                if not (p.get("doc") or p.get("profiling") or p.get("evidence")):
                    r.err(cw, "provenance needs evidence ids, a doc, or a profiling file")
            # Confidence and escalation
            q = c.get("open_question")
            if c["confidence"] == "low" and not q:
                r.err(cw, "low confidence needs an open_question id")
            if q:
                if q not in questions:
                    r.err(cw, f"open_question {q} is not in registry/open_questions.yaml")
                else:
                    qq = questions[q]
                    if qq.get("source_id") != source_id:
                        r.warn(cw, f"{q} belongs to {qq.get('source_id')}")
                    if qq.get("blocking") and qq.get("status") == "open":
                        msg = f"blocking question {q} is still open"
                        if doc["status"] == "approved":
                            r.err(cw, msg + " (cannot approve)")
                        else:
                            r.warn(cw, msg)

        # Audit columns are added by codegen; warn if someone mapped them by hand differently
        for a in naming.get("audit_columns", []):
            if a in cols and cols[a]["rule"] != "technical":
                r.warn(tw, f"audit column '{a}' should use rule 'technical'")

    # Any open blocking question for this source blocks approval, even if no column cites it
    if doc["status"] == "approved":
        for q in questions.values():
            if q.get("source_id") == source_id and q.get("blocking") and q.get("status") == "open":
                r.err("status", f"cannot be 'approved' while blocking question {q['id']} is open")
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--all", action="store_true", help="validate every sources/*/04_mapping/sttm.yaml")
    ap.add_argument("--json", action="store_true", help="print JSON results")
    a = ap.parse_args(argv)
    files = list(a.files)
    if a.all:
        files += sorted(glob.glob(os.path.join(ROOT, "sources", "*", "04_mapping", "sttm.yaml")))
    if not files:
        ap.error("give a file or --all")
    ctx = load_context()
    results = [validate(f, ctx) for f in files]
    if a.json:
        print(json.dumps([x.as_dict() for x in results], indent=2))
    else:
        for x in results:
            print(f"{'PASS' if x.ok else 'FAIL'}  {x.file}  ({len(x.errors)} errors, {len(x.warnings)} warnings)")
            for e in x.errors:
                print(f"  ERROR    {e}")
            for w in x.warnings:
                print(f"  warning  {w}")
    return 0 if all(x.ok for x in results) else 1


if __name__ == "__main__":
    sys.exit(main())
