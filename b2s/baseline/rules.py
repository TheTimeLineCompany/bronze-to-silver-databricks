"""Column and key rules for the P1 baseline (first taken from the 2.4.0 discovery engine; maintained here).

Kept: identifier tokens, type families, key likeness and composite-key search (find_keys), column classes
(classify_column), and value redaction (redact_values). Changes for V1.4 live in b2s.baseline.engine, not here.
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



def stats_unique(p: dict) -> bool:
    """True when exact statistics say the column has no NULLs and one distinct value per row."""
    return bool(p.get("stats_rows")) and not p.get("stats_nulls") and p.get("stats_distinct", 0) >= 0.999 * p["stats_rows"]



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
