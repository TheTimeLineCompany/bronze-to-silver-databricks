"""Column profiles on a sample (in memory only). Raw values never leave this module unredacted:
b2s.baseline.engine.redact() runs before anything is written."""
from __future__ import annotations

import re
from collections import Counter

from .rules_v11 import VALUE_KINDS, family

_KIND_RE = {k: re.compile(v) for k, v in VALUE_KINDS.items()}


def shape(v) -> str:
    """Letter/digit shape of a value: 'MSCU1000007' -> 'AAAA9999999', 'a.b@c.de' -> 'a.a@a.aa'."""
    out = []
    for ch in str(v):
        if ch.isdigit():
            out.append("9")
        elif ch.isalpha():
            out.append("A" if ch.isupper() else "a")
        else:
            out.append(ch)
    s = "".join(out)
    return re.sub(r"(.)\1{5,}", lambda m: m.group(1) * 5 + "+", s)


def profile_columns(rows: list[dict], columns: list[tuple[str, str]], topk: int = 20) -> list[dict]:
    n = len(rows)
    out = []
    for name, typ in columns:
        vals = [r.get(name) for r in rows]
        nn = [v for v in vals if v is not None]
        fam = family(typ)
        p = {"column": name, "type": typ, "family": fam,
             "null_pct": round(100.0 * (n - len(nn)) / n, 3) if n else 0.0,
             "approx_distinct": len(set(nn)), "min": None, "max": None, "avg_len": None, "max_len": None,
             "kinds": {}, "shapes": [], "topk": []}
        if nn:
            try:
                p["min"], p["max"] = min(nn), max(nn)
            except TypeError:
                s = [str(v) for v in nn]
                p["min"], p["max"] = min(s), max(s)
            lens = [len(str(v)) for v in nn]
            p["avg_len"], p["max_len"] = round(sum(lens) / len(lens), 2), max(lens)
            if fam == "str":
                for k, rx in _KIND_RE.items():
                    hit = sum(1 for v in nn if rx.search(str(v)))
                    if hit:
                        p["kinds"][k] = round(hit / len(nn), 3)
            p["shapes"] = [s for s, _ in Counter(shape(v) for v in nn).most_common(3)]
            p["topk"] = [[v, c] for v, c in Counter(nn).most_common(topk)]
        out.append(p)
    return out
