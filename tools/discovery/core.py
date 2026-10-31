"""Bronze discovery: pure-Python decision logic (no Spark). Spark access is in spark_io.py.

Methods follow the data-profiling literature, scaled down to what an agent pipeline needs:
  - Single-column profiling (cardinality, nulls, patterns, value distributions)       [Abedjan, Golab, Naumann 2015/2018]
  - Unique column combinations by bottom-up Apriori over a pruned column pool,
    verified exactly on the full table (HCA / DUCC idea: prune by distinct counts,
    never test supersets of a found key)                                              [Abedjan et al.; Heise et al. DUCC]
  - Unary inclusion dependencies as foreign-key candidates: pre-filter by type,
    distinct counts, value ranges, and name similarity; verify containment on
    distinct value sets (SPIDER idea: discard on first missing value -> here: ratio)  [Bauckmann et al. SPIDER]
  - Foreign-key ranking heuristics: referenced side is a key, name similarity,
    dependent values look like a sample of the key, surrogate auto-increment caution  [Rostin et al. 2009; Zhang et al. 2010]
  - Grain declaration and table roles (fact / dimension / bridge / aggregate)          [Kimball & Ross, The Data Warehouse Toolkit]

Everything here works on small summaries (profiles), never on raw data.
"""
from __future__ import annotations

import itertools
import re

TECH_COL = re.compile(r"^(_.*|load_?ts|ingest_?ts|etl_.*|batch_?id|file_?name|source_?file|dw_.*|rec_?src)$", re.I)
STAGING = re.compile(r"(^|_)(stg|tmp|temp|bkp|backup|old|test|copy|archive|bak)(_|$|\d)", re.I)
AGG_NAME = re.compile(r"(^|_)(agg|sum|summary|daily|weekly|monthly|yearly|rpt|report|kpi|stats|v|vw|view|cube|mart)(_|$)", re.I)
KEYISH = {"id", "no", "nr", "num", "number", "code", "cd", "key", "seq", "line", "item", "pos", "idx", "ref"}
SEQISH = {"seq", "line", "item", "pos", "leg", "idx", "lineno", "sequence"}
DATEISH = {"date", "dt", "ts", "time", "timestamp", "day", "month", "period", "asof", "snapshot", "valid", "from", "to"}
SNAPISH = {"snapshot", "asof", "as_of", "period", "snap", "balance"}
DESCISH = {"name", "desc", "description", "text", "label", "title"}
# Application / operational tables that carry no business object (they must not reach silver by accident)
TECH_TABLE = re.compile(r"(^|_)(log|logs|audit|session|sessions|login|logon|trace|error|errors|exception|etl|job|jobs|batch|"
                        r"config|cfg|param|params|setting|settings|queue|lock|locks|sys|system|monitor|heartbeat|debug|"
                        r"usr_pref|preference|cache|token|tokens|event_log|changelog|chg_log)(_|$|\d)", re.I)
TECH_COLS = {"ip", "ip_address", "host", "hostname", "browser", "user_agent", "session", "session_id", "login", "logout",
             "level", "severity", "message", "msg", "stack", "stacktrace", "exception", "error", "error_code", "thread",
             "process_id", "pid", "action", "event_type", "status_message", "duration_ms", "request", "response", "url", "endpoint"}


def tokens(name: str, abbreviations: dict | None = None) -> set:
    """lower-case word tokens of an identifier: 'CNTR_NO' -> {'cntr','no'} (+ expanded abbreviations)."""
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(name))
    out = {t for t in re.split(r"[^A-Za-z0-9]+", s.lower()) if t}
    out |= {t[:-1] for t in out if len(t) > 3 and t.endswith("s")}          # plural -> singular
    if abbreviations:
        out |= {abbreviations[t] for t in list(out) if t in abbreviations}
    return out


def family(spark_type: str) -> str:
    t = str(spark_type).lower()
    if any(x in t for x in ("int", "long", "short", "byte")):
        return "int"
    if any(x in t for x in ("double", "float", "decimal")):
        return "num"
    if "timestamp" in t or t == "date" or t.startswith("date"):
        return "date"
    if "bool" in t:
        return "bool"
    return "str"


def is_technical(col: str) -> bool:
    return bool(TECH_COL.match(col))


def key_likeness(p: dict) -> float:
    """0..1: how much a column looks like an identifier (name + profile)."""
    tk = tokens(p["column"])
    s = 0.0
    if tk & KEYISH:
        s += 0.5
    if p.get("family") in ("str", "int"):
        s += 0.2
    if (p.get("null_pct") or 0) == 0:
        s += 0.2
    if p.get("family") == "str" and (p.get("max_len") or 99) <= 40:
        s += 0.1
    if p.get("family") == "num":
        s -= 0.4
    return max(0.0, min(1.0, s))


# ---------------------------------------------------------------------------- keys
def key_score(p: dict, shared: set | None = None) -> float:
    """key_likeness + a bonus when the same column name exists in another table of the source
    (shared names such as MANDT, EBELN are join-key parts far more often than attributes)."""
    return key_likeness(p) + (0.4 if shared and p["column"] in shared else 0.0)


def key_pool(profiles: list, budget: dict, shared: set | None = None) -> list:
    """Columns allowed in composite-key search (pruned pool, best first)."""
    pool = [p for p in profiles
            if not is_technical(p["column"]) and (p.get("null_pct") or 0) <= budget.get("key_max_null_pct", 1.0)
            and p.get("family") != "num" and not (p.get("family") == "str" and (p.get("avg_len") or 0) > 60)
            and (p.get("approx_distinct") or 0) > 1]
    pool.sort(key=lambda p: (-key_score(p, shared), -(p.get("approx_distinct") or 0)))
    return pool[: budget.get("key_pool_size", 8)]


def find_keys(profiles: list, row_count: int, verify, budget: dict, shared: set | None = None, declared: list | None = None) -> dict:
    """Minimal unique column combinations up to size max_key_size.

    verify(cols) -> bool runs an exact uniqueness test on the FULL table (no nulls, no duplicates).
    Returns {"keys": [[cols]...], "checks": n, "best": [cols] or None}.
    """
    sample_rows = max(1, min(row_count, budget.get("sample_rows", 200000)))
    checks, keys = 0, []
    max_checks = budget.get("max_key_checks", 15)

    def try_(cols):
        nonlocal checks
        if checks >= max_checks:
            return False
        checks += 1
        return verify(list(cols))

    names_all = {p["column"].lower(): p["column"] for p in profiles}
    for d in declared or []:                                 # keys declared in Unity Catalog: test first (they are informational)
        cols = [names_all.get(c.lower()) for c in d]
        if all(cols) and try_(cols):
            keys.append(cols)
    singles = [p for p in profiles if not is_technical(p["column"]) and [p["column"]] not in keys
               and (((p.get("null_pct") or 0) == 0 and (p.get("approx_distinct") or 0) >= 0.95 * sample_rows) or stats_unique(p))]
    singles.sort(key=lambda p: -key_score(p, shared))
    for p in singles:
        if try_([p["column"]]):
            keys.append([p["column"]])
    pool = key_pool(profiles, budget, shared)
    names = [p["column"] for p in pool]
    dist = {p["column"]: max(1, p.get("approx_distinct") or 1) for p in pool}
    found = [set(k) for k in keys]
    for size in range(2, budget.get("max_key_size", 3) + 1):
        for combo in itertools.combinations(names, size):
            s = set(combo)
            if any(f <= s for f in found):                      # minimality: never test a superset of a key
                continue
            prod = 1
            for c in combo:
                prod *= dist[c]
            if prod < 0.95 * sample_rows:                        # cannot be unique (distinct-count pruning)
                continue
            if try_(combo):
                keys.append(list(combo))
                found.append(s)
        if keys and size >= 2:
            break
    order = {p["column"]: i for i, p in enumerate(profiles)}
    keys = [sorted(k, key=lambda c: order.get(c, 999)) for k in keys]     # show key parts in table column order
    best = None
    if keys:
        best = sorted(keys, key=lambda k: (len(k), -sum(key_score(next(p for p in profiles if p["column"] == c), shared) for c in k)))[0]
    return {"keys": keys, "checks": checks, "best": best}


# ---------------------------------------------------------------------------- links (inclusion dependencies)
def _ranges_overlap(a: dict, b: dict) -> bool:
    if a["family"] in ("int", "num", "date"):
        try:
            return not (str(a["max"]) < str(b["min"]) or str(a["min"]) > str(b["max"])) if a["family"] == "date" else \
                not (float(a["max"]) < float(b["min"]) or float(a["min"]) > float(b["max"]))
        except (TypeError, ValueError):
            return True
    al, bl = (a.get("min_len"), a.get("max_len")), (b.get("min_len"), b.get("max_len"))
    if None in al or None in bl:
        return True
    return not (al[1] < bl[0] - 3 or al[0] > bl[1] + 3)          # allow format noise (spaces, dashes)


def name_similarity(dep_table: str, dep_col: str, ref_table: str, ref_col: str, abbr: dict) -> float:
    d = tokens(dep_col, abbr) - {"id", "no", "cd", "code", "key", "nr", "num"}
    r = (tokens(ref_col, abbr) | tokens(ref_table, abbr)) - {"id", "no", "cd", "code", "key", "nr", "num"}
    full_d, full_r = tokens(dep_col, abbr), tokens(ref_col, abbr)
    s = 0.0
    if full_d == full_r:
        s += 0.6
    if d and r:
        s += 0.4 * len(d & r) / len(d | r) * 2
    return min(1.0, s)


def link_candidates(tables: dict, keys: dict, budget: dict, abbr: dict | None = None) -> list:
    """Rank candidate inclusion dependencies dep.col ⊆ ref.key_col.

    tables: {table: {"row_count": n, "columns": [profile...]}}; keys: {table: {"keys": [[...]], "best": [...]}}
    Referenced side: single-column keys only (unary INDs). Dependent side: any compatible column.
    """
    abbr = abbr or {}
    refs = []
    for t, k in keys.items():
        for kk in k.get("keys", []):
            if len(kk) == 1:
                p = next(p for p in tables[t]["columns"] if p["column"] == kk[0])
                refs.append((t, p))
    out = []
    for rt, rp in refs:
        for dt, info in tables.items():
            for dp in info["columns"]:
                if dt == rt and dp["column"] == rp["column"]:
                    continue
                if is_technical(dp["column"]) or dp["family"] in ("num", "bool"):
                    continue
                if {dp["family"], rp["family"]} - {"int", "str"} and dp["family"] != rp["family"]:
                    continue
                if (dp.get("approx_distinct") or 0) < 2:
                    continue
                # a foreign key cannot have (many) more distinct values than its parent key; format variants
                # (case, spaces) can add some, so allow budget link_distinct_slack (default x2)
                ref_full = max(1, tables[rt]["row_count"])
                if (dp.get("approx_distinct") or 0) > budget.get("link_distinct_slack", 2.0) * ref_full:
                    continue
                if dp["family"] == rp["family"] and not _ranges_overlap(dp, rp):
                    continue
                ns = name_similarity(dt, dp["column"], rt, rp["column"], abbr)
                shape = 0.2 if set(dp.get("patterns") or []) & set(rp.get("patterns") or []) else 0.0
                score = ns + shape + 0.2 * key_likeness(dp)
                if score < budget.get("min_link_score", 0.3):
                    continue
                out.append({"dep_table": dt, "dep_column": dp["column"], "ref_table": rt, "ref_column": rp["column"],
                            "score": round(score, 3), "name_similarity": round(ns, 3)})
    out.sort(key=lambda x: -x["score"])
    return out[: budget.get("max_link_checks", 400)]


def link_cols(name: str) -> list:
    """'MANDT+EBELN' -> ['MANDT', 'EBELN'] (composite links are stored with '+')."""
    return [c for c in str(name).split("+") if c]


def composite_link_candidates(tables: dict, keys: dict, budget: dict, abbr: dict | None = None) -> list:
    """n-ary inclusion dependency candidates: dep.(c1..cn) ⊆ ref.(k1..kn) for composite keys of size 2..max_fk_columns.

    Built level-wise from per-component candidates (as in the n-ary IND algorithms of the survey: MIND/BINDER
    build n-ary candidates only from plausible unary parts). To stay cheap, each component needs a compatible
    type and a name score >= composite_min_name_score; only the best `composite_options` columns per component
    are combined. Typical case: SAP-style header/line tables (MANDT+EBELN -> header, MANDT+EBELN+EBELP -> line).
    """
    abbr = abbr or {}
    mx = budget.get("max_fk_columns", 3)
    min_ns = budget.get("composite_min_name_score", 0.5)
    n_opt = budget.get("composite_options", 2)
    out = []
    for rt, k in keys.items():
        rprof = {p["column"]: p for p in tables[rt]["columns"]}
        for kk in k.get("keys", []):
            if not 2 <= len(kk) <= mx:
                continue
            for dt, info in tables.items():
                if dt == rt:
                    continue
                options = []
                for rc in kk:
                    rp = rprof[rc]
                    opts = []
                    for dp in info["columns"]:
                        if is_technical(dp["column"]):
                            continue
                        fams = {dp["family"], rp["family"]}
                        if dp["family"] != rp["family"] and not fams <= {"int", "str"}:
                            continue
                        if dp["family"] == rp["family"] and not _ranges_overlap(dp, rp):
                            continue
                        ns = name_similarity(dt, dp["column"], rt, rc, abbr)
                        if ns >= min_ns:
                            opts.append((ns, dp["column"]))
                    opts.sort(reverse=True)
                    options.append(opts[:n_opt])
                if not all(options):
                    continue
                for combo in itertools.product(*options):
                    cols = [c for _, c in combo]
                    if len(set(cols)) != len(cols):
                        continue
                    score = sum(s for s, _ in combo) / len(combo)
                    out.append({"dep_table": dt, "dep_column": "+".join(cols), "ref_table": rt, "ref_column": "+".join(kk),
                                "score": round(score + 0.3, 3), "name_similarity": round(score, 3)})
    out.sort(key=lambda x: -x["score"])
    return out[: budget.get("max_composite_link_checks", 100)]


def judge_link(c: dict, dep_unique: bool, budget: dict) -> dict:
    """Turn measured containment into a decision.  c has containment_raw, containment_norm, coverage."""
    raw, norm = c.get("containment_raw") or 0, c.get("containment_norm") or 0
    best = max(raw, norm)
    hi, lo = budget.get("fk_containment_high", 0.98), budget.get("fk_containment_low", 0.8)
    status = "fk" if best >= hi else "fk_partial" if best >= lo else "no_link"
    note = []
    if norm >= hi and raw < hi:
        note.append("matches only after normalisation (trim/upper/remove spaces and dashes): needs a key rule")
    if status == "fk_partial":
        note.append(f"{(1 - best):.1%} of dependent values have no parent: orphans or wrong link")
    card = "1:1" if dep_unique else "N:1"
    return {**c, "status": status, "cardinality": card if status != "no_link" else None, "note": "; ".join(note)}


def shared_domains(tables: dict, budget: dict) -> list:
    """Low-cardinality columns in different tables whose value sets overlap (codes used across tables)."""
    lows = [(t, p) for t, info in tables.items() for p in info["columns"]
            if p.get("topk") and not is_technical(p["column"]) and not p.get("redacted")]   # redacted values are not a domain
    out = []
    for (t1, a), (t2, b) in itertools.combinations(lows, 2):
        if t1 == t2:
            continue
        va = {str(v).strip().upper() for v, _ in a["topk"]}
        vb = {str(v).strip().upper() for v, _ in b["topk"]}
        if not va or not vb:
            continue
        j = len(va & vb) / len(va | vb)
        if j >= budget.get("domain_jaccard_min", 0.6):
            out.append({"table_a": t1, "column_a": a["column"], "table_b": t2, "column_b": b["column"], "jaccard": round(j, 3),
                        "shared_values": ", ".join(sorted(va & vb)[:8])})
    out.sort(key=lambda x: -x["jaccard"])
    return out


# ---------------------------------------------------------------------------- roles, grain, lineage
ROLE_TO_CLASS = {"technical": None, "master": "master", "reference": "reference", "transaction_header": "event", "transaction_line": "event",
                 "event": "event", "snapshot": "snapshot", "bridge": "bridge", "aggregate": "measure", "staging": None, "unknown": None}
ROLE_TO_KINDS = {"master": {"party", "thing", "place"}, "reference": {"classification"}, "transaction_header": {"event", "agreement"},
                 "transaction_line": {"event", "agreement", "measure"}, "event": {"event"}, "snapshot": {"measure", "thing"},
                 "bridge": {"measure", "agreement", "classification"}, "aggregate": {"measure"}}


def classify(table: str, info: dict, key: list | None, out_links: list, in_links: list, budget: dict) -> dict:
    """Role of a bronze table, with reasons and confidence. Kimball-style: what does one row mean?"""
    cols = [p for p in info["columns"] if not is_technical(p["column"])]
    names = [p["column"] for p in cols]
    rows = info["row_count"]
    fk_cols = {c for l in out_links for c in link_cols(l["dep_column"])}
    key = key or []
    key_set = set(key)
    measures = [p for p in cols if p["family"] == "num" and p["column"] not in key_set and p["column"] not in fk_cols]
    dates = [p for p in cols if p["family"] == "date" or tokens(p["column"]) & {"date", "dt", "ts", "time"}]
    desc = [p for p in cols if p["family"] == "str" and p["column"] not in key_set and p["column"] not in fk_cols]
    ttk = tokens(table)
    reasons, scores = {}, {}

    def add(role, pts, why):
        scores[role] = scores.get(role, 0) + pts
        reasons.setdefault(role, []).append(why)

    if STAGING.search(table):
        add("staging", 5, "name looks like a copy, backup, or staging table")
    tech_hits = {c.lower() for c in names if c.lower() in TECH_COLS or (tokens(c) & {"ip", "browser", "session", "severity", "stacktrace", "useragent"})}
    if TECH_TABLE.search(table):
        add("technical", 3, "name looks like an application log, audit, session, job, or config table")
    if len(tech_hits) >= 2:
        add("technical", 2, f"log-style columns ({', '.join(sorted(tech_hits)[:5])})")
    if "technical" in scores and not in_links:
        add("technical", 1, "no other table points to it")
    if AGG_NAME.search(table):
        add("aggregate", 2, "name looks like a summary or report table")
    if key and set(key) <= fk_cols | {c for c in key if tokens(c) & DATEISH} and measures and not (len(key) == 1):
        add("aggregate", 2, "key is only foreign keys/dates, with numeric measures")
    if not key:
        add("aggregate", 1, "no unique key found")
        add("unknown", 1, "no unique key found")
    single = len(key) == 1
    if single and rows <= budget.get("reference_max_rows", 1000) and len(cols) <= 4 and \
            (tokens(key[0]) & {"code", "cd", "type", "status", "cat", "class"} or any(tokens(c) & DESCISH for c in names)):
        add("reference", 3, f"small code list ({rows} rows, {len(cols)} columns) with a code key")
    if single and in_links:
        add("master", 2, f"referenced by {len(in_links)} column(s) in other tables")
    if single and len(desc) >= 2 and len(measures) <= 1:
        add("master", 1, f"{len(desc)} descriptive attributes")
    child_lines = [l for l in in_links if l.get("dep_unique") is False or str(l.get("dep_unique")).lower() == "false"]
    if key and dates and child_lines and not (key_set & fk_cols):
        add("transaction_header", 3, f"own key + date, with {len(child_lines)} child table(s) holding many rows per key")
    if single and out_links and dates:
        add("transaction_header", 2, "own id + foreign keys + date")
        if in_links and any(l.get("dep_unique") is False for l in in_links):
            add("transaction_header", 1, "has child rows (line table points to it)")
    if len(key) >= 2 and key_set & fk_cols and any(tokens(c) & SEQISH for c in key):
        add("transaction_line", 3, "key = parent foreign key + sequence/line number")
    elif len(key) >= 2 and key_set & fk_cols and len(key_set - fk_cols) == 1 and not key_set <= fk_cols:
        add("transaction_line", 3, f"key = parent foreign key + one line column ({', '.join(sorted(key_set - fk_cols))})")
    if dates and out_links and (len(key) >= 2 or not single) and not any(tokens(c) & SNAPISH for c in key):
        add("event", 2, "time-stamped rows linked to masters")
    if any(tokens(c) & SNAPISH for c in key) or (key and any(tokens(c) & {"date", "dt"} for c in key) and measures and not out_links == []):
        add("snapshot", 2, "key contains a snapshot/as-of/period date")
    if len(key) == 2 and key_set <= fk_cols and len(cols) <= 4:
        add("bridge", 4, "key = two foreign keys, few other columns")
    if not scores:
        add("unknown", 1, "no rule matched")
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    role, top = ranked[0]
    margin = top - (ranked[1][1] if len(ranked) > 1 else 0)
    conf = "high" if top >= 3 and margin >= 2 else "medium" if margin >= 1 else "low"
    if role == "staging":
        conf = "high"
    if role == "technical" and top >= 5 and margin >= 2:
        conf = "high"
    return {"role": role, "role_confidence": conf, "role_reasons": "; ".join(reasons[role]),
            "alternatives": ", ".join(f"{r}({s})" for r, s in ranked[1:3]), "data_class": ROLE_TO_CLASS.get(role)}


def grain(table: str, key: list | None, role: str) -> str:
    if not key:
        return f"Unknown: no unique key found in {table}. Ask the client or check duplicates."
    return f"One row per {' + '.join(key)} ({role.replace('_', ' ')})."


def lineage_levels(tables: list, fks: list) -> dict:
    """Level 0 = root tables (referenced, refer to nothing). Level n = depends on level < n."""
    deps = {t: {l["ref_table"] for l in fks if l["dep_table"] == t and l["ref_table"] != t} for t in tables}
    level, todo = {}, set(tables)
    for n in range(len(tables) + 1):
        ready = {t for t in todo if deps[t] <= set(level)}
        if not ready:
            break
        for t in ready:
            level[t] = n
        todo -= ready
    for t in todo:
        level[t] = -1                                                   # cycle
    return level


def derived_candidates(tables: dict, roles: dict, keys: dict) -> list:
    """Aggregate tables whose key columns also exist (by name) in a larger detail table."""
    out = []
    for t, r in roles.items():
        if r["role"] != "aggregate":
            continue
        kcols = {c.lower() for c in (keys.get(t, {}).get("best") or [])} or \
                {p["column"].lower() for p in tables[t]["columns"] if p["family"] != "num" and not is_technical(p["column"])}
        for d, info in tables.items():
            if d == t or roles[d]["role"] in ("aggregate", "staging"):
                continue
            dcols = {p["column"].lower() for p in info["columns"]}
            common = kcols & dcols
            if len(common) >= max(1, len(kcols) - 1) and info["row_count"] > tables[t]["row_count"]:
                out.append({"table": t, "derived_from": d, "shared_columns": ", ".join(sorted(common)),
                            "evidence": f"{len(common)}/{len(kcols)} grouping columns in {d}; {info['row_count']} > {tables[t]['row_count']} rows"})
    return out


# ---------------------------------------------------------------------------- ontology mapping
def split_camel(name: str) -> set:
    return tokens(re.sub(r"([a-z])([A-Z])", r"\1 \2", name))


def map_ontology(table: str, info: dict, role: dict, business: dict, preferred: list | None = None) -> list:
    """Rank business objects for a bronze table. Name tokens + synonyms + abbreviations + kind fit."""
    abbr = business.get("abbreviations", {}) or {}
    ttk = tokens(table, abbr)
    classifier_words = ttk & {"type", "status", "category", "class", "group", "kind", "reason", "code"}
    ctk = set().union(*[tokens(p["column"], abbr) for p in info["columns"] if not is_technical(p["column"])] or [set()])
    res = []
    for name, o in business["business_objects"].items():
        vocab = split_camel(name) | set().union(*[tokens(s, abbr) for s in o.get("synonyms", [])] or [set()])
        whole = {name.lower()} | {s.lower().replace(" ", "") for s in o.get("synonyms", [])}
        s = 0.0
        if ttk & whole or "".join(sorted(ttk)) in whole:
            s += 3
        s += 2 * len(ttk & vocab) / max(1, len(split_camel(name)))
        s += 0.3 * min(3, len(ctk & vocab))
        if role.get("role") in ROLE_TO_KINDS and o.get("kind") in ROLE_TO_KINDS[role["role"]]:
            s += 1
        if preferred and name in preferred:
            s += 0.5
        if classifier_words and o.get("kind") != "classification":
            s -= 2.5                       # 'container_types' is a code list ABOUT containers, not the Container object
        if role.get("role") == "aggregate" and o.get("kind") != "measure":
            s -= 2.5                       # a summary of legs is not the ShipmentLeg object
        if s > 0.5:
            res.append({"business_object": name, "score": round(s, 2), "kind": o.get("kind")})
    res.sort(key=lambda x: -x["score"])
    return res[:3]


def ontology_confidence(cands: list) -> str:
    if not cands:
        return "none"
    top = cands[0]["score"]
    margin = top - (cands[1]["score"] if len(cands) > 1 else 0)
    return "high" if top >= 4 and margin >= 1.5 else "medium" if top >= 2.5 and margin >= 0.75 else "low"


# ---------------------------------------------------------------------------- Unity Catalog metadata (pure helpers)
def declared_keys(constraint_rows: list) -> dict:
    """{table_name: [[cols], ...]} from declared PRIMARY KEY / UNIQUE constraints (tried first, still verified)."""
    out = {}
    for c in constraint_rows or []:
        if c.get("type") in ("PRIMARY KEY", "UNIQUE") and c.get("columns"):
            out.setdefault(c["table"].lower(), []).append(list(c["columns"]))
    return out


def declared_links(constraint_rows: list, schema_prefix: str) -> list:
    """Link candidates from declared FOREIGN KEY constraints (score 9: tested first)."""
    out = []
    for c in constraint_rows or []:
        if c.get("type") == "FOREIGN KEY" and c.get("ref_table") and c.get("columns") and c.get("ref_columns"):
            out.append({"dep_table": f"{schema_prefix}.{c['table']}", "dep_column": "+".join(c["columns"]), "ref_table": c["ref_table"],
                        "ref_column": "+".join(c["ref_columns"]), "score": 9.0, "name_similarity": 1.0, "declared": c.get("name")})
    return out


def apply_stats(profile: dict, stat_rows: list) -> dict:
    """Attach exact column statistics (SHOW STATISTICS) to a sampled profile: stats_distinct / stats_nulls / stats_rows."""
    by = {(str(r["table"]).lower(), str(r["column"]).lower()): r for r in stat_rows or []}
    for p in profile["columns"]:
        r = by.get((profile["table"].lower(), p["column"].lower()))
        if r and r.get("distinct_count") is not None:
            p["stats_distinct"], p["stats_nulls"], p["stats_rows"] = int(r["distinct_count"]), int(r.get("num_nulls") or 0), int(r.get("num_rows") or 0)
    return profile


def stats_unique(p: dict) -> bool:
    """True when exact statistics say the column has no NULLs and one distinct value per row."""
    return bool(p.get("stats_rows")) and not p.get("stats_nulls") and p.get("stats_distinct", 0) >= 0.999 * p["stats_rows"]


def lineage_view(table_rows: list, column_rows: list, ours: list) -> dict:
    """Interpret system.access lineage for the source's tables.
    writers: what writes each table (job, pipeline, notebook) and from where (tables or paths outside the source);
    readers: tables built from ours; derived: column-level derived-from edges between our own tables."""
    def sk(t):
        return ".".join(str(t or "").lower().split(".")[-2:]) if t else ""
    full = {sk(t): t for t in ours}
    ours_l = set(full)
    writers, readers, outside, derived = {}, {}, set(), set()
    for r in table_rows or []:
        src_full = (r.get("source_table_full_name") or "").lower()
        src, tgt = sk(r.get("source_table_full_name")), sk(r.get("target_table_full_name"))
        if tgt in ours_l:
            w = writers.setdefault(tgt, set())
            w.add(f"{r.get('entity_type') or 'unknown'}" + (f" job {r['job_id']}" if r.get("job_id") else "")
                  + (f" pipeline {r['pipeline_id']}" if r.get("pipeline_id") else ""))
            if src and src not in ours_l:
                outside.add(src_full)
            if r.get("source_path") and not src:
                w.add(f"path {r['source_path']}")
        if src in ours_l and tgt and tgt not in ours_l:
            readers.setdefault(src, set()).add((r.get("target_table_full_name") or "").lower())
    for r in column_rows or []:
        src, tgt = sk(r.get("source_table_full_name")), sk(r.get("target_table_full_name"))
        if src in ours_l and tgt in ours_l and src != tgt:
            derived.add((full[tgt], full[src]))
    return {"writers": {full[k]: sorted(v) for k, v in writers.items()}, "readers": {full[k]: sorted(v) for k, v in readers.items()},
            "upstream_outside": sorted(outside), "derived": sorted(derived)}


def doc_gaps(doc_tables: set, doc_columns: dict, bronze: dict) -> dict:
    """Compare what documents name with what bronze has (case-insensitive, prefixes like T_ or schema ignored).
    doc_columns: {DOC_TABLE: {COL, ...}}; bronze: {full_table: {col, ...}}."""
    def k(n):
        n = str(n).split(".")[-1].lower()
        return n[2:] if n.startswith(("t_", "v_")) else n
    bmap = {k(t): t for t in bronze}
    found = {d: bmap.get(k(d)) for d in doc_tables}
    missing = sorted(d for d, b in found.items() if not b)
    undocumented = sorted(t for t in bronze if k(t) not in {k(d) for d in doc_tables})
    col_gaps = []
    for d, cols in (doc_columns or {}).items():
        b = found.get(d) or bmap.get(k(d))
        if not b:
            continue
        bc = {c.lower() for c in bronze[b]}
        for c in sorted(cols):
            if c.lower() not in bc:
                col_gaps.append({"doc_table": d, "bronze_table": b, "column": c, "gap": "documented, not in bronze"})
    return {"documented_not_in_bronze": missing, "in_bronze_not_documented": undocumented, "columns": col_gaps}


def score_related(rows: list, lineage_outside: list, budget: dict) -> list:
    """Rank tables outside the source schema that may belong to it."""
    out = {}
    for r in rows or []:
        full = f"{r['table_catalog']}.{r['table_schema']}.{r['table_name']}"
        s = 2.0 * int(r.get("name_hit") or 0) + 1.0 * int(r.get("key_cols_shared") or 0)
        out[full] = {"table": full, "score": s, "why": ", ".join(x for x in [("name matches" if r.get("name_hit") else ""),
                     (f"shares key columns {sorted(c for c in (r.get('shared_columns') or []) if c)}" if r.get("key_cols_shared") else "")] if x)}
    for full in lineage_outside or []:
        e = out.setdefault(full, {"table": full, "score": 0.0, "why": ""})
        e["score"] += 3.0
        e["why"] = (e["why"] + ", " if e["why"] else "") + "writes into this source's tables (lineage)"
    res = sorted(out.values(), key=lambda x: -x["score"])
    return [r for r in res if r["score"] >= budget.get("related_min_score", 2.0)][: budget.get("max_related", 20)]



def scope(role_row: dict, allowed_objects: set) -> tuple:
    """Should this bronze table feed silver? Returns (scope, reason).
    in_scope        maps (with medium/high confidence) to a business object this source is allowed to provide
    out_of_scope    technical (logs, audit, sessions, jobs, config) or staging (copies, backups)
    derive_instead  aggregates: rebuild from the detail table
    review          everything else: a card asks, a person approves at CP2"""
    role, bo, oc = role_row.get("role"), role_row.get("business_object") or "", role_row.get("ontology_confidence")
    if role == "staging":
        return "out_of_scope", "copy, backup, or staging table"
    if role == "technical":
        return ("out_of_scope", "application or operational table (log, audit, session, job, config)") if role_row.get("role_confidence") == "high" \
            else ("review", "looks like an application or operational table")
    if role == "aggregate":
        return "derive_instead", "summary of a detail table"
    if bo and not bo.startswith("NEW:") and bo != "none" and oc in ("high", "medium", "agent"):
        if not allowed_objects or bo in allowed_objects:
            return "in_scope", f"maps to {bo}"
        return "review", f"maps to {bo}, which is not in this source's business scope (sources.yaml)"
    return "review", "no clear business object"



# ---------------------------------------------------------------------------- column classes (names + content + UC tags)
# Spark (Java) regular expressions, tested on the sample with rlike; anchored to the whole value.
VALUE_KINDS = {
    "ip":         r"^\s*(\d{1,3}\.){3}\d{1,3}\s*$|^\s*([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\s*$",
    "email":      r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$",
    "uuid":       r"^\{?[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}\}?$",
    "url":        r"^(https?|ftp)://\S+$",
    "json":       r"^\s*[\[{].*[\]}]\s*$",
    "user_agent": r"(?i)(mozilla/|applewebkit|chrome/|safari/|okhttp|python-requests|curl/)",
    # needs a +, (, space, or dash: plain digit runs (epoch seconds, ids) are not phones; not an IPv4 address
    "phone":      r"^(?!\s*(\d{1,3}\.){3}\d{1,3}\s*$)(?=.*[+()\s-])\+?[\d\s().-]{7,20}$",
    "hash_token": r"^[0-9a-fA-F]{32,}$|^[A-Za-z0-9+/_-]{40,}={0,2}$",
    "text_ts":    r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}|^\d{2}[/.]\d{2}[/.]\d{4}[ T]\d{2}:\d{2}",
}
APP_LOG_NAMES = {"ip", "ipaddress", "ipaddr", "host", "hostname", "browser", "useragent", "agent", "session", "sessionid", "login",
                 "logon", "logout", "logintime", "lastlogin", "device", "deviceid", "os", "osversion", "clientversion", "appversion",
                 "requestid", "traceid", "spanid", "correlationid", "thread", "pid", "stacktrace", "stack", "severity", "loglevel",
                 "endpoint", "referrer", "referer", "cookie", "click", "pageview", "durationms", "responsetimems"}
AUDIT_NAMES = {"createdby", "createdat", "createdon", "createdate", "createdts", "creby", "credat", "updatedby", "updatedat", "updatedon",
               "updatedts", "modifiedby", "modifiedat", "modifiedon", "changedby", "changedon", "lastupdated", "lastupdts", "lastupdby",
               "insertts", "inserttime", "recordstatus", "recstatus", "version", "rowversion", "etlbatch", "loadid", "deleted", "isdeleted"}
SECRET_NAMES = {"password", "passwd", "pwd", "secret", "token", "apikey", "accesstoken", "refreshtoken", "hash", "salt", "pin", "otp"}
PII_NAMES = {"email", "mail", "phone", "mobile", "telephone", "fax", "firstname", "lastname", "fullname", "surname", "birthdate",
             "dob", "dateofbirth", "ssn", "nationalid", "passport", "street", "address", "zip", "zipcode", "postcode", "iban"}
FREE_TEXT_NAMES = {"comment", "comments", "note", "notes", "remark", "remarks", "memo", "description", "text", "body", "payload", "message"}


def _flat(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def classify_column(p: dict, key_cols: set = (), fk_cols: set = (), tags: list | None = None, masked: bool = False,
                    table_log_names: int = 0) -> dict:
    """Class of one bronze column from its NAME, its CONTENT (value kinds, nulls, distinct, length), and Unity Catalog TAGS.
    Returns {"column_class", "use": map | technical_only | out_of_scope | review | drop, "reasons"}."""
    name, fl, toks = p["column"], _flat(p["column"]), tokens(p["column"])
    k = p.get("kinds") or {}
    reasons = []
    tagtxt = " ".join(tags or []).lower()
    nd, nullp, avgl = p.get("approx_distinct") or 0, p.get("null_pct") or 0, p.get("avg_len") or 0

    def out(cls, use, why):
        return {"column_class": cls, "use": use, "reasons": "; ".join([why] + reasons)}
    pii_name = fl in PII_NAMES or bool(toks & {"email", "phone", "mobile", "birth"}) or \
        (bool(toks & {"name"}) and bool(toks & {"contact", "first", "last", "full", "person", "user", "buyer", "employee", "driver"}))
    pii_kind = max(k.get("email", 0), k.get("phone", 0) if k.get("ip", 0) < 0.5 else 0) >= 0.5
    if (name in key_cols or name in fk_cols) and (pii_name or pii_kind):
        return out("personal_data", "review", "part of a key AND personal data: map only with privacy handling (hash or keep_tagged)")
    if name in key_cols:
        return out("key", "map", "part of the table's unique key")
    if name in fk_cols:
        return out("foreign_key", "map", "links to another table")
    if nullp >= 99.9:
        return out("empty", "drop", "no values in the sample")
    if nd == 1 and nullp == 0 and not is_technical(name):
        return out("constant", "drop", "one value only")
    if fl in SECRET_NAMES or toks & {"password", "secret", "token", "apikey"} or k.get("hash_token", 0) >= 0.8 and fl not in ("id",):
        return out("secret_or_token", "out_of_scope", "name or content looks like a password, token, or hash")
    if any(x in tagtxt for x in ("pii", "class.", "sensitive", "personal")) or masked:
        reasons.append("Unity Catalog tag or mask marks it sensitive")
    pii_content = max(k.get("email", 0), k.get("phone", 0) if k.get("ip", 0) < 0.5 else 0)
    if pii_name or pii_content >= 0.5 or reasons:
        return out("personal_data", "review", "name, content, or tag shows personal data" + (f" (email {k.get('email', 0):.0%}, phone {k.get('phone', 0):.0%})" if pii_content else ""))
    log_content = max(k.get("ip", 0), k.get("user_agent", 0), k.get("url", 0))
    log_name = fl in APP_LOG_NAMES or bool(toks & {"ip", "browser", "session", "login", "logon", "logout", "useragent", "stacktrace", "severity"})
    if log_content >= 0.5 or (log_name and log_content >= 0.2):
        return out("application_log", "out_of_scope", "content looks like " + ", ".join(f"{x} {k[x]:.0%}" for x in ("ip", "user_agent", "url") if k.get(x)))
    if log_name and table_log_names >= 3:
        return out("application_log", "out_of_scope", f"name looks like an application log field, and the table has {table_log_names} such columns")
    if log_name:
        return out("application_log", "review", "name looks like an application log field (content does not confirm it)")
    if fl in AUDIT_NAMES or is_technical(name) or (toks & {"created", "updated", "modified", "changed"} and toks & {"by", "at", "on", "ts", "date", "time", "user"}):
        return out("audit_metadata", "technical_only", "who/when a record was written, not business data")
    if k.get("json", 0) >= 0.5 or (avgl >= 200 and p.get("family") == "str"):
        return out("payload_or_free_text", "review", "JSON or long free text: may hide several fields or personal data")
    if fl in FREE_TEXT_NAMES and avgl >= 40:
        return out("payload_or_free_text", "review", "free text: check for personal data before mapping")
    if k.get("uuid", 0) >= 0.8:
        return out("system_id", "review", "UUIDs: a system identifier; map only if it is a business key or FK")
    if k.get("text_ts", 0) >= 0.8:
        return out("business_date", "map", "timestamps stored as text: convert, check the time zone")
    if p.get("family") == "num":
        return out("measure", "map", "numeric value")
    if p.get("family") == "date":
        return out("business_date", "map", "date or time")
    return out("business_attribute", "map", "descriptive value")



def log_name_count(profiles: list) -> int:
    return sum(1 for p in profiles if _flat(p["column"]) in APP_LOG_NAMES or
               tokens(p["column"]) & {"ip", "browser", "session", "login", "logon", "logout", "useragent", "stacktrace", "severity"})


SENSITIVE_CLASSES = {"personal_data", "secret_or_token", "application_log", "payload_or_free_text"}


def redact_values(profile: dict, tags_by_col: dict | None = None, masked: set | None = None) -> dict:
    """Remove raw values (min, max, top values) of sensitive columns BEFORE anything is written to disk.
    Sensitive = personal data, secrets, application-log values, free text/JSON (by name, content kinds, or UC tag/mask).
    Shapes (patterns such as 'aaaa@aaa.aaa'), ratios, and counts stay: they carry no personal value."""
    n_log = log_name_count(profile["columns"])
    for p in profile["columns"]:
        cls = classify_column(p, tags=(tags_by_col or {}).get(p["column"].lower()), masked=p["column"].lower() in (masked or set()),
                              table_log_names=n_log)["column_class"]
        if cls in SENSITIVE_CLASSES:
            p["min"] = p["max"] = None
            p["topk"] = [["<redacted>", sum(n for _, n in p.get("topk") or [])]] if p.get("topk") else []
            p["redacted"] = cls
    return profile
