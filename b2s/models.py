"""The five models (design §9): YAML formats, validators, and Mermaid writers + a parser for the framework's subset.

Each model YAML is the source of truth. Mermaid (.mmd) and the viewer (.html) are generated from it and must match
(check: b2s.viewer.check_views). Every element has status known | assumed | unknown:
  assumed -> names its assumption (A-xxxx);  unknown -> names its question (Q-xxxx).
"""
from __future__ import annotations

import re

STATUSES = {"known", "assumed", "unknown"}
MODELS = ("dependencies", "process", "conceptual", "logical", "mapping")
CARDINALITIES = {"1:1", "1:N", "N:1", "N:M"}
# Mermaid erDiagram ends: left end describes the LEFT entity seen from the right, right end the RIGHT entity.
_ER = {"1:1": "||--||", "1:N": "||--o{", "N:1": "}o--||", "N:M": "}o--o{"}
_ER_REV = {v: k for k, v in _ER.items()}


class ModelError(ValueError):
    pass


# =========================================================================== validation
def _check_status(errs: list, where: str, el: dict) -> None:
    st = el.get("status", "known")
    if st not in STATUSES:
        errs.append(f"{where}: status {st!r} not in {sorted(STATUSES)}")
    if st == "assumed" and not re.match(r"^A-\d{4}$", str(el.get("assumption", ""))):
        errs.append(f"{where}: status assumed needs 'assumption: A-nnnn'")
    if st == "unknown" and not re.match(r"^Q-\d{4}$", str(el.get("question", ""))):
        errs.append(f"{where}: status unknown needs 'question: Q-nnnn'")


def _ident(errs, where, s):
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", str(s)):
        errs.append(f"{where}: id {s!r} must be a simple identifier (letters, digits, _)")


def validate(kind: str, m: dict, ontology_business: dict | None = None) -> list[str]:
    """Errors (empty list = valid). Ontology checks run when the business ontology is given."""
    if kind not in MODELS:
        return [f"unknown model kind {kind}"]
    errs: list[str] = []
    if not isinstance(m, dict):
        return ["model must be a mapping"]
    f = globals()[f"_validate_{kind}"]
    f(errs, m, ontology_business or {})
    return errs


def _validate_dependencies(errs, m, onto):
    if not m.get("app"):
        errs.append("app is required")
    seen = set()
    for i, s in enumerate(m.get("systems") or []):
        w = f"systems[{i}]"
        _ident(errs, w, s.get("id"))
        if s.get("id") in seen:
            errs.append(f"{w}: duplicate id {s.get('id')}")
        seen.add(s.get("id"))
        if s.get("relation") not in ("upstream", "downstream", "both"):
            errs.append(f"{w}: relation must be upstream | downstream | both")
        _check_status(errs, w, s)


def _validate_process(errs, m, onto):
    bps = set((onto.get("processes") or {}).keys())
    ids = set()
    for i, p in enumerate(m.get("processes") or []):
        w = f"processes[{i}]"
        _ident(errs, w, p.get("id"))
        if bps and p.get("business_process") and p["business_process"] not in bps:
            errs.append(f"{w}: business_process {p['business_process']} not in the ontology (change request needed)")
        for j, st in enumerate(p.get("steps") or []):
            ws = f"{w}.steps[{j}]"
            _ident(errs, ws, st.get("id"))
            if st.get("id") in ids:
                errs.append(f"{ws}: duplicate step id {st.get('id')}")
            ids.add(st.get("id"))
            _check_status(errs, ws, st)
        for j, fl in enumerate(p.get("flows") or []):
            wf = f"{w}.flows[{j}]"
            for end in ("from", "to"):
                if fl.get(end) not in ids:
                    errs.append(f"{wf}: {end} {fl.get(end)!r} is not a step of this model")
            _check_status(errs, wf, fl)


def _validate_conceptual(errs, m, onto):
    bos = set((onto.get("business_objects") or {}).keys())
    names = set()
    for i, o in enumerate(m.get("objects") or []):
        w = f"objects[{i}]"
        _ident(errs, w, o.get("name"))
        names.add(o.get("name"))
        _check_status(errs, w, o)
        if bos and o.get("name") not in bos and not o.get("change_request"):
            errs.append(f"{w}: {o.get('name')} is not in the business ontology; add 'change_request: CR-nnnn' (never invent)")
    for i, r in enumerate(m.get("relationships") or []):
        w = f"relationships[{i}]"
        for end in ("from", "to"):
            if r.get(end) not in names:
                errs.append(f"{w}: {end} {r.get(end)!r} is not an object of this model")
        if r.get("cardinality") not in CARDINALITIES:
            errs.append(f"{w}: cardinality must be one of {sorted(CARDINALITIES)}")
        _check_status(errs, w, r)


def _validate_logical(errs, m, onto):
    tables = {}
    for i, t in enumerate(m.get("tables") or []):
        w = f"tables[{i}]"
        _ident(errs, w, t.get("name"))
        if t.get("name") in tables:
            errs.append(f"{w}: duplicate table {t.get('name')}")
        tables[t.get("name")] = t
        for k in ("business_object", "data_class", "grain"):
            if not t.get(k):
                errs.append(f"{w}: {k} is required")
        _check_status(errs, w, t)
        cols = {c.get("name") for c in t.get("columns") or []}
        pk = t.get("primary_key") or []
        if not pk:
            errs.append(f"{w}: primary_key is required")
        for c in pk + (t.get("business_key") or []):
            if c not in cols:
                errs.append(f"{w}: key column {c} is not a column of the table")
        for j, c in enumerate(t.get("columns") or []):
            _ident(errs, f"{w}.columns[{j}]", c.get("name"))
            _check_status(errs, f"{w}.columns[{j}]", c)
    for i, r in enumerate(m.get("relationships") or []):
        w = f"relationships[{i}]"
        for end in ("from", "to"):
            if r.get(end) not in tables:
                errs.append(f"{w}: {end} {r.get(end)!r} is not a table of this model")
        if r.get("cardinality") not in CARDINALITIES - {"N:M"}:
            errs.append(f"{w}: cardinality must be 1:1, 1:N or N:1 (resolve N:M with a bridge table)")
        fc = r.get("fk_column")
        if r.get("from") in tables and fc not in {c.get("name") for c in tables[r["from"]].get("columns") or []}:
            errs.append(f"{w}: fk_column {fc!r} is not a column of {r.get('from')}")
        _check_status(errs, w, r)


def _validate_mapping(errs, m, onto):
    for i, l in enumerate(m.get("links") or []):
        w = f"links[{i}]"
        for k in ("bronze_table", "bronze_columns", "silver_table", "silver_columns"):
            if not l.get(k):
                errs.append(f"{w}: {k} is required")
        if len(l.get("bronze_columns") or []) != len(l.get("silver_columns") or []):
            errs.append(f"{w}: bronze_columns and silver_columns must have the same length")
        _check_status(errs, w, l)


# =========================================================================== Mermaid writers
_CLASSDEFS = [
    "  classDef known fill:#ffffff,stroke:#1f2937,color:#111827;",
    "  classDef assumed fill:#fff7e6,stroke:#92400e,stroke-dasharray:6 3,color:#111827;",
    "  classDef unknown fill:#fdecec,stroke:#b91c1c,stroke-dasharray:4 3,color:#111827;",
]


def _q(s: str) -> str:
    return '"' + str(s).replace('"', "'") + '"'


def _status_suffix(el: dict) -> str:
    st = el.get("status", "known")
    if st == "assumed":
        return f" ({el['assumption']})"
    if st == "unknown":
        return f" ({el['question']})"
    return ""


def _status_prefix(el: dict) -> str:
    return "? " if el.get("status") == "unknown" else ""


def _edge(el: dict) -> str:
    return "-->" if el.get("status", "known") == "known" else "-.->"


def _undirected(el: dict) -> str:
    return "---" if el.get("status", "known") == "known" else "-.-"


def to_mermaid(kind: str, m: dict) -> str:
    return globals()[f"_mmd_{kind}"](m) + "\n"


def _mmd_dependencies(m):
    app = m["app"]
    lines = ["flowchart LR", f"  APP(({_q(app)}))"]
    for s in m.get("systems") or []:
        lines.append(f"  {s['id']}[{_q(_status_prefix(s) + s.get('name', s['id']))}]")
    for s in m.get("systems") or []:
        label = _q(_status_prefix(s) + ", ".join(s.get("gives") or []) + _status_suffix(s))
        if s["relation"] in ("upstream", "both"):
            lines.append(f"  {s['id']} {_edge(s)}|{label}| APP")
        if s["relation"] in ("downstream", "both"):
            lines.append(f"  APP {_edge(s)}|{label}| {s['id']}")
    lines += _CLASSDEFS
    lines += [f"  class {s['id']} {s.get('status', 'known')};" for s in m.get("systems") or []]
    return "\n".join(lines)


def _mmd_process(m):
    lines = ["flowchart TD"]
    for p in m.get("processes") or []:
        lines.append(f"  subgraph {p['id']}[{_q(p.get('name', p['id']))}]")
        for st in p.get("steps") or []:
            lines.append(f"    {st['id']}[{_q(_status_prefix(st) + st.get('name', st['id']) + _status_suffix(st))}]")
        lines.append("  end")
    for p in m.get("processes") or []:
        for fl in p.get("flows") or []:
            lab = _status_prefix(fl) + (fl.get("label") or "") + _status_suffix(fl)
            lines.append(f"  {fl['from']} {_edge(fl)}" + (f"|{_q(lab.strip())}|" if lab.strip() else "") + f" {fl['to']}")
    lines += _CLASSDEFS
    for p in m.get("processes") or []:
        lines += [f"  class {st['id']} {st.get('status', 'known')};" for st in p.get("steps") or []]
    return "\n".join(lines)


def _mmd_conceptual(m):
    lines = ["flowchart LR"]
    for o in m.get("objects") or []:
        lines.append(f"  {o['name']}[{_q(_status_prefix(o) + o['name'] + _status_suffix(o))}]")
    for r in m.get("relationships") or []:
        lab = _status_prefix(r) + f"{r.get('verb', '')} {r['cardinality']}".strip() + _status_suffix(r)
        lines.append(f"  {r['from']} {_edge(r)}|{_q(lab)}| {r['to']}")
    lines += _CLASSDEFS
    lines += [f"  class {o['name']} {o.get('status', 'known')};" for o in m.get("objects") or []]
    return "\n".join(lines)


def _mmd_logical(m):
    lines = ["erDiagram"]
    for r in m.get("relationships") or []:
        # from = child table holding the FK; cardinality is read from -> to (N:1 = many children, one parent)
        sym = _ER[r["cardinality"]]
        if r.get("status", "known") != "known":
            sym = sym.replace("--", "..")
        lab = _status_prefix(r) + (r.get("label") or r["fk_column"]) + _status_suffix(r)
        lines.append(f"  {r['from']} {sym} {r['to']} : {_q(lab)}")
    for t in m.get("tables") or []:
        # a table that is not known carries its status in the entity alias label (Mermaid: name["label"] {)
        alias = "" if t.get("status", "known") == "known" else             "[" + _q(_status_prefix(t) + t["name"] + _status_suffix(t)) + "]"
        lines.append(f"  {t['name']}{alias} {{")
        pk, bk = set(t.get("primary_key") or []), set(t.get("business_key") or [])
        fks = {r["fk_column"] for r in m.get("relationships") or [] if r["from"] == t["name"]}
        for c in t.get("columns") or []:
            keys = [k for k, s in (("PK", pk), ("FK", fks)) if c["name"] in s]
            comment = []
            if c["name"] in bk:
                comment.append("BK")
            if c.get("status", "known") != "known":
                comment.append((_status_prefix(c) + _status_suffix(c).strip()).strip())
            ks = (" " + ",".join(keys)) if keys else ""
            cm = (" " + _q(" ".join(x for x in comment if x))) if comment else ""
            lines.append(f"    {c.get('type', 'string')} {c['name']}{ks}{cm}")
        lines.append("  }")
    return "\n".join(lines)


def _mmd_mapping(m):
    lines = ["flowchart LR"]
    objs = sorted({l["business_object"] for l in m.get("links") or [] if l.get("business_object")})
    silver = {}
    bronze = {}
    for l in m.get("links") or []:
        silver.setdefault(l["silver_table"], set()).update(l["silver_columns"])
        bronze.setdefault(l["bronze_table"], set()).update(l["bronze_columns"])
    lines.append("  subgraph BO[\"Business objects\"]")
    lines += [f"    bo_{o}[{_q(o)}]" for o in objs]
    lines.append("  end")
    lines.append("  subgraph SLV[\"Silver\"]")
    lines += [f"    s_{_nid(t)}[{_q(t + '<br/>' + '<br/>'.join(sorted(cs)))}]" for t, cs in sorted(silver.items())]
    lines.append("  end")
    lines.append("  subgraph BRZ[\"Bronze\"]")
    lines += [f"    b_{_nid(t)}[{_q(t + '<br/>' + '<br/>'.join(sorted(cs)))}]" for t, cs in sorted(bronze.items())]
    lines.append("  end")
    done = set()
    for l in m.get("links") or []:
        if l.get("business_object") and (l["business_object"], l["silver_table"]) not in done:
            done.add((l["business_object"], l["silver_table"]))
            lines.append(f"  bo_{l['business_object']} --- s_{_nid(l['silver_table'])}")
    for l in m.get("links") or []:
        pairs = ", ".join(f"{b} → {s}" for b, s in zip(l["bronze_columns"], l["silver_columns"]))
        lab = _status_prefix(l) + pairs + (f" ({l['key_rule']})" if l.get("key_rule") else "") + _status_suffix(l)
        lines.append(f"  b_{_nid(l['bronze_table'])} {_edge(l)}|{_q(lab)}| s_{_nid(l['silver_table'])}")
    return "\n".join(lines)


def _nid(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


# =========================================================================== Mermaid parser (framework subset)
_NODE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\(|\[)"([^"]*)"(?:\)\)|\])\s*$')
_FEDGE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s+(-->|-\.->|---|-\.-)\s*(?:\|"([^"]*)"\|)?\s*([A-Za-z_][A-Za-z0-9_]*)\s*$')
_CLASS = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s+(known|assumed|unknown);\s*$")
_EREDGE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s+([|}][|o](?:--|\.\.)[|o][|{])\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*"([^"]*)"\s*$')
_ERENT = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)(?:\["([^"]*)"\])?\s*\{\s*$')
_ERATTR = re.compile(r'^\s*(\S+)\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+([A-Z,]+))?(?:\s+"([^"]*)")?\s*$')


def parse_mermaid(text: str) -> dict:
    """Parse the Mermaid this module writes into a neutral graph:
    {"type": "flowchart"|"erDiagram", "nodes": {id: {"label", "status"?, "attrs"?}}, "edges": [{from,to,label,dashed,card?}]}"""
    lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("%%")]
    if not lines:
        raise ModelError("empty Mermaid")
    head = lines[0].strip()
    if head.startswith("erDiagram"):
        return _parse_er(lines[1:])
    if head.startswith("flowchart"):
        return _parse_flow(lines[1:])
    raise ModelError(f"unsupported Mermaid diagram: {head}")


_SUBGRAPH = re.compile(r'^\s*subgraph\s+([A-Za-z_][A-Za-z0-9_]*)\s*\["([^"]*)"\]\s*$')


def _parse_flow(lines):
    g = {"type": "flowchart", "nodes": {}, "edges": [], "groups": {}}
    group = None
    for l in lines:
        s = l.strip()
        if s.startswith("classDef"):
            continue
        if s == "end":
            group = None
            continue
        m = _SUBGRAPH.match(l)
        if m:
            group = m[1]
            g["groups"][m[1]] = m[2]
            continue
        m = _CLASS.match(l)
        if m:
            g["nodes"].setdefault(m[1], {})["status"] = m[2]
            continue
        m = _FEDGE.match(l)
        if m:
            g["edges"].append({"from": m[1], "to": m[4], "label": m[3] or "", "dashed": "." in m[2],
                               "directed": ">" in m[2]})
            continue
        m = _NODE.match(l)
        if m:
            node = g["nodes"].setdefault(m[1], {})
            node["label"] = m[2]
            if group:
                node["group"] = group
            continue
        raise ModelError(f"line not in the framework Mermaid subset: {l!r}")
    return g


def _parse_er(lines):
    g = {"type": "erDiagram", "nodes": {}, "edges": []}
    cur = None
    for l in lines:
        s = l.strip()
        if cur is None:
            m = _EREDGE.match(l)
            if m:
                sym = m[2].replace("..", "--")
                g["edges"].append({"from": m[1], "to": m[3], "label": m[4], "dashed": ".." in m[2],
                                   "card": _ER_REV.get(sym)})
                continue
            m = _ERENT.match(l)
            if m:
                cur = m[1]
                g["nodes"].setdefault(cur, {"label": m[2] if m[2] is not None else cur, "attrs": []})
                continue
            raise ModelError(f"line not in the framework Mermaid subset: {l!r}")
        if s == "}":
            cur = None
            continue
        m = _ERATTR.match(l)
        if not m:
            raise ModelError(f"attribute line not understood: {l!r}")
        g["nodes"][cur]["attrs"].append({"type": m[1], "name": m[2], "keys": (m[3] or "").split(",") if m[3] else [],
                                          "comment": m[4] or ""})
    return g


def graph_of(kind: str, m: dict) -> dict:
    """The graph the Mermaid of this model must contain: parse of to_mermaid (single definition of truth)."""
    return parse_mermaid(to_mermaid(kind, m))
