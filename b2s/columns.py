"""P2.3 scope proposal and column understanding (design §11), and the P3 logical (central) model draft.

The framework first tries to explain each column itself (name tokens, abbreviations, profile class, the conceptual
model). Only columns that stay `unclear` may go to a Glean column round (design §10.1).

Column status: known | inferred | unclear.   Scope: in_scope | out_of_scope | derive_instead | technical | review.
Decisions the worker made (via Genie, `set_scope`) are kept on every rerun.
"""
from __future__ import annotations

import re

from . import versions
from .layout import Layout
from .project import ontology
from .steps import ext_of, save_output

COMMON_WORDS = {
    "id", "no", "nr", "num", "number", "code", "cd", "key", "name", "nm", "desc", "description", "status", "stat",
    "type", "typ", "date", "dt", "ts", "time", "at", "by", "created", "updated", "modified", "from", "to", "qty",
    "quantity", "amount", "amt", "leg", "plan", "owner", "iso", "seq", "line", "item", "valid", "start", "end",
    "first", "last", "email", "phone", "contact", "user", "session", "login", "agent", "ip", "moved", "move", "loc",
    "location", "flag", "is", "count", "total", "price", "value", "unit", "currency", "weight", "version",
}
SENSITIVE = {"personal_data", "secret_or_token", "application_log", "payload_or_free_text"}


def _tokens(name: str, abbr: dict) -> list[str]:
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", name)
    return [abbr.get(t, t) for t in re.split(r"[^A-Za-z0-9]+", s.lower()) if t]


def silver_name(bronze_col: str, abbr: dict) -> str:
    """cntr_no -> container_no (abbreviations from the business ontology)."""
    return "_".join(_tokens(bronze_col, abbr))


def _snake(obj: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", obj).lower()


def _profile_class(p: dict) -> tuple[str | None, str | None]:
    """Column class and use from a baseline column profile (tolerant to where the engine stores them)."""
    for src in (p, p.get("classification") or {}, p.get("class") if isinstance(p.get("class"), dict) else {}):
        if src.get("column_class"):
            return src["column_class"], src.get("use")
    return (p.get("class") if isinstance(p.get("class"), str) else None), p.get("use")


def _baseline_tables(layout: Layout, app: str) -> dict:
    summ_v = versions.latest(layout.stem(app, "baseline/summary"), "json")
    if not summ_v:
        raise FileNotFoundError("no baseline summary: run P2 first")
    summary = versions.read(summ_v)
    out = {}
    for t in summary.get("tables") or []:
        name = t["table"]
        tv = versions.latest(layout.stem(app, f"baseline/tables/{name}"), "json")
        out[name] = {"summary": t, "detail": versions.read(tv) if tv else {}}
    return out


def build_columns(layout: Layout, app: str, *, reason: str = "rerun") -> tuple[versions.Version, versions.Version]:
    """P2.3 deterministic part: columns/columns.yaml and scope/scope.yaml (proposal)."""
    business = ontology(layout, "business")
    abbr = business.get("abbreviations") or {}
    vocab = COMMON_WORDS | set(abbr.values()) | {w.lower() for bo in (business.get("business_objects") or {})
                                                  for w in re.findall(r"[A-Z][a-z]+", bo)}
    conc_v = versions.latest(layout.stem(app, "models/conceptual"), "yaml")
    conceptual = versions.read(conc_v) if conc_v else {}
    table_obj = {t: o["name"] for o in conceptual.get("objects") or [] if o.get("status") != "unknown"
                 for t in o.get("tables") or []}
    prev_scope_v = versions.latest(layout.stem(app, "scope/scope"), "yaml")
    prev = versions.read(prev_scope_v) if prev_scope_v else {"tables": {}, "columns": {}}

    cols_out, scope_t, scope_c = {"tables": {}}, {}, {}
    for name, t in _baseline_tables(layout, app).items():
        s, d = t["summary"], t["detail"]
        profiles = d.get("columns") or []
        classes = {p["column"]: _profile_class(p) for p in profiles}
        n_log = sum(1 for c, _ in classes.values() if c == "application_log")
        # ---- table scope proposal
        if s.get("copy_of"):
            ts = ("out_of_scope", f"copy of {s['copy_of']}")
        elif s.get("empty") or s.get("row_count") == 0:
            ts = ("review", "empty table: is it loaded later?")
        elif profiles and n_log >= max(2, len(profiles) // 2):
            ts = ("out_of_scope", "application log table")
        elif name in table_obj:
            ts = ("in_scope", f"records {table_obj[name]} (conceptual model)")
        else:
            ts = ("review", "no business object in the conceptual model")
        pt = (prev.get("tables") or {}).get(name)
        scope_t[name] = pt if pt and pt.get("decided") else {"scope": ts[0], "reason": ts[1],
                                                             "business_object": table_obj.get(name)}
        # ---- columns
        tcols = {}
        for p in profiles:
            col = p["column"]
            cls, use = classes[col]
            toks = _tokens(col, abbr)
            meaning = " ".join(toks)
            status = "known" if toks and all(x in vocab for x in toks) else ("inferred" if any(x in vocab for x in toks) else "unclear")
            tcols[col] = {"class": cls, "use": use, "meaning": meaning, "silver_name": silver_name(col, abbr),
                          "status": status}
            if scope_t[name]["scope"] in ("in_scope", "review"):
                key = f"{name}.{col}"
                pc = (prev.get("columns") or {}).get(key)
                if pc and pc.get("decided"):
                    scope_c[key] = pc
                    continue
                cs = ("out_of_scope" if use in ("out_of_scope", "drop") else
                      "technical" if use == "technical_only" else
                      "review" if cls == "payload_or_free_text" else "in_scope")
                entry = {"scope": cs, "reason": (p.get("reasons") or cls or "")}
                if cls == "personal_data":
                    entry["privacy"] = {"class": "personal_data", "handling": None}
                scope_c[key] = entry
        cols_out["tables"][name] = {"business_object": table_obj.get(name), "columns": tcols}
    cv = save_output(layout, app, "columns/columns", cols_out, reason=reason)
    sv = save_output(layout, app, "scope/scope", {"tables": scope_t, "columns": scope_c}, reason=reason)
    return cv, sv


def unclear_columns(layout: Layout, app: str) -> set[str]:
    v = versions.latest(layout.stem(app, "columns/columns"), "yaml")
    if not v:
        return set()
    data = versions.read(v)
    return {f"{t}.{c}" for t, td in data["tables"].items() for c, cd in td["columns"].items() if cd["status"] == "unclear"}


def set_scope(layout: Layout, app: str, target: str, *, scope: str | None = None, handling: str | None = None,
              reason: str, via: str | None = None) -> versions.Version:
    """A worker decision on scope or privacy (given in the chat, saved by Genie). Kept on reruns."""
    v = versions.latest(layout.stem(app, "scope/scope"), "yaml")
    data = versions.read(v)
    bucket = "tables" if target in data["tables"] else "columns"
    if target not in data[bucket]:
        raise KeyError(f"{target} is not in scope.yaml")
    e = dict(data[bucket][target])
    if scope:
        if scope not in ("in_scope", "out_of_scope", "derive_instead", "technical"):
            raise ValueError("scope must be in_scope | out_of_scope | derive_instead | technical")
        e["scope"] = scope
    if handling:
        if handling not in ("keep_tagged", "mask", "hash"):
            raise ValueError("handling must be keep_tagged | mask | hash")
        e.setdefault("privacy", {"class": "personal_data"})["handling"] = handling
    e.update({"decided": True, "decision_reason": reason})
    data[bucket][target] = e
    return save_output(layout, app, "scope/scope", data, reason=f"decision: {target}", via=via)


# =========================================================================== P3 draft
KIND_TO_CLASS = {"party": "master", "thing": "master", "place": "master", "event": "event", "agreement": "agreement",
                 "measure": "measure", "classification": "reference"}


def draft_logical(layout: Layout, app: str) -> versions.Version:
    """Deterministic first draft of the logical silver model; Genie (@p3-logical) refines it as new versions."""
    business = ontology(layout, "business")
    abbr = business.get("abbreviations") or {}
    bos = business.get("business_objects") or {}
    conceptual = versions.read(versions.latest(layout.stem(app, "models/conceptual"), "yaml"))
    scope = versions.read(versions.latest(layout.stem(app, "scope/scope"), "yaml"))
    cols = versions.read(versions.latest(layout.stem(app, "columns/columns"), "yaml"))
    base = _baseline_tables(layout, app)
    tables, rels, tname = [], [], {}
    for o in conceptual.get("objects") or []:
        srcs = [t for t in o.get("tables") or [] if (scope["tables"].get(t) or {}).get("scope") == "in_scope"]
        if not srcs or o.get("status") == "unknown":
            continue
        src = srcs[0]
        name = f"slv_{_snake(o['name'])}"
        tname[o["name"]] = name
        key = (base.get(src, {}).get("summary") or {}).get("key") or []
        bk = [silver_name(c, abbr) for c in key]
        columns = [{"name": f"{_snake(o['name'])}_sk", "type": "string", "rule": "surrogate_key"}]
        for c, cd in cols["tables"][src]["columns"].items():
            sc = (scope["columns"].get(f"{src}.{c}") or {}).get("scope")
            if sc != "in_scope":
                continue
            entry = {"name": cd["silver_name"], "type": "string", "source_hint": {"table": src, "column": c}}
            if cd["status"] == "unclear":
                entry["note"] = "meaning unclear (P6)"
            columns.append(entry)
        status = {k: o[k] for k in ("status", "assumption", "question") if k in o}
        t = {"name": name, "business_object": o["name"],
             "data_class": KIND_TO_CLASS.get((bos.get(o["name"]) or {}).get("kind"), "event"),
             "grain": f"One row per {o['name']}" + (f" ({', '.join(bk)})." if bk else " (key unknown)."),
             "primary_key": [columns[0]["name"]], "business_key": [b for b in bk if b in {c["name"] for c in columns}],
             "columns": columns, "sources": srcs, **status}
        if not key:
            t.setdefault("note", "no key found in the baseline")
        tables.append(t)
    for r in conceptual.get("relationships") or []:
        if r["from"] in tname and r["to"] in tname and r.get("cardinality") in ("N:1", "1:1"):
            child = next(t for t in tables if t["name"] == tname[r["from"]])
            fk = f"{_snake(r['to'])}_sk"
            if fk not in {c["name"] for c in child["columns"]}:
                child["columns"].append({"name": fk, "type": "string", "rule": "lookup_fk"})
            rel = {"from": tname[r["from"]], "to": tname[r["to"]], "fk_column": fk, "cardinality": r["cardinality"],
                   "label": r.get("verb", "")}
            rel.update({k: r[k] for k in ("status", "assumption", "question") if k in r})
            rels.append(rel)
    return save_output(layout, app, "models/logical", {"tables": tables, "relationships": rels}, reason="draft (P7 tool)")
