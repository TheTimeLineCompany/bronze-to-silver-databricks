"""M1.2, M1.6, M1.7, M1.8, M1.9: navigator, scope, logical draft, approvals in the chat, STTM, handoff, Glean, plug-ins."""
import copy
import json
import shutil
import zipfile

import pytest
from openpyxl import load_workbook

from b2s import FRAMEWORK_ROOT, items, navigator, plugins, research, sttm, versions
from b2s.approve import ApprovalError, record, request
from b2s.columns import build_columns, draft_logical, set_scope
from b2s.steps import MissingApproval, save_output
from fixtures_models import ALL
from flow_helpers import APP, build_to_p5


def step(st, sid):
    return next(s for s in st["steps"] if s["step"] == sid)


def approve(layout, point, name="Jane Doe", extra=None):
    req = request(layout, APP, point)
    stmt = req["template"].replace("<your name>", name)
    if extra:
        stmt = extra(stmt)
    return req, record(layout, APP, req["id"], stmt)


@pytest.fixture
def app(project):
    build_to_p5(project)
    return project


# ----------------------------------------------------------------- navigator (M1.2)
def test_navigator_status_and_staleness(app):
    st = navigator.status(app, APP)
    assert step(st, "P2.2b")["status"] == "current"
    assert step(st, "P2.3")["status"] == "todo" and step(st, "P4.1")["status"] == "waiting"
    build_columns(app, APP)
    assert step(navigator.status(app, APP), "P2.3")["status"] == "current"
    # a new conceptual version makes P6 stale (upstream), with the reason
    conc = copy.deepcopy(ALL["conceptual"])
    conc["objects"][0]["tables"].append("yard.cntr_status")
    save_output(app, APP, "models/conceptual", conc, reason="input IN-0001", via="genie")
    s6 = step(navigator.status(app, APP), "P2.3")
    assert s6["status"] == "stale" and any("models/conceptual v001 -> v002" in w for w in s6["why"])
    plan = {p["step"]: p["status"] for p in navigator.rerun_plan(app, APP)}
    assert plan["P2.3"] == "stale" and plan["P2.1"] == "todo" and "P2.2b" not in plan
    assert "Approvals:" in navigator.render_text(navigator.status(app, APP))


# ----------------------------------------------------------------- P6 scope
def test_scope_proposal(app):
    _, sv = build_columns(app, APP)
    scope = versions.read(sv)
    t = scope["tables"]
    assert t["yard.cntr_mst"]["scope"] == "in_scope" and t["yard.mv_leg_bkp"]["scope"] == "out_of_scope"
    assert t["yard.usr_session"]["scope"] == "out_of_scope" and t["yard.contact"]["scope"] == "review"
    assert scope["columns"]["yard.cntr_mst.created_by"]["scope"] == "technical"
    assert scope["columns"]["yard.contact.email"]["privacy"] == {"class": "personal_data", "handling": None}


def test_scope_decisions_survive_rerun(app):
    build_columns(app, APP)
    set_scope(app, APP, "yard.contact", scope="out_of_scope", reason="contacts are not modelled", via="genie")
    _, sv = build_columns(app, APP, reason="rerun")
    assert versions.read(sv)["tables"]["yard.contact"]["scope"] == "out_of_scope"


# ----------------------------------------------------------------- approvals (M1.8)
def test_approval_statement_rules(app):
    build_columns(app, APP)
    with pytest.raises(ApprovalError, match="contact is still 'review'"):
        request(app, APP, "CP2")
    set_scope(app, APP, "yard.contact", scope="out_of_scope", reason="not modelled")
    req = request(app, APP, "CP2")
    assert req["template"] == ("I, <your name>, approve CP2 app_brief.v001, dependencies.v001, process.v001, "
                               "conceptual.v001, scope.v002.")
    assert "To approve, copy and complete" in req["chat_text"]
    with pytest.raises(ApprovalError, match="your name"):
        record(app, APP, req["id"], req["template"])
    with pytest.raises(ApprovalError, match="not an approval statement"):
        record(app, APP, req["id"], "looks good")
    good = req["template"].replace("<your name>", "Jane Doe")
    with pytest.raises(ApprovalError, match="file version"):
        record(app, APP, req["id"], "I, Jane Doe, approve CP2.")
    with pytest.raises(ApprovalError, match="not the version shown"):
        record(app, APP, req["id"], good.replace("scope.v002", "scope.v001 scope.v002"))
    with pytest.raises(ApprovalError, match="must name the approval point"):
        record(app, APP, req["id"], good.replace("CP2", "CP3"))
    res = record(app, APP, req["id"], good)
    apr = res["approval"]
    assert apr["name_in_statement"] == "Jane Doe" and apr["how"] == "chat" and apr["approval_mode"] == "self"
    assert apr["statement"] == good
    with pytest.raises(ApprovalError, match="already approved"):
        record(app, APP, req["id"], good)


def test_request_goes_stale_when_file_changes(app):
    build_columns(app, APP)
    set_scope(app, APP, "yard.contact", scope="out_of_scope", reason="x")
    req = request(app, APP, "CP2")
    set_scope(app, APP, "yard.mv_plan", scope="in_scope", reason="confirmed")       # new scope version
    with pytest.raises(ApprovalError, match="changed after the request"):
        record(app, APP, req["id"], req["template"].replace("<your name>", "Jane Doe"))


def _to_ap4(app):
    build_columns(app, APP)
    set_scope(app, APP, "yard.contact", scope="out_of_scope", reason="not modelled")
    approve(app, "CP2")
    return draft_logical(app, APP)


def test_chain_rule_and_ap4_blocks_p8(app):
    build_columns(app, APP)
    set_scope(app, APP, "yard.contact", scope="out_of_scope", reason="not modelled")
    lv = draft_logical(app, APP)
    with pytest.raises(ApprovalError, match="chain"):
        request(app, APP, "CP3")
    approve(app, "CP2")
    lv = draft_logical(app, APP)                    # same content -> same version, fingerprint refreshed
    assert step(navigator.status(app, APP), "P4.1")["status"] == "blocked"
    with pytest.raises(MissingApproval):
        sttm.draft(app, APP)
    req, res = approve(app, "CP3")
    assert req["template"] == f"I, <your name>, approve CP3 {lv.label}."
    assert lv.companion("mmd").exists() and lv.companion("html").exists()      # viewer written for the request
    assert step(navigator.status(app, APP), "P4.1")["status"] == "todo"


def test_logical_draft_is_valid_and_named_from_ontology(app):
    lv = _to_ap4(app)
    from b2s import models
    from b2s.project import ontology
    lm = versions.read(lv)
    assert models.validate("logical", lm, ontology(app, "business")) == []
    leg = next(t for t in lm["tables"] if t["name"] == "slv_shipment_leg")
    assert leg["business_key"] == ["plan_id", "leg_no"]
    names = {c["name"] for c in leg["columns"]}
    assert {"container_no", "container_sk", "shipment_sk", "moved_at"} <= names


def test_sttm_handoff_end_to_end(app):
    _to_ap4(app)
    approve(app, "CP3")
    sv = sttm.draft(app, APP)
    doc = versions.read(sv)
    assert sttm.validate(app, APP, doc) == []
    leg = next(t for t in doc["tables"] if t["target_table"] == "slv_shipment_leg")
    fk = next(c for c in leg["columns"] if c["target_column"] == "container_sk")
    assert fk["rule"] == "lookup_fk" and fk["fk"]["lookup_on"] == ["yard.mv_leg.cntr_no"]
    unclear = next(c for c in leg["columns"] if c["target_column"] == "xq_flg")
    assert unclear["status"] == "unknown" and unclear["question"].startswith("Q-")
    n_q = len(items.list_items(app, APP, "question"))
    sttm.draft(app, APP)                                                    # rerun: no duplicate questions
    assert len(items.list_items(app, APP, "question")) == n_q
    ex = plugins.export_sttm(app, APP, sv)
    assert ex["plugin"]["origin"] == "core" and load_workbook(ex["path"]).sheetnames == ["Tables", "Mapping", "Open items"]
    mapping = versions.latest(app.stem(APP, "models/mapping"))
    assert mapping and any(l["bronze_columns"] == ["cntr_no"] for l in versions.read(mapping)["links"])

    req = request(app, APP, "CP4")
    q_new = unclear["question"]
    assert f"{q_new}: must answer" in req["template"] and "A-0001: accept" in req["template"]
    # the worker accepts the older questions' assumptions; the new question must be answered
    stmt = req["template"].replace("<your name>", "Jane Doe")
    for q in ("Q-0001", "Q-0002", "Q-0003", "Q-0004"):
        stmt = stmt.replace(f"{q}: must answer", f"{q}: accept")
    res = record(app, APP, req["id"], stmt)
    assert res["handoff"] is None and res["waiting_for"] == [q_new]
    # answer the question -> new CP4 -> handoff
    items.update(app, APP, q_new, {"status": "answered", "answer": "flag for exceptions"}, reason="client answer")
    req2 = request(app, APP, "CP4")
    assert "Q-0001: accept" in req2["template"] and q_new not in req2["template"]   # previous decisions carried over
    res2 = record(app, APP, req2["id"], req2["template"].replace("<your name>", "Jane Doe"))
    assert res2["handoff"], res2
    folder = app.root / res2["handoff"]
    readme = (folder / "README.md").read_text(encoding="utf-8")
    assert "Self-approved" in readme and "I, Jane Doe, approve CP4 sttm.v001." in readme
    assert "known" in readme and "assumed" in readme and "made by Genie" in readme
    assert (folder / f"{sv.label}.xlsx").exists() and (folder / "manifest.json").exists()


def test_reapproval_after_new_version(app):
    lv = _to_ap4(app)
    approve(app, "CP3")
    lm = versions.read(lv)
    lm["tables"][0]["grain"] = "One row per container."
    save_output(app, APP, "models/logical", lm, reason="worker change via Genie", via="genie")
    ap4 = next(a for a in navigator.approval_status(app, APP) if a["point"] == "CP3")
    assert ap4["state"] == "re-approval needed" and ap4["files"][0]["approved"] == ["v001"]
    assert step(navigator.status(app, APP), "P4.1")["status"] == "blocked"
    req = request(app, APP, "CP3")
    assert "logical.v002" in req["template"] and req["changes_since_last_approval"]


def test_missing_item_references_block_approval(project):
    from flow_helpers import build_to_p5
    from b2s.project import register_app
    register_app(project, APP, "x", ["yard"])
    from flow_helpers import write_baseline
    write_baseline(project)
    save_output(project, APP, "models/process", ALL["process"], reason="first")
    save_output(project, APP, "models/conceptual", ALL["conceptual"], reason="first")
    save_output(project, APP, "understanding/app_brief", "# x\n", reason="first")
    save_output(project, APP, "models/dependencies", {**ALL["dependencies"], "app": APP}, reason="first")
    build_columns(project, APP)
    with pytest.raises(ApprovalError, match="(?s)refers to items that do not exist: .*A-0001"):
        request(project, APP, "CP2")


def test_ap1_open_point_decisions(app):
    op, _ = items.upsert_derived(app, APP, "open_point", {"point": "copy_of", "tables": ["yard.mv_leg_bkp"]},
                                 {"point": "copy_of", "tables": ["yard.mv_leg_bkp", "yard.mv_leg"], "detail": {}})
    req = request(app, APP, "CP1")
    assert f"{op['id']}: accept" in req["template"]
    record(app, APP, req["id"], req["template"].replace("<your name>", "Jane Doe").replace(": accept", ": defer"))
    assert items.get(app, APP, op["id"])["status"] == "deferred"


# ----------------------------------------------------------------- Glean (M1.6)
def test_glean_conceptual_first_and_raw_first(app):
    build_columns(app, APP)
    with pytest.raises(research.ResearchError, match="after a conceptual round"):
        research.new_round(app, APP, "column", [{"topic": "x", "question": "?", "about": "yard.mv_leg.xq_flg"}])
    r = research.new_round(app, APP, "conceptual", [{"topic": "purpose", "question": "What does the yard app do?"}])
    assert json.loads(research.request_text(app, APP, r["id"]))["topics"][0]["n"] == 1
    research.mark_sent(app, APP, r["id"], "paste")
    with pytest.raises(research.ResearchError, match="save the reply first"):
        research.parse(app, APP, r["id"])
    with pytest.raises(research.ResearchError, match="empty"):
        research.record_raw(app, APP, r["id"], "   ")
    research.record_raw(app, APP, r["id"], 'Here: {"n": 1, "answer": "Plans container moves", "sources": ["Overview"]}')
    parsed = research.parse(app, APP, r["id"])
    assert parsed["answers"][0]["answer"] == "Plans container moves"
    ids = research.integrate(app, APP, r["id"], [{"statement": "The app plans container moves.", "cites": "IF-0001"},
                                                  {"statement": "It feeds the TOS.", "confidence": "high"}])
    e1, e2 = (items.get(app, APP, i) for i in ids)
    assert e1["root_source"] == "IF-0001" and e2["root_source"] == f"glean:{r['id']}" and e2["confidence"] == "medium"
    with pytest.raises(research.ResearchError, match="marks unclear"):
        research.new_round(app, APP, "column", [{"topic": "x", "question": "?", "about": "yard.mv_leg.plan_id"}])
    c = research.new_round(app, APP, "column", [{"topic": "flag", "question": "What is XQ_FLG?", "about": "yard.mv_leg.xq_flg"}])
    assert c["type"] == "column"
    research.close(app, APP, r["id"])
    assert research.reopen(app, APP, r["id"], reason="new document", extra_budget=3)["budget"] == 8


# ----------------------------------------------------------------- plug-ins (M1.9)
def test_plugin_install_activate_package(project, tmp_path):
    src = tmp_path / "my_export"
    shutil.copytree(FRAMEWORK_ROOT / "plugins" / "sttm_export_excel_default", src)
    man = (src / "plugin.yaml").read_text(encoding="utf-8").replace("sttm_export_excel_default", "client_template_export") \
        .replace("origin: core", "origin: project").replace("1.0.0", "0.1.0")
    (src / "plugin.yaml").write_text(man, encoding="utf-8")
    info = plugins.install(project, src)
    assert info["contract_test"] == "passed" and not info["active"]
    assert plugins.resolve(project, "sttm_export_excel")[1]["origin"] == "core"        # not active before approval
    with pytest.raises(ApprovalError):
        plugins.activate(project, "client_template_export", "I, Jane Doe, approve PLUGIN.")
    plugins.activate(project, "client_template_export", "I, Jane Doe, approve PLUGIN client_template_export.v0.1.0.")
    fn, rinfo = plugins.resolve(project, "sttm_export_excel")
    assert rinfo == {"name": "client_template_export", "version": "0.1.0", "origin": "project", "overrides_core": True}
    z = plugins.package(project, "client_template_export", "Exports the client STTM template.")
    names = zipfile.ZipFile(z).namelist()
    assert "client_template_export/CHANGE_NOTE.md" in names and "client_template_export/contract_test.json" in names
    assert not any("activation" in n for n in names)


def test_plugin_contract_test_catches_lossy_export(project, tmp_path):
    src = tmp_path / "bad"
    shutil.copytree(FRAMEWORK_ROOT / "plugins" / "sttm_export_excel_default", src)
    (src / "plugin.yaml").write_text((src / "plugin.yaml").read_text(encoding="utf-8").replace(
        "sttm_export_excel_default", "bad_export"), encoding="utf-8")
    (src / "adapter.py").write_text("from openpyxl import Workbook\n"
                                    "def export(sttm, out):\n    Workbook().save(out)\n", encoding="utf-8")
    with pytest.raises(plugins.PluginError, match="contract test failed"):
        plugins.install(project, src)
