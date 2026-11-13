"""Build a complete demo project for the fake application S90_yardops, from bronze to the handoff.

    python -m b2s.demo.walkthrough <empty folder>

Genie's judgement steps (app brief, models) are simulated with the fixture models; approvals use statements as a
worker would type them in the chat. Open <folder>/proj/apps/S90_yardops/models/*.html to see the viewer.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

from .. import baseline, documents, navigator, plugins, sttm, versions
from ..approve import record, request
from ..baseline.readers import LocalCsvReader
from ..columns import build_columns, draft_logical, set_scope
from ..layout import Layout
from ..project import init_project
from ..steps import save_output
from . import fake_app

APP = "S90_yardops"
WORKER = "Demo Worker"


def _approve(layout, point, edit=None):
    req = request(layout, APP, point)
    stmt = req["template"].replace("<your name>", WORKER)
    print(f"\n{req['chat_text']}\n\n>>> worker types:\n{stmt}")
    res = record(layout, APP, req["id"], edit(stmt) if edit else stmt)
    print(f"<<< recorded {res['approval']['id']}")
    return res


def _models():
    from .example_models import ALL
    return ALL


def run(out: str | Path) -> Path:
    out = Path(out)
    Layout(out)                                           # allow writes under the demo folder
    layout = init_project(out / "proj", "Demo project")
    fake = fake_app.make_fake_app(out / "fake")
    fake_app.install(layout, fake)
    baseline.run(layout, APP, LocalCsvReader(fake["bronze_root"]))
    documents.inventory(layout, APP)
    documents.triage(layout, APP)
    documents.extract(layout, APP)
    _approve(layout, "CP1")
    ALL = _models()
    from .. import items                                   # the A-/Q- items the fixture models refer to
    for i in range(5):
        items.create(layout, APP, "assumption", {"statement": f"Demo assumption {i + 1}"}, via="genie")
    for i in range(4):
        items.create(layout, APP, "question", {"text": f"Demo question {i + 1}?"}, via="genie")
    save_output(layout, APP, "documents/comparison", {"facts": [], "documents_only": [], "bronze_only": []},
                reason="first", via="genie")
    save_output(layout, APP, "understanding/app_brief", "# Yard operations\nPlans and moves containers in the yard.\n",
                reason="first", via="genie")
    deps = copy.deepcopy(ALL["dependencies"])
    deps["app"] = APP
    from .. import viewer
    for stem, m in (("models/dependencies", deps), ("models/process", ALL["process"]),
                    ("models/conceptual", ALL["conceptual"])):
        v = save_output(layout, APP, stem, m, reason="first", via="genie")
        viewer.write_views(v, stem.split("/")[1], m)
    build_columns(layout, APP)
    scope = versions.read(versions.latest(layout.stem(APP, "scope/scope"), "yaml"))
    for t, s in scope["tables"].items():
        if s["scope"] == "review":
            set_scope(layout, APP, t, scope="out_of_scope", reason="worker in chat: not modelled", via="genie")
    scope = versions.read(versions.latest(layout.stem(APP, "scope/scope"), "yaml"))
    for c, s in scope["columns"].items():
        if scope["tables"][c.rsplit(".", 1)[0]]["scope"] == "in_scope" and s["scope"] == "review":
            set_scope(layout, APP, c, scope="out_of_scope", reason="worker in chat: free text", via="genie")
    _approve(layout, "CP2")
    draft_logical(layout, APP)
    _approve(layout, "CP3")
    sv = sttm.draft(layout, APP)
    plugins.export_sttm(layout, APP, sv)
    mv = versions.latest(layout.stem(APP, "models/mapping"), "yaml")
    viewer.write_views(mv, "mapping", versions.read(mv))
    res = _approve(layout, "CP4", edit=lambda s: s.replace(": must answer", ": accept"))
    print("\n" + navigator.render_text(navigator.status(layout, APP)))
    print(f"\nHandoff: {layout.root / res['handoff']}")
    return layout.root


if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) != 2:
        sys.exit("usage: python -m b2s.demo.walkthrough <empty folder>")
    run(sys.argv[1])
