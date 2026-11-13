"""P4.1: canonical STTM (sttm/sttm.vNNN.json), draft from the approved logical model, validator, mapping model.

Canonical STTM (the contract to team 2; client templates are exports through plug-in slots):
{
  "app", "logical_version": "v004",
  "tables": [{"target_table", "business_object", "data_class", "grain", "primary_key", "business_key", "sources",
              "columns": [{"target_column", "type", "rule", "source": {"table", "columns"} | null,
                           "key_rule"?, "fk"?: {"table", "lookup_on": [...]}, "privacy"?: {"class", "handling"},
                           "business_rule"?, "status", "assumption"?, "question"?, "evidence": []}]}]
}
rule: direct | normalised_key | surrogate_key | lookup_fk | derived | constant | technical
"""
from __future__ import annotations

from . import items, versions
from .layout import Layout
from .steps import ext_of, save_output

RULES = {"direct", "normalised_key", "surrogate_key", "lookup_fk", "derived", "constant", "technical"}


def _latest(layout, app, stem):
    v = versions.latest(layout.stem(app, stem), ext_of(stem))
    if not v:
        raise FileNotFoundError(f"{stem} does not exist")
    return v


def _question_for(layout: Layout, app: str, about: str, text: str) -> str:
    """Reuse an open question about the same thing; create one otherwise (no duplicates on reruns)."""
    for q in items.list_items(layout, app, "question"):
        if q.get("about_key") == about and q["status"] in ("open", "assumed"):
            return q["id"]
    return items.create(layout, app, "question", {"text": text, "about_key": about, "step": "P4.1"}, step="P4.1")["id"]


def draft(layout: Layout, app: str) -> versions.Version:
    """Draft the STTM from the latest APPROVED logical model version (CP3 is enforced by save_output)."""
    lv = _latest(layout, app, "models/logical")
    logical = versions.read(lv)
    scope = versions.read(_latest(layout, app, "scope/scope"))
    cols = versions.read(_latest(layout, app, "columns/columns"))
    by_name = {t["name"]: t for t in logical["tables"]}
    out_tables = []
    for t in logical["tables"]:
        srcs = t.get("sources") or []
        rels = {r["fk_column"]: r for r in logical.get("relationships") or [] if r["from"] == t["name"]}
        out_cols = []
        for c in t["columns"]:
            col = {"target_column": c["name"], "type": c.get("type", "string"), "evidence": []}
            hint = c.get("source_hint")
            if c["name"] in t["primary_key"] and c.get("rule") == "surrogate_key":
                col.update(rule="surrogate_key", source=None, derived_from=t.get("business_key") or [])
            elif c["name"] in rels:
                r = rels[c["name"]]
                parent = by_name[r["to"]]
                lookup = []
                for bk in parent.get("business_key") or []:
                    pc = next((x for x in parent["columns"] if x["name"] == bk), {})
                    pcol = (pc.get("source_hint") or {}).get("column")
                    if pcol and srcs and pcol in cols["tables"].get(srcs[0], {}).get("columns", {}):
                        lookup.append(f"{srcs[0]}.{pcol}")
                col.update(rule="lookup_fk", source={"table": srcs[0] if srcs else None,
                                                     "columns": [l.split(".")[-1] for l in lookup]},
                           fk={"table": r["to"], "lookup_on": lookup})
                for k in ("status", "assumption", "question"):
                    if k in r:
                        col[k] = r[k]
                if not lookup:
                    col.update(status="unknown", question=_question_for(
                        layout, app, f"{t['name']}.{c['name']}",
                        f"Which bronze column of {srcs[0] if srcs else '?'} identifies the {parent['business_object']} "
                        f"for {t['name']}.{c['name']}?"))
            elif hint:
                col.update(rule="normalised_key" if c["name"] in (t.get("business_key") or []) else "direct",
                           source={"table": hint["table"], "columns": [hint["column"]]})
                sc = scope["columns"].get(f"{hint['table']}.{hint['column']}") or {}
                if sc.get("privacy"):
                    col["privacy"] = sc["privacy"]
                cinfo = cols["tables"].get(hint["table"], {}).get("columns", {}).get(hint["column"], {})
                if cinfo.get("status") == "unclear":
                    col.update(status="unknown", question=_question_for(
                        layout, app, f"{hint['table']}.{hint['column']}",
                        f"What does {hint['table']}.{hint['column']} mean?"))
            else:
                col.update(rule="derived", source=None, status="unknown", question=_question_for(
                    layout, app, f"{t['name']}.{c['name']}", f"Where does {t['name']}.{c['name']} come from?"))
            for k in ("status", "assumption", "question"):
                if k in c and k not in col:
                    col[k] = c[k]
            col.setdefault("status", "known")
            out_cols.append(col)
        out_tables.append({k: t.get(k) for k in ("business_object", "data_class", "grain", "primary_key", "business_key")}
                          | {"target_table": t["name"], "sources": srcs, "columns": out_cols})
    sttm = {"app": app, "logical_version": lv.tag, "tables": out_tables}
    v = save_output(layout, app, "sttm/sttm", sttm, reason="draft (P8 tool)")
    save_output(layout, app, "models/mapping", mapping_model(sttm, logical), reason=f"from {v.label}")
    return v


def mapping_model(sttm: dict, logical: dict) -> dict:
    """The mapping model (design §9.5) derived from the STTM: bronze id columns -> silver keys."""
    links = []
    for t in sttm["tables"]:
        for c in t["columns"]:
            if c["rule"] in ("normalised_key", "lookup_fk") or c["target_column"] in (t.get("business_key") or []):
                src = c.get("source") or {}
                if not src.get("table") or not src.get("columns"):
                    continue
                link = {"business_object": t["business_object"], "bronze_table": src["table"],
                        "bronze_columns": list(src["columns"]), "silver_table": t["target_table"],
                        "silver_columns": [c["target_column"]] * len(src["columns"])}
                if c.get("key_rule"):
                    link["key_rule"] = c["key_rule"]
                link.update({k: c[k] for k in ("status", "assumption", "question") if k in c})
                links.append(link)
    return {"links": links}


def validate(layout: Layout, app: str, sttm: dict) -> list[str]:
    """Structural and policy checks. Empty list = valid."""
    errs = []
    lv = versions.get(layout.stem(app, "models/logical"), int(sttm.get("logical_version", "v000")[1:] or 0), "yaml") \
        if sttm.get("logical_version") else None
    if not lv:
        return [f"logical model version {sttm.get('logical_version')} not found"]
    logical = {t["name"]: t for t in versions.read(lv)["tables"]}
    sv = versions.latest(layout.stem(app, "scope/scope"), "yaml")
    scope = versions.read(sv) if sv else {"tables": {}, "columns": {}}
    for t in sttm.get("tables") or []:
        tn = t.get("target_table")
        if tn not in logical:
            errs.append(f"{tn}: not a table of logical {lv.label}")
            continue
        lcols = {c["name"] for c in logical[tn]["columns"]}
        seen = set()
        for c in t.get("columns") or []:
            w = f"{tn}.{c.get('target_column')}"
            seen.add(c.get("target_column"))
            if c.get("target_column") not in lcols:
                errs.append(f"{w}: not a column of logical {lv.label}")
            if c.get("rule") not in RULES:
                errs.append(f"{w}: rule must be one of {sorted(RULES)}")
            st = c.get("status", "known")
            if st == "assumed" and not str(c.get("assumption", "")).startswith("A-"):
                errs.append(f"{w}: assumed needs an assumption (A-nnnn)")
            if st == "unknown" and not str(c.get("question", "")).startswith("Q-"):
                errs.append(f"{w}: unknown needs a question (Q-nnnn)")
            if c.get("rule") in ("direct", "normalised_key") and st == "known" and not (c.get("source") or {}).get("columns"):
                errs.append(f"{w}: a mapped column needs a source")
            if c.get("rule") == "lookup_fk" and st == "known" and not (c.get("fk") or {}).get("lookup_on"):
                errs.append(f"{w}: a foreign key needs fk.lookup_on")
            for sc in (c.get("source") or {}).get("columns") or []:
                key = f"{c['source']['table']}.{sc}"
                s = scope["columns"].get(key) or {}
                if s.get("scope") in ("out_of_scope",) and not c.get("scope_override"):
                    errs.append(f"{w}: source {key} is out of scope (needs scope_override with a reason)")
                if s.get("privacy") and (c.get("privacy") or s["privacy"]).get("handling") not in ("keep_tagged", "mask", "hash"):
                    errs.append(f"{w}: source {key} is personal data — privacy handling keep_tagged | mask | hash needed")
                if (s.get("reason") or "").startswith("secret") or "secret_or_token" in str(s.get("reason")):
                    errs.append(f"{w}: secrets never go to silver")
        missing = lcols - seen
        if missing:
            errs.append(f"{tn}: logical columns not mapped: {', '.join(sorted(missing))}")
    return errs


def counts(sttm: dict) -> dict:
    out = {"known": 0, "assumed": 0, "unknown": 0}
    for t in sttm.get("tables") or []:
        for c in t.get("columns") or []:
            out[c.get("status", "known")] += 1
    return out
