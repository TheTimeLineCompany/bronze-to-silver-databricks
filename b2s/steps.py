"""The step graph (design §5) and how an output is saved with its lineage (design §7.5, §8).

Every output of a step is saved through `save_output`, which records the exact input versions (lineage) and the
fingerprint. The navigator compares them with the latest input versions to find stale outputs.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from . import versions
from .layout import Layout
from .project import settings


@dataclass(frozen=True)
class Step:
    id: str
    name: str
    runs_as: str                      # notebook | agent | tool
    how: str                          # what the person or Genie does
    outputs: tuple                    # stems relative to the app folder
    inputs: tuple = ()                # stems the outputs are made from
    optional_inputs: tuple = ()       # used when present (P4: documents OR baseline)
    needs_approval: tuple = ()        # approval points that must be approved for the input versions used
    dynamic_inputs: str | None = None  # folder whose versioned files are all inputs (P2: baseline/tables)
    version: int = 1                  # bump when the step's code changes meaningfully (marks outputs stale)
    config_keys: tuple = field(default=())


STEPS: dict[str, Step] = {s.id: s for s in [
    # V1.3 sequence kept: P1 register + bronze baseline -> P2 documents, application understanding, scope ->
    # P3 central (logical) model -> P4 STTM. V1.4 upgrades what runs inside each step.
    Step("P1", "Bronze baseline (S0-S5)", "notebook", "@p1-baseline (the agent runs nb_p1_baseline)", ("baseline/summary",),
         config_keys=("baseline",), dynamic_inputs="baseline/tables"),
    Step("P2.1", "Documents: inventory, triage, extracts", "notebook", "@p2-1-triage (the agent runs nb_p2_documents)",
         ("documents/inventory", "documents/triage")),
    Step("P2.2", "Compare documents with the baseline", "agent", "@p2-2-compare",
         ("documents/comparison",), inputs=("baseline/summary", "documents/triage")),
    Step("P2.2b", "Application understanding and models", "agent",
         "@p2-2b-understand (Glean conceptual rounds first), then @x-model-view",
         ("understanding/app_brief", "models/dependencies", "models/process", "models/conceptual"),
         optional_inputs=("baseline/summary", "documents/comparison")),
    Step("P2.3", "Scope proposal and column understanding", "tool", "python -m b2s columns <app>, then @p2-3-scope",
         ("columns/columns", "scope/scope"), inputs=("baseline/summary", "models/conceptual")),
    Step("P3", "Central model: logical silver model", "agent", "python -m b2s draft-logical <app>, then @p3-logical",
         ("models/logical",), inputs=("models/conceptual", "columns/columns", "scope/scope")),
    Step("P4.1", "STTM", "tool", "python -m b2s draft-sttm <app>, then @p4-sttm",
         ("sttm/sttm", "models/mapping"), inputs=("models/logical", "columns/columns", "scope/scope"),
         needs_approval=("CP3",)),
    # P5 build and P6 handoff (team 2 part of the V1.3 sequence). CP5 and CP6 are automatic checkpoints.
    Step("P5.1", "Code generation (PySpark notebooks)", "tool", "python -m b2s build <app>, then @p5-1-codegen",
         ("build/index",), inputs=("sttm/sttm", "models/logical"), needs_approval=("CP4",)),
    Step("P5.4", "Master build notebooks (shared masters)", "tool", "python -m b2s build <app> (masters), @p5-4-masters",
         ("build/masters",), inputs=("build/index",)),
    Step("P5.2", "QA on the dev silver schema", "notebook", "@p5-2-qa (qa-plan, then the agent runs nb_p5_qa)",
         ("qa/plan", "qa/results"), inputs=("build/index", "build/masters")),
    Step("P5.3", "Code review (new chat)", "agent", "@p5-3-code-review in a new chat",
         ("build/code_review",), inputs=("build/index",)),
    Step("P6.1", "Readiness package", "tool", "python -m b2s cp-auto <app> CP5, then python -m b2s release <app> (@p6-1-release)",
         ("release/readiness",), inputs=("build/index", "build/masters", "qa/results", "build/code_review"),
         needs_approval=("CP5",)),
]}

OUTPUT_TO_STEP = {o: s.id for s in STEPS.values() for o in s.outputs}
EXT = {"baseline/summary": "json", "documents/inventory": "json", "documents/triage": "yaml",
       "documents/comparison": "yaml", "understanding/app_brief": "md", "models/dependencies": "yaml", "models/process": "yaml",
       "models/conceptual": "yaml", "columns/columns": "yaml", "scope/scope": "yaml", "models/logical": "yaml",
       "sttm/sttm": "json", "models/mapping": "yaml", "build/index": "json", "build/masters": "json",
       "qa/plan": "json", "qa/results": "json", "build/code_review": "md", "release/readiness": "md"}


_META_RE = re.compile(r"^(?P<base>.+)\.v\d{3}\.meta\.json$")


def ext_of(stem: str) -> str:
    return EXT.get(stem, "json")


def config_hash(layout: Layout, step: Step) -> str:
    s = settings(layout)
    cfg = {k: s.get(k) for k in step.config_keys}
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:16]


def current_inputs(layout: Layout, app: str, step: Step) -> dict:
    """{stem: 'vNNN'} of the latest versions of the step's inputs that exist."""
    out = {}
    for stem in step.inputs + step.optional_inputs:
        v = versions.latest(layout.stem(app, stem), ext_of(stem))
        if v:
            out[stem] = v.tag
    if step.dynamic_inputs:
        folder = layout.stem(app, step.dynamic_inputs)
        if folder.exists():
            bases = sorted({m["base"] for f in folder.iterdir() if (m := _META_RE.match(f.name))})
            for base in bases:
                v = versions.latest(folder / base, "json")
                if v:
                    out[f"{step.dynamic_inputs}/{base}"] = v.tag
    return out


def fingerprint(layout: Layout, app: str, step: Step, inputs: dict | None = None) -> str:
    """hash(step id + step version + effective config + content hash of each input version) — design §8.1.
    (Bronze state is part of P2's own per-table fingerprints in b2s.baseline.)"""
    inputs = current_inputs(layout, app, step) if inputs is None else inputs
    parts = {"step": step.id, "step_version": step.version, "config": config_hash(layout, step), "inputs": {}}
    for stem, tag in sorted(inputs.items()):
        v = versions.get(layout.stem(app, stem), int(tag[1:]), ext_of(stem))
        parts["inputs"][stem] = v.meta.get("content_hash") if v else None
    return "fp:" + hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:24]


class MissingApproval(RuntimeError):
    pass


def save_output(layout: Layout, app: str, stem: str, content, *, reason: str, via: str | None = None,
                inputs: dict | None = None, extra_meta: dict | None = None) -> versions.Version:
    """Save an output of a step with lineage and fingerprint. Used by tools, notebooks and `b2s save` (Genie/worker).
    For P4.1, the logical model version used must be approved at CP3 (design §5.3)."""
    if stem not in OUTPUT_TO_STEP:
        raise ValueError(f"{stem} is not an output of any step; known: {sorted(OUTPUT_TO_STEP)}")
    step = STEPS[OUTPUT_TO_STEP[stem]]
    inputs = current_inputs(layout, app, step) if inputs is None else inputs
    for point in step.needs_approval:
        from .approve import approved_versions          # local import: approve imports steps
        ok = approved_versions(layout, app, point)
        for main in _point_main(layout, point):
            if main in inputs and inputs[main] not in ok.get(main, set()):
                raise MissingApproval(f"{step.id} needs {point} approval of {main}.{inputs[main]} first "
                                      f"(approved: {sorted(ok.get(main, set())) or 'none'})")
    fp = fingerprint(layout, app, step, inputs)
    return versions.save(layout, layout.stem(app, stem), ext_of(stem), content, reason=reason, step=step.id,
                         app=app, inputs=inputs, fingerprint=fp, extra_meta=extra_meta, via=via)


def _point_main(layout: Layout, point: str) -> list:
    from .project import approval_points
    return approval_points(layout)[point]["main"]
