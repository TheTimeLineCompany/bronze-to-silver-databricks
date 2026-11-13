"""P2 bronze baseline (design §5, §13, §14): profile, classify, find keys, find copies and empty tables, open points.

Runs in a notebook a person starts (no long work inside Genie). Resumable: a table whose fingerprint did not change
is skipped; a time budget stops the run early and the summary says partial. Values are redacted BEFORE any write.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

from .. import FRAMEWORK_VERSION, items, versions
from ..layout import Layout
from ..project import app_config, ontology, settings
from ..store import emit_event, sha256_bytes
from .profile import profile_columns
from .rules_v11 import (DESCISH, KEYISH, SENSITIVE_CLASSES, STAGING, classify_column, find_keys, is_technical,
                        log_name_count, tokens)

ENGINE_VERSION = "p2-1"
DEFAULT_PATTERNS = {
    "cdc": [r"^_?load_?ver(sion)?$", r"^_?cdc_", r"^op_?type$", r"^_?commit_?version$", r"^_?change_?seq(uence)?$"],
    "audit": [r"^(created|updated|modified|changed|inserted|deleted)_?(by|at|on|ts|date|time|user)$"],
}
REDACT_ALSO = {"audit_metadata"}           # who/when values (user names) are not written either


class RedactionError(RuntimeError):
    pass


def _sha(obj) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _patterns(layout: Layout) -> dict:
    info = ontology(layout, "information")
    pats = dict(DEFAULT_PATTERNS)
    pats.update((info.get("column_patterns") or {}))
    return {k: [re.compile(p, re.I) for p in v] for k, v in pats.items()}


def _desc_like(col: str) -> bool:
    t = tokens(col)
    return bool(t & DESCISH) or col.lower().endswith(("_nm", "_name", "_desc", "_text"))


def key_candidates(profiles: list, classes: dict, pats: dict, budget: dict) -> tuple[list, dict, dict]:
    """Apply the key-search rules in order. Returns (candidate profiles, removed_by_rule, allowed_by_rule)."""
    removed: dict[str, list] = {}
    allowed: dict[str, list] = {}

    def drop(rule, col):
        removed.setdefault(rule, []).append(col)

    keep = []
    for p in profiles:
        c = p["column"]
        if is_technical(c):
            drop("TECHNICAL", c)
        elif any(rx.search(c) for rx in pats.get("cdc", [])):
            drop("CDC_LOAD_VERSION", c)
        elif any(rx.search(c) for rx in pats.get("audit", [])) or classes.get(c) == "audit_metadata":
            drop("AUDIT", c)
        elif p.get("family") == "num":
            drop("MEASURE", c)
        elif (p.get("null_pct") or 0) > budget.get("key_max_null_pct", 1.0):
            drop("NULLS", c)
        elif (p.get("approx_distinct") or 0) <= 1:
            drop("CONSTANT", c)
        elif p.get("family") == "str" and (p.get("avg_len") or 0) > 60:
            drop("LONG_TEXT", c)
        else:
            keep.append(p)
    has_code = any(tokens(p["column"]) & KEYISH and not _desc_like(p["column"]) for p in keep)
    out = []
    for p in keep:
        if _desc_like(p["column"]):
            if has_code:
                drop("DESC_NOT_KEY", p["column"])
                continue
            allowed.setdefault("NM_FALLBACK", []).append(p["column"])
        out.append(p)
    return out, removed, allowed


def redact(profile: dict, low_card_max: int) -> dict:
    """R-01 / design §14: sensitive columns keep only shapes and ratios; top values only for low-cardinality
    code-like business attributes, never for keys."""
    keyset = set(profile.get("key") or [])
    for p in profile["columns"]:
        cls = p.get("column_class")
        if cls in SENSITIVE_CLASSES or cls in REDACT_ALSO:
            p["min"] = p["max"] = None
            p["topk"] = []
            p["redacted"] = cls
            continue
        if not (cls == "business_attribute" and (p.get("approx_distinct") or 0) <= low_card_max
                and p["column"] not in keyset):
            p["topk"] = []
    return profile


def profile_table(reader, table: str, cfg: dict, pats: dict, external_cols: list | None = None) -> dict:
    """external_cols: column profiles from an integrated profiler plug-in (slot `profiler`, converted by its adapter).
    Key search, classification and redaction still run here, so the framework rules hold for any profiler."""
    cols = reader.columns(table)
    rows_total = reader.row_count(table)
    if external_cols is not None:
        sample = []
        profs = [dict(c) for c in external_cols]
    else:
        sample = reader.sample(table, int(cfg.get("sample_rows", 5_000_000)), int(cfg.get("seed", 42))) if rows_total else []
        profs = profile_columns(sample, cols, topk=int(cfg.get("topk", 20)))
    n_log = log_name_count(profs)
    pre = {p["column"]: classify_column(p, table_log_names=n_log)["column_class"] for p in profs}
    budget = {"sample_rows": max(1, len(sample) if external_cols is None else rows_total), "max_key_size": cfg.get("max_key_size", 4),
              "key_pool_size": cfg.get("key_pool_size", 8), "max_key_checks": cfg.get("max_key_checks", 25),
              "key_max_null_pct": cfg.get("key_max_null_pct", 1.0)}
    out = {"table": table, "row_count": rows_total, "sample_rows": len(sample) if external_cols is None else None,
           "profiler": "external" if external_cols is not None else "core", "columns": profs,
           "key": None, "keys": [], "key_result": None, "key_detail": {}, "removed_by_rule": {}, "allowed_by_rule": {},
           "content_hash": reader.content_hash(table) if rows_total else None, "state": reader.state(table)}
    if not rows_total:
        out["key_result"] = "empty"
    else:
        cands, removed, allowed = key_candidates(profs, pre, pats, budget)
        out["removed_by_rule"], out["allowed_by_rule"] = removed, allowed
        res = find_keys(cands, rows_total, lambda cs: reader.all_rows_unique(table, cs), budget) if cands else \
            {"keys": [], "checks": 0, "best": None}
        out["key_detail"]["checks"] = res["checks"]
        if res["best"]:
            out.update(key=res["best"], keys=res["keys"], key_result="key")
        else:
            limits = {k: budget[k] for k in ("max_key_size", "key_pool_size", "max_key_checks")}
            names = [p["column"] for p in cands]
            if names and reader.all_rows_unique(table, names):
                out["key_result"] = "no_key_within_limits"
                out["key_detail"].update(limits=limits, unique_over=names)
            else:
                near_max = int(cfg.get("near_key_max_duplicates", 10))
                best = None
                for p in sorted(cands, key=lambda p: -(p.get("approx_distinct") or 0))[:5]:
                    d = reader.duplicate_count(table, [p["column"]])
                    if d <= near_max and (best is None or d < best[1]):
                        best = ([p["column"]], d)
                if best:
                    out.update(key=best[0], key_result="near_key")
                    out["key_detail"].update(duplicates=best[1])
                else:
                    out["key_result"] = "no_key"
                    out["key_detail"].update(limits=limits)
    keyset = set(out["key"] or []) if out["key_result"] == "key" else set()
    cdc = set(out["removed_by_rule"].get("CDC_LOAD_VERSION", []))
    for p in profs:
        c = classify_column(p, key_cols=keyset, table_log_names=n_log)
        p["column_class"], p["use"], p["class_reasons"] = c["column_class"], c["use"], c["reasons"]
        if p["column"] in cdc:
            p["column_class"], p["use"], p["class_reasons"] = "cdc_metadata", "technical_only", "load version (CDC) column"
    return out


def run(layout: Layout, app: str, reader, *, time_budget_s: float | None = None, fresh: bool = False,
        redact_off_reason: str | None = None, external_profiles: dict | None = None,
        external_info: dict | None = None) -> dict:
    """external_profiles: {table: [column profiles]} collected from a profiler plug-in run (b2s.plugins.collect);
    external_info: the plug-in name and version (part of the fingerprint and recorded on each table).
    P1 for one application. Returns the summary (also saved as baseline/summary.vNNN.json)."""
    st = settings(layout)
    cfg = dict(st.get("baseline") or {})
    if not st.get("redact_values", True):
        if not redact_off_reason:
            raise RedactionError("redact_values is off in project.yaml: give redact_off_reason (it is logged)")
        emit_event(layout, "redaction_off", app=app, step="P1", note=redact_off_reason)
    do_redact = st.get("redact_values", True)
    acfg = app_config(layout, app)
    schemas = list(acfg.get("schemas") or []) + list(acfg.get("lookup_schemas") or [])
    tables = reader.list_tables(schemas)[: int(st.get("max_tables", 1000))]
    budget_s = time_budget_s if time_budget_s is not None else float(st.get("time_budget_minutes", 25)) * 60
    pats = _patterns(layout)
    pat_src = {k: [p.pattern for p in v] for k, v in pats.items()}
    t0 = time.monotonic()
    done, skipped, created, remaining = {}, [], [], []
    for i, t in enumerate(tables):
        if i > 0 and time.monotonic() - t0 >= budget_s:
            remaining = tables[i:]
            break
        state = reader.state(t)
        state_hash = _sha(state)
        fp = _sha({"framework": FRAMEWORK_VERSION, "engine": ENGINE_VERSION, "settings": cfg, "patterns": pat_src,
                   "redact": do_redact, "state": state, "profiler": external_info if external_profiles else None,
                   "external": _sha((external_profiles or {}).get(t)) if external_profiles else None})
        stem = layout.stem(app, f"baseline/tables/{t}")
        cur = versions.latest(stem, "json")
        if cur and cur.meta.get("fingerprint") == fp and not fresh:
            done[t] = (versions.read(cur), cur)
            skipped.append(t)
            continue
        prof = profile_table(reader, t, cfg, pats, (external_profiles or {}).get(t))
        if external_profiles and t in external_profiles:
            prof["profiler_plugin"] = external_info
        if do_redact:
            redact(prof, int(cfg.get("low_cardinality_max", 50)))
        reason = "fresh_run" if fresh else ("rerun" if cur else "first")
        v = versions.save(layout, stem, "json", prof, reason=reason, step="P1", app=app,
                          inputs={f"bronze:{t}": state_hash}, fingerprint=fp)
        if v.created:
            created.append(t)
        done[t] = (prof, v)

    # copies: same columns and same content; the table without a staging-like name is the original
    groups: dict = {}
    for t, (p, _) in done.items():
        if p["row_count"]:
            groups.setdefault((tuple(c["column"] for c in p["columns"]), p["content_hash"]), []).append(t)
    copy_of = {}
    for ts in groups.values():
        if len(ts) > 1:
            ts = sorted(ts, key=lambda x: (bool(STAGING.search(x.split(".")[1])), x))
            for c in ts[1:]:
                copy_of[c] = ts[0]

    entries, ops = [], []
    for t in tables:
        if t not in done:
            continue
        p, v = done[t]
        pts = []
        kr = p["key_result"]
        if kr in ("near_key", "no_key_within_limits", "no_key", "empty"):
            pts.append((kr, [t], {"key": p.get("key"), **p.get("key_detail", {})}))
        if t in copy_of:
            pts.append(("copy_of", [t, copy_of[t]], {"original": copy_of[t]}))
        ids = []
        for point, tabs, detail in pts:
            it, _ = items.upsert_derived(layout, app, "open_point", {"point": point, "tables": tabs},
                                         {"point": point, "tables": tabs, "detail": detail}, step="P1")
            ids.append(it["id"])
        ops += ids
        entries.append({"table": t, "kind": "view" if p["state"].get("view_text") else "table",
                        "row_count": p["row_count"], "n_columns": len(p["columns"]), "key": p.get("key"),
                        "key_result": kr, "copy_of": copy_of.get(t), "empty": kr == "empty",
                        "version": v.label if hasattr(v, "label") else None, "open_points": ids,
                        "sensitive_columns": [c["column"] for c in p["columns"] if c.get("redacted")]})
    summary = {"app": app, "engine": ENGINE_VERSION, "partial": bool(remaining), "remaining": remaining,
               "tables": entries, "open_points": sorted(set(ops)),
               "bronze_state": _sha({t: done[t][0]["state"] for t in done}),
               "counts": {"tables": len(entries), "key": sum(e["key_result"] == "key" for e in entries),
                          "open_points": len(set(ops))}}
    from ..steps import save_output       # lineage + the step fingerprint the navigator recomputes
    sv = save_output(layout, app, "baseline/summary", summary, reason="baseline",
                     inputs={f"baseline/tables/{t}": done[t][1].tag for t in done})
    emit_event(layout, "baseline_run", app=app, step="P1", outputs={layout.rel(sv.path): sv.meta.get("content_hash")},
               note=f"{len(created)} new, {len(skipped)} unchanged, {len(remaining)} remaining",
               extra={"created": created, "skipped": skipped, "remaining": remaining, "fresh": fresh})
    summary["_version"] = sv.label
    return summary


__all__ = ["run", "profile_table", "redact", "key_candidates", "RedactionError", "ENGINE_VERSION", "sha256_bytes"]
