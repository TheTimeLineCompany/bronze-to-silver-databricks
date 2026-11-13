"""P5 build (codegen, masters, QA, review), CP5 automatic, P6.1 readiness, CP6 automatic, H2 — on the fake app."""
import ast
import copy

import pytest
import yaml

from b2s import baseline, documents, items, navigator, sttm, versions
from b2s.approve import ApprovalError, record, request, run_automatic
from b2s.baseline.readers import LocalCsvReader
from b2s.build import codegen, generate, generate_masters, make_plan, record_results, save_notebook
from b2s.columns import build_columns, draft_logical, set_scope
from b2s.demo import fake_app
from b2s.release import readiness
from b2s.steps import MissingApproval, save_output
from fixtures_models import ALL

APP = "S90_yardops"
BANNED = {"sparkContext", "rdd", "_jvm", "_jsc"}


def _approve(layout, point, edit=None):
    req = request(layout, APP, point)
    stmt = req["template"].replace("<your name>", "Jane Doe")
    return record(layout, APP, req["id"], edit(stmt) if edit else stmt)


def _to_cp4(project, tmp_path):
    fake = fake_app.make_fake_app(tmp_path / "fake")
    fake_app.install(project, fake)
    baseline.run(project, APP, LocalCsvReader(fake["bronze_root"]))
    documents.inventory(project, APP)
    documents.triage(project, APP)
    _approve(project, "CP1")
    for i in range(5):
        items.create(project, APP, "assumption", {"statement": f"assumption {i + 1}"}, via="genie")
    for i in range(4):
        items.create(project, APP, "question", {"text": f"question {i + 1}?"}, via="genie")
    save_output(project, APP, "documents/comparison", {"facts": []}, reason="first", via="genie")
    save_output(project, APP, "understanding/app_brief", "# Yard\n", reason="first", via="genie")
    deps = copy.deepcopy(ALL["dependencies"])
    deps["app"] = APP
    for stem, m in (("models/dependencies", deps), ("models/process", ALL["process"]), ("models/conceptual", ALL["conceptual"])):
        save_output(project, APP, stem, m, reason="first", via="genie")
    _, sv = build_columns(project, APP)
    for t, s in versions.read(sv)["tables"].items():
        if s["scope"] == "review":
            set_scope(project, APP, t, scope="out_of_scope", reason="x")
    scope = versions.read(versions.latest(project.stem(APP, "scope/scope"), "yaml"))
    for c, s in scope["columns"].items():
        if scope["tables"][c.rsplit(".", 1)[0]]["scope"] == "in_scope" and s["scope"] == "review":
            set_scope(project, APP, c, scope="out_of_scope", reason="x")
    _approve(project, "CP2")
    draft_logical(project, APP)
    _approve(project, "CP3")
    sttm.draft(project, APP)
    _approve(project, "CP4", edit=lambda s: s.replace(": must answer", ": accept"))


def _add_container_entity(project):
    p = project.ontology_dir / "entities.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["entities"].append({"name": "Container", "business_object": "Container", "data_class": "master",
                            "target_table": "slv_mst_container", "grain": "One row per container.",
                            "business_key": ["container_no"], "surrogate_key": "container_sk", "scd_type": 2})
    p.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def _complete_todos(project, tmp_path):
    idx = versions.read(versions.latest(project.stem(APP, "build/index"), "json"))
    for n in idx["notebooks"].values():
        v = versions.latest(project.stem(APP, f"build/notebooks/{n['notebook']}"), "py")
        text = v.path.read_text(encoding="utf-8").replace(
            "bronze_count = None  # TODO(genie): row count after filter + dedup", "bronze_count = src.count()") \
            .replace("df = df  # replace", "df = df")
        f = tmp_path / f"{n['notebook']}.py"
        f.write_text(text, encoding="utf-8")
        save_notebook(project, APP, f, reason="TODO cells completed", via="genie")


def _qa_results(project, fail=False):
    plan = versions.read(versions.latest(project.stem(APP, "qa/plan"), "json"))
    out = [{"check": f"{q} x", "table": e["fqn"], "status": "pass"} for e in plan["tables"] for q in e["required"]]
    if fail:
        out[0]["status"] = "fail"
    return out


@pytest.fixture
def app(project, tmp_path):
    _to_cp4(project, tmp_path)
    _add_container_entity(project)
    return project


def test_codegen_notebooks(app, tmp_path):
    res = generate(app, APP)
    nbs = res["notebooks"]
    assert set(nbs) == {"slv_mst_container", "slv_mst_location", "slv_shipment", "slv_shipment_leg"}
    assert nbs["slv_mst_container"]["kind"] == "master"
    for n in nbs.values():
        text = versions.latest(app.stem(APP, f"build/notebooks/{n['notebook']}"), "py").path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        assert not [x.attr for x in ast.walk(tree) if isinstance(x, ast.Attribute) and x.attr in BANNED]
        assert "# GENERATED: parameters" in text and "# TODO(genie):" in text and "%pip" not in text
        assert 'DEV_CATALOG, DEV_SCHEMA = "dev", "silver_dev"' in text
    leg = versions.latest(app.stem(APP, f"build/notebooks/{nbs['slv_shipment_leg']['notebook']}"), "py").path.read_text(encoding="utf-8")
    assert "lookup_sk(df, spark.table(ENTITY_TABLES['Container'])" in leg and "['cntr_no']" in leg
    master = versions.latest(app.stem(APP, f"build/notebooks/{nbs['slv_mst_container']['notebook']}"), "py").path.read_text(encoding="utf-8")
    assert "load_staging(" in master and "slv_stg_mst_container_s90" in master
    # rerun: no new versions
    again = generate(app, APP)
    assert again["notebooks"] == nbs and not again["index"].created


def test_rerun_keeps_todo_and_marks_review(app, tmp_path):
    generate(app, APP)
    _complete_todos(app, tmp_path)
    # the STTM changes (grain) -> new version -> CP4 again -> regenerate
    sv = versions.latest(app.stem(APP, "sttm/sttm"), "json")
    doc = versions.read(sv)
    doc["tables"][1]["grain"] = "One row per move plan (changed)."
    save_output(app, APP, "sttm/sttm", doc, reason="input IN-0001", via="genie")
    with pytest.raises(MissingApproval):
        generate(app, APP)
    _approve(app, "CP4", edit=lambda s: s.replace(": must answer", ": accept"))
    res = generate(app, APP)
    rep = res["reports"][codegen.notebook_name(APP, {"target_table": doc["tables"][1]["target_table"]})]
    assert rep["todo_review"]
    name = res["notebooks"][doc["tables"][1]["target_table"]]["notebook"]
    text = versions.latest(app.stem(APP, f"build/notebooks/{name}"), "py").path.read_text(encoding="utf-8")
    assert "# REVIEW(STTM changed)" in text and "bronze_count = src.count()" in text
    assert any("REVIEW" in p for p in codegen.notebook_problems(text, codegen.build_settings(app)))


def test_hand_edited_generated_cell_is_refused(app, tmp_path):
    res = generate(app, APP)
    n = res["notebooks"]["slv_shipment"]["notebook"]
    text = versions.latest(app.stem(APP, f"build/notebooks/{n}"), "py").path.read_text(encoding="utf-8")
    f = tmp_path / f"{n}.py"
    f.write_text(text.replace('TARGET = f"{DEV_CATALOG}', 'TARGET = f"prod.{DEV_CATALOG}'), encoding="utf-8")
    with pytest.raises(ValueError, match="edited by hand"):
        save_notebook(app, APP, f, reason="x")


def test_masters_and_survivorship_rule(app, monkeypatch):
    generate(app, APP)
    mv = generate_masters(app, APP)
    m = versions.read(mv)["masters"]["Container"]
    assert m["feeding"] == [APP] and m["problems"] == [] and m["notebook"].startswith("masters/slv_mst_container/")
    text = (app.root / m["notebook"]).read_text(encoding="utf-8")
    assert "build_master(spark, ENTITY" in text
    ast.parse(text)
    from b2s.build import masters
    monkeypatch.setattr(masters, "_feeding", lambda layout, e: {APP: {}, "S91_other": {}})
    m2 = versions.read(generate_masters(app, APP))["masters"]["Container"]
    assert m2["problems"] and "survivorship" in m2["problems"][0]


def test_cp5_cp6_automatic_and_h2(app, tmp_path):
    generate(app, APP)
    generate_masters(app, APP)
    with pytest.raises(ApprovalError, match="automatic checkpoint"):
        request(app, APP, "CP5")
    make_plan(app, APP)
    plan = versions.read(versions.latest(app.stem(APP, "qa/plan"), "json"))
    assert {e["name"] for e in plan["tables"]} >= {"slv_stg_mst_container_s90", "slv_mst_container", "slv_shipment_leg"}
    record_results(app, APP, _qa_results(app, fail=True))
    save_output(app, APP, "build/code_review", "# Code review\n\nVerdict: pass\n", reason="review in a new chat", via="genie")
    res = run_automatic(app, APP, "CP5")
    assert not res["recorded"]
    assert any("TODO cell not completed" in p for p in res["problems"]) and any("QA" in p for p in res["problems"])
    with pytest.raises(MissingApproval):
        readiness(app, APP)
    _complete_todos(app, tmp_path)
    generate_masters(app, APP)
    make_plan(app, APP)
    record_results(app, APP, _qa_results(app))
    save_output(app, APP, "build/code_review", "# Code review (index updated)\n\nVerdict: pass\n", reason="review", via="genie")
    res = run_automatic(app, APP, "CP5")
    assert res["recorded"], res.get("problems")
    assert res["approval"]["how"] == "automatic" and res["approval"]["name_in_statement"] == "framework checks"
    rv = readiness(app, APP)
    assert rv.meta["complete"], rv.meta["problems"]
    res6 = run_automatic(app, APP, "CP6")
    assert res6["recorded"] and res6["handoff"].endswith("H2-001")
    folder = app.root / res6["handoff"]
    names = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    assert any(n.startswith("notebooks/nb_slv_") for n in names) and "masters/slv_mst_container.py" in names
    assert "README.md" in names and "manifest.json" in names
    st = navigator.status(app, APP)
    states = {a["point"]: (a["mode"], a["state"]) for a in st["approvals"]}
    assert states["CP5"] == ("automatic", "approved") and states["CP6"] == ("automatic", "approved")
    assert all(s["status"] == "current" for s in st["steps"]), navigator.render_text(st)
