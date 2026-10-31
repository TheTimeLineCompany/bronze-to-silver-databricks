"""Shared business-key normalisation for PySpark (checkpoint CP3b rules).

Every notebook uses these functions for business keys. Do not write ad-hoc
trim/upper/lpad code for keys in notebooks: then two sources could normalise the
same key in two different ways, and keys would not match across systems.

Example:
    from lib.keys import normalise, key_pattern_ok
    df = df.withColumn("container_number", normalise("container_number", F.col("CNTR_NO")))
"""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache

import yaml

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Unknown member: one deterministic row in every shared master. Child rows whose FK has no parent
# (orphan_policy: unknown_member) point to UNKNOWN_SK. Spark: sha2('#UNKNOWN', 256) gives the same value.
UNKNOWN_BK = "#UNKNOWN"
UNKNOWN_SK = hashlib.sha256(UNKNOWN_BK.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def rules(path: str | None = None) -> dict:
    path = path or os.path.join(_ROOT, "registry", "key_normalisation.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalise(rule_name: str, col):
    """Return a Spark Column with the named rule applied. Missing tokens become NULL."""
    from pyspark.sql import functions as F

    cfg = rules()
    r = cfg["rules"][rule_name]
    c = col.cast("string")
    if r.get("trim", True):
        c = F.trim(c)
    tokens = [t for t in cfg.get("null_tokens", [])]
    if tokens:
        c = F.when(F.upper(c).isin([t.upper() for t in tokens]) | c.isNull(), F.lit(None)).otherwise(c)
    for ch in r.get("remove_chars") or []:
        c = F.regexp_replace(c, _re_escape(ch), "")
    if r.get("case") == "upper":
        c = F.upper(c)
    elif r.get("case") == "lower":
        c = F.lower(c)
    lp = r.get("lpad")
    if lp:
        c = F.when(c.isNull(), None).otherwise(F.lpad(c, int(lp["length"]), str(lp["char"])))
    return c


def key_pattern_ok(rule_name: str, col):
    """Boolean Column: True when the normalised key matches the rule's pattern (or no pattern)."""
    from pyspark.sql import functions as F

    pat = rules()["rules"][rule_name].get("pattern")
    if not pat:
        return F.lit(True)
    return col.rlike(pat)


def normalise_py(rule_name: str, value):
    """Pure-Python version, used by tests and by the profiler's pattern report."""
    cfg = rules()
    r = cfg["rules"][rule_name]
    if value is None:
        return None
    v = str(value)
    if r.get("trim", True):
        v = v.strip()
    if v.upper() in {t.upper() for t in cfg.get("null_tokens", [])}:
        return None
    for ch in r.get("remove_chars") or []:
        v = v.replace(ch, "")
    if r.get("case") == "upper":
        v = v.upper()
    elif r.get("case") == "lower":
        v = v.lower()
    lp = r.get("lpad")
    if lp:
        v = v.rjust(int(lp["length"]), str(lp["char"]))
    return v


def _re_escape(ch: str) -> str:
    import re
    return re.escape(ch)


def lookup_expr(item):
    """One fk.lookup_on item -> Spark Column. A string is a SQL expression; {expr, key_rule} is normalised with the rule."""
    from pyspark.sql import functions as F
    if isinstance(item, str):
        return F.expr(item)
    c = F.expr(item["expr"])
    return normalise(item["key_rule"], c) if item.get("key_rule") else c


def lookup_sk(df, parent, lookup_on, parent_bk, parent_sk, out_col, orphan_policy="reject", quarantine=None):
    """Resolve one foreign key (single or COMPOSITE) to the parent's surrogate key.

    lookup_on: one item per parent business-key column, in the same order (fk.lookup_on in the STTM).
    The CURRENT parent row is used when the parent keeps history (is_current column).
    orphan_policy: unknown_member -> UNKNOWN_SK; allow_null -> NULL; reject -> rows are removed
    (and appended to `quarantine`, a table name, if given).
    Returns (df with out_col, number of rejected rows).
    """
    from pyspark.sql import functions as F
    if len(lookup_on) != len(parent_bk):
        raise ValueError(f"lookup_on has {len(lookup_on)} items, parent business key {parent_bk} has {len(parent_bk)}")
    p = parent.where("is_current") if "is_current" in parent.columns else parent
    keys = [f"__lk{i}" for i in range(len(parent_bk))]
    p = p.select(*[F.col(b).alias(k) for b, k in zip(parent_bk, keys)], F.col(parent_sk).alias("__lk_sk")).dropDuplicates(keys)
    d = df.select("*", *[lookup_expr(it).alias(k) for it, k in zip(lookup_on, keys)])
    j = d.join(p, on=keys, how="left")
    any_null = None
    for k in keys:                                     # a key with a NULL part has no parent: not an orphan, just no reference
        x = F.col(k).isNull()
        any_null = x if any_null is None else (any_null | x)
    orphan = F.col("__lk_sk").isNull() & ~any_null
    rejected = 0
    if orphan_policy == "unknown_member":
        j = j.withColumn(out_col, F.when(orphan, F.lit(UNKNOWN_SK)).otherwise(F.col("__lk_sk")))
    elif orphan_policy == "allow_null":
        j = j.withColumn(out_col, F.col("__lk_sk"))
    else:
        bad = j.where(orphan)
        rejected = bad.count()
        if rejected and quarantine:
            bad.drop(*keys, "__lk_sk").write.mode("append").saveAsTable(quarantine)
        j = j.where(~orphan).withColumn(out_col, F.col("__lk_sk"))
    return j.drop(*keys, "__lk_sk"), rejected
