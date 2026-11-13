"""P5.2 QA: plan (which checks of standards/qa_checklist.md apply to which dev silver table) and results.

The plan is made here (pure Python). The checks run in the notebook nb_p5_qa on the DEV silver schema (Spark) with
lib/qa_checks.py, which saves the results through record_results. CP5 reads qa_problems.
"""
from __future__ import annotations

from .. import versions
from ..layout import Layout
from ..project import ontology
from ..steps import save_output
from .codegen import build_settings
from .spec import approved_sttm, runtime_tables


def make_plan(layout: Layout, app: str, *, reason: str = "plan (P5.2)") -> versions.Version:
    from lib.qa_rules import required_checks
    from lib.survivorship import master_spec, staging_spec, staging_table
    b = build_settings(layout)
    prefix = f"{b['dev_catalog']}.{b['dev_silver_schema']}"
    sv = approved_sttm(layout, app)
    specs = runtime_tables(layout, app, versions.read(sv))
    entries = []
    for t in specs:
        if t["target_kind"] == "master":
            spec, name = staging_spec({**t, "columns": [dict(c) for c in t["columns"]]}), staging_table(t["target_table"], app)
        else:
            spec, name = t, t["target_table"]
        entries.append({"name": name, "fqn": f"{prefix}.{name}", "spec": spec, "required": required_checks(spec)})
    mv = versions.latest(layout.stem(app, "build/masters"), "json")
    ents = {e["name"]: e for e in (ontology(layout, "entities").get("entities") or [])}
    for entity, m in (versions.read(mv)["masters"] if mv else {}).items():
        feeding = [t for t in specs if t.get("conformed_entity") == entity]
        spec = master_spec(ents[entity], feeding)
        entries.append({"name": m["table"], "fqn": f"{prefix}.{m['table']}", "spec": spec,
                        "required": required_checks(spec), "master": True})
    return save_output(layout, app, "qa/plan", {"app": app, "silver_prefix": prefix, "tables": entries}, reason=reason)


def record_results(layout: Layout, app: str, results: list[dict], *, via: str | None = None) -> versions.Version:
    """Save QA results (from nb_p5_qa) with coverage against the plan. Every required check must be present and pass."""
    from lib.qa_rules import coverage
    plan = versions.latest(layout.stem(app, "qa/plan"), "json")
    if not plan:
        raise FileNotFoundError("no QA plan: run python -m b2s qa-plan <app> first")
    p = versions.read(plan)
    cov = coverage({}, results, pairs=[(e["name"], e["spec"]) for e in p["tables"]])
    ok = all(not c["missing"] and not c["not_passing"] for c in cov.values()) and all(r.get("status") == "pass" for r in results)
    return save_output(layout, app, "qa/results", {"app": app, "plan_version": plan.tag, "all_passed": ok,
                                                   "coverage": cov, "results": results},
                       reason="QA run (nb_p5_qa)", via=via)


def qa_problems(layout: Layout, app: str) -> list[str]:
    v = versions.latest(layout.stem(app, "qa/results"), "json")
    if not v:
        return ["no QA results: run notebook nb_p5_qa"]
    r = versions.read(v)
    plan = versions.latest(layout.stem(app, "qa/plan"), "json")
    out = []
    if plan and r.get("plan_version") != plan.tag:
        out.append(f"QA results are for {r.get('plan_version')}, the plan is {plan.label}: run nb_p5_qa again")
    for name, c in (r.get("coverage") or {}).items():
        if c["missing"]:
            out.append(f"QA {name}: missing {', '.join(c['missing'])}")
        if c["not_passing"]:
            out.append(f"QA {name}: not passing {', '.join(c['not_passing'])}")
    if not r.get("all_passed") and not out:
        out.append("QA did not pass")
    return out
