"""End to end on the fake application: P2 engine -> P3 documents -> P4/P5 (Genie simulated) -> P6 -> approvals in the
chat -> P3 -> CP3 -> P4 -> CP4 -> handoff. Also: no sensitive value anywhere outside the inbox."""
import copy

from b2s import baseline, documents, navigator, plugins, sttm, versions
from b2s.approve import record, request
from b2s.baseline.readers import LocalCsvReader
from b2s.columns import build_columns, draft_logical, set_scope
from b2s.demo import fake_app
from b2s.steps import save_output
from fixtures_models import ALL

APP = "S90_yardops"


def _approve(layout, point, edit=None):
    req = request(layout, APP, point)
    stmt = req["template"].replace("<your name>", "Jane Doe")
    if edit:
        stmt = edit(stmt)
    return record(layout, APP, req["id"], stmt)


def test_fake_app_end_to_end(project, tmp_path):
    fake = fake_app.make_fake_app(tmp_path / "fake")
    fake_app.install(project, fake)
    # P1 + P2.1 (notebooks in the workspace)
    summary = baseline.run(project, APP, LocalCsvReader(fake["bronze_root"]))
    assert not summary["partial"]
    documents.inventory(project, APP)
    documents.triage(project, APP)
    documents.extract(project, APP)
    _approve(project, "CP1")                                       # open points accepted as pre-filled
    from b2s import items
    for i in range(5):
        items.create(project, APP, "assumption", {"statement": f"assumption {i + 1}"}, via="genie")
    for i in range(4):
        items.create(project, APP, "question", {"text": f"question {i + 1}?"}, via="genie")
    # P2.2 + P2.2b (Genie, saved with lineage)
    save_output(project, APP, "documents/comparison", {"facts": [], "documents_only": [], "bronze_only": []},
                reason="first", via="genie")
    save_output(project, APP, "understanding/app_brief", "# Yard operations\nPlans and moves containers.\n",
                reason="first", via="genie")
    deps = copy.deepcopy(ALL["dependencies"])
    deps["app"] = APP
    for stem, m in (("models/dependencies", deps), ("models/process", ALL["process"]),
                    ("models/conceptual", ALL["conceptual"])):
        save_output(project, APP, stem, m, reason="first", via="genie")
    # P2.3 + decisions given in the chat
    _, sv = build_columns(project, APP)
    scope = versions.read(sv)
    for t, s in scope["tables"].items():
        if s["scope"] == "review":
            set_scope(project, APP, t, scope="out_of_scope", reason="not in the conceptual model", via="genie")
    scope = versions.read(versions.latest(project.stem(APP, "scope/scope"), "yaml"))
    for c, s in scope["columns"].items():
        if scope["tables"][c.rsplit(".", 1)[0]]["scope"] == "in_scope" and s["scope"] == "review":
            set_scope(project, APP, c, scope="out_of_scope", reason="free text", via="genie")
    _approve(project, "CP2")
    # P3 -> CP3 -> P4 -> CP4
    draft_logical(project, APP)
    _approve(project, "CP3")
    sv = sttm.draft(project, APP)
    assert sttm.validate(project, APP, versions.read(sv)) == []
    plugins.export_sttm(project, APP, sv)
    res = _approve(project, "CP4", edit=lambda s: s.replace(": must answer", ": accept"))
    assert res["handoff"], res.get("waiting_for")
    st = navigator.status(project, APP)
    assert {a["point"]: a["state"] for a in st["approvals"]}["CP4"] == "approved"
    assert all(s["status"] == "current" for s in st["steps"] if s["step"][:2] in ("P1", "P2", "P3", "P4")), \
        navigator.render_text(st)

    # R-01: no sensitive value reaches any file outside the inbox (incl. extracts, items, events, views, handoff)
    leaks = []
    for f in project.root.rglob("*"):
        if not f.is_file() or "inbox" in f.relative_to(project.root).parts or f.suffix == ".xlsx":
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        leaks += [(f.name, v) for v in fake["sensitive_values"] if v in text]
    assert leaks == []
