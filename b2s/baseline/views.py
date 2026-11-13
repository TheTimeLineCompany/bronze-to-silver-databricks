"""Shared by every bronze reader, so the fake reader and the Spark reader do the same work (feedback I-17 §2).

- quote(name): backtick-quote each part of a table name (names with spaces, dashes, reserved words).
- base_tables(view_text, schema, catalog): the tables a view reads, from its SQL text (FROM / JOIN), resolved to
  schema.table (or catalog.schema.table). CTE names are not tables. Views over views are followed by the reader.
"""
from __future__ import annotations

import re

_IDENT = r"(?:`(?:[^`]|``)+`|[A-Za-z_][A-Za-z0-9_$]*)"
_NAME = rf"{_IDENT}(?:\s*\.\s*{_IDENT}){{0,2}}"
_FROM = re.compile(rf"\b(?:FROM|JOIN)\s+({_NAME})", re.I)
_CTE = re.compile(rf"(?:\bWITH|,)\s*({_IDENT})\s+AS\s*\(", re.I)
_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
_STRING = re.compile(r"'(?:[^']|'')*'")


def split_name(name: str) -> list[str]:
    """Split on dots outside backticks: 'cat.`my schema`.t' -> ['cat', 'my schema', 't']; spaces inside a part stay."""
    parts, cur, quoted, i = [], "", False, 0
    while i < len(name):
        ch = name[i]
        if ch == "`":
            if quoted and name[i + 1:i + 2] == "`":
                cur += "`"
                i += 2
                continue
            quoted = not quoted
        elif ch == "." and not quoted:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    parts.append(cur.strip())
    return [p for p in parts if p]


def quote(name: str) -> str:
    """'cat.my schema.t' -> `cat`.`my schema`.`t` (each part quoted, backticks doubled)."""
    return ".".join("`" + p.replace("`", "``") + "`" for p in split_name(name))


def base_tables(view_text: str, schema: str, catalog: str | None = None) -> list[str]:
    sql = _STRING.sub("''", _COMMENT.sub(" ", view_text or ""))
    ctes = {split_name(m)[0].lower() for m in _CTE.findall(sql)}
    out = []
    for m in _FROM.findall(sql):
        parts = split_name(m)
        if len(parts) == 1 and parts[0].lower() in ctes:
            continue
        if len(parts) == 1:
            parts = [schema] + parts
        if catalog and len(parts) == 2:
            parts = [catalog] + parts
        name = ".".join(parts)
        if name not in out:
            out.append(name)
    return out
