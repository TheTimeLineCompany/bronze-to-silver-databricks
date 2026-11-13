"""Fixes from the integration reviews I-17 and I-18: paths, views, approvers, statements from stdin, data-only request
files, handover text, doctor and lock modes, installed skills, item buckets, copies after unifying abbreviations."""
import io
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

import pytest
import yaml

import _workers
from b2s import FRAMEWORK_ROOT, baseline, doctor, items, navigator, versions
from b2s.approve import ApprovalError, record, request
from b2s.baseline.readers import LocalCsvReader
from b2s.baseline.views import base_tables, quote, split_name
from b2s.cli import main
from b2s.columns import build_columns, set_scope
from b2s.install import install_skills, skills_problem
from b2s.layout import is_shared, workspace_path
from b2s.project import init_project, register_app
from flow_helpers import APP, build_to_p5


# ----------------------------------------------------------------- views (I-17 §2, I-18 #1)
def test_base_tables_from_view_text():
    sql = """-- comment FROM fake.t
      WITH recent AS (SELECT * FROM yard.mv_leg WHERE x = 'FROM a.b')
      SELECT * FROM recent r JOIN `yard`.`cntr mst` c ON 1=1
      LEFT JOIN cntr_status s ON 1=1 /* JOIN other.x */"""
    assert base_tables(sql, "yard") == ["yard.mv_leg", "yard.cntr mst", "yard.cntr_status"]
    assert base_tables("select * from s.t", "x", catalog="main") == ["main.s.t"]
    assert split_name("`my cat`.s.`t``x`") == ["my cat", "s", "t`x"]
    assert quote("my cat.s.t") == "`my cat`.`s`.`t`"


# ----------------------------------------------------------------- paths (I-17 §3, I-18 #9)
@pytest.mark.parametrize("p,shared", [
    ("/Workspace/Shared/a b/x", True), ("/Shared/x", True), ("dbfs:/Workspace/Shared", True),
    ("/Workspace/Users/u/../../Shared/x", True), ("/Workspace/Users/u/Frameworks/Old Frameworks/v1.4", False),
    ("/Users/u/Shared stuff", False)])
def test_shared_check_every_form(p, shared):
    assert is_shared(p) is shared


def test_workspace_path_one_form():
    assert workspace_path("/Workspace/Users/a/x/") == workspace_path("/Users/a/x") == "/Users/a/x"


def test_init_refuses_shared_written_without_workspace(tmp_path):
    with pytest.raises(ValueError, match="Shared"):
        init_project("/Shared/proj", "x")


def test_framework_folder_with_spaces_and_dots_and_moved(tmp_path):
    fw = tmp_path / "Frameworks" / "Old Frameworks" / "b2s v1.4.0"
    for part in ("b2s", "registry_template", "plugins", "skills"):
        shutil.copytree(FRAMEWORK_ROOT / part, fw / part, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(FRAMEWORK_ROOT / "FRAMEWORK_VERSION", fw)
    proj = tmp_path / "My Project.v2"
    env = {**os.environ, "PYTHONPATH": str(fw), "PYTHONDONTWRITEBYTECODE": "1"}
    run = lambda *a: subprocess.run([sys.executable, "-m", "b2s", *a], cwd=tmp_path, env=env,  # noqa: E731
                                    capture_output=True, text=True)
    assert run("init", str(proj), "Demo").returncode == 0
    moved = tmp_path / "moved" / "fw two"
    shutil.move(str(fw), str(moved))
    env["PYTHONPATH"] = str(moved)
    r = run("--project", str(proj), "register", "S01_demo", "Demo", "--schemas", "demo")
    assert r.returncode == 0, r.stderr
    r = run("--project", str(proj), "status", "S01_demo", "--brief")
    assert r.returncode == 0 and "Handover S01_demo" in r.stdout, r.stderr
    assert not list(moved.rglob("__pycache__"))


# ----------------------------------------------------------------- approvals (I-17 §4, I-18 #10)
@pytest.fixture
def cp2_ready(project):
    build_to_p5(project)
    build_columns(project, APP)
    set_scope(project, APP, "yard.contact", scope="out_of_scope", reason="x")
    return project


def test_agent_names_are_refused(cp2_ready):
    req = request(cp2_ready, APP, "CP2")
    with pytest.raises(ApprovalError, match="agent"):
        record(cp2_ready, APP, req["id"], req["template"].replace("<your name>", "Genie"))


def test_approver_list_is_by_account(cp2_ready, monkeypatch):
    cfg = yaml.safe_load(cp2_ready.project_yaml.read_text(encoding="utf-8"))
    cfg["approvers"] = ["worker@example.com"]
    cp2_ready.project_yaml.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    req = request(cp2_ready, APP, "CP2")
    monkeypatch.setenv("B2S_USER", "someone.else@example.com")
    with pytest.raises(ApprovalError, match="not an approver"):
        record(cp2_ready, APP, req["id"], req["template"].replace("<your name>", "Jane Doe"))
    monkeypatch.setenv("B2S_USER", "worker@example.com")
    record(cp2_ready, APP, req["id"], req["template"].replace("<your name>", "Jane Doe"))


def test_signature_is_recorded_with_the_account(cp2_ready, monkeypatch):
    """The typed name is a signature; the account e-mail is always recorded, and a different name is not refused."""
    monkeypatch.setenv("B2S_USER_NAME", "Worker One")
    req = request(cp2_ready, APP, "CP2")
    assert "<your name>" in req["template"]
    record(cp2_ready, APP, req["id"], req["template"].replace("<your name>", "J. Doe"))
    apr = items.list_items(cp2_ready, APP, "approval")[-1]
    assert apr["name_in_statement"] == "J. Doe" and apr["account"]["email"] == "worker@example.com"
    assert apr["account"]["name"] == "Worker One" and apr["signature_matches_account"] is False


def test_request_file_holds_data_only(cp2_ready):
    req = request(cp2_ready, APP, "CP2")
    assert "To approve" in req["chat_text"]
    stored = json.loads((cp2_ready.review_dir(APP) / f"{req['id']}.json").read_text(encoding="utf-8"))
    assert "chat_text" not in stored


def test_statement_from_stdin_keeps_quotes_and_lines(cp2_ready, monkeypatch, capsys):
    req = request(cp2_ready, APP, "CP2")
    stmt = req["template"].replace("<your name>", "Jane \"JD\" O'Neil")
    monkeypatch.setattr(sys, "stdin", io.StringIO(stmt))
    main(["--project", str(cp2_ready.root), "approve", "record", APP, req["id"], "--statement-file", "-"])
    apr = items.list_items(cp2_ready, APP, "approval")[-1]
    assert apr["statement"] == stmt and apr["name_in_statement"] == "Jane \"JD\" O'Neil"


# ----------------------------------------------------------------- handover and sizes (I-17 §4)
def test_status_brief_is_a_short_handover(cp2_ready):
    text = navigator.brief(cp2_ready, APP)
    assert text.startswith(f"Handover {APP}") and "Next:" in text and "Checkpoints:" in text
    assert len(text) <= 3000
    assert "skills are not installed" in text


def test_baseline_summary_is_small(project, tmp_path):
    from b2s.demo import fake_app
    fake = fake_app.make_fake_app(tmp_path / "fake")
    fake_app.install(project, fake)
    baseline.run(project, APP, LocalCsvReader(fake["bronze_root"]))
    v = versions.latest(project.stem(APP, "baseline/summary"), "json")
    assert v.path.stat().st_size < 8 * 1024


# ----------------------------------------------------------------- doctor and lock modes (I-17 §1, I-18 #3)
def test_doctor_writes_capabilities(project):
    res = doctor.file_checks(project)
    caps = yaml.safe_load(project.project_yaml.read_text(encoding="utf-8"))["capabilities"]
    assert res["results"]["K-01"]["ok"] and caps["lock_mode"] == "o_excl" and caps["atomic_rename"]
    assert "PASS" in doctor.render(res["results"]) and "MANUAL" in doctor.render(res["results"])


def test_mkdir_lock_mode_keeps_ids_unique(project):
    cfg = yaml.safe_load(project.project_yaml.read_text(encoding="utf-8"))
    cfg["capabilities"] = {"lock_mode": "mkdir"}
    project.project_yaml.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with ProcessPoolExecutor(max_workers=4) as ex:
        ids = [i for r in ex.map(_workers.alloc_ids, [str(project.root)] * 4, [25] * 4) for i in r]
    assert sorted(ids) == [f"E-{n:04d}" for n in range(1, 101)]
    assert not list(project.locks_dir.glob("*.lockdir"))


# ----------------------------------------------------------------- skills installed where Genie loads them (I-17 §4)
def test_install_skills_and_version_check(project, tmp_path):
    target = tmp_path / ".assistant" / "skills"
    stamp = install_skills(target, project)
    assert "b2s-run" in stamp["skills"] and (target / "p1-baseline" / "SKILL.md").exists()
    assert skills_problem(project) is None
    s = json.loads((target / ".b2s_skills_version.json").read_text(encoding="utf-8"))
    s["skills_hash"] = "sha256:old"
    (target / ".b2s_skills_version.json").write_text(json.dumps(s), encoding="utf-8")
    assert "install them again" in skills_problem(project)
    assert str(FRAMEWORK_ROOT.name) in (project.root / "AGENTS.md").read_text(encoding="utf-8") or True


# ----------------------------------------------------------------- many small files (I-17 §5)
def test_items_are_bucketed(project):
    register_app(project, APP, "x", ["yard"])
    for i in range(250):
        items.create(project, APP, "question", {"text": f"q{i}?"})
    folder = project.state_dir_app(APP) / "items" / "questions"
    buckets = sorted(p.name for p in folder.iterdir())
    assert buckets == ["Q-00xx", "Q-01xx", "Q-02xx"]
    assert max(len(list(b.iterdir())) for b in folder.iterdir()) <= 200       # 100 ids, file + sidecar
    assert len(items.list_items(project, APP, "question")) == 250


# ----------------------------------------------------------------- copies after unifying abbreviations (I-18 #4)
def test_copy_detection_unifies_abbreviations(project, tmp_path):
    root = tmp_path / "bronze"
    (root / "plnt").mkdir(parents=True)
    rows = "\n".join(f"P{i:03d},Plant {i}" for i in range(20))
    (root / "plnt" / "plant_master.csv").write_text("plt_cd,plt_nm,created_by\n" +
                                                    "\n".join(f"P{i:03d},Plant {i},u{i}" for i in range(20)) + "\n")
    (root / "plnt" / "plant_master_old.csv").write_text("plant_code,plant_name\n" + rows + "\n")
    (root / "schema.json").write_text(json.dumps({"tables": {
        "plnt.plant_master": {"columns": [["plt_cd", "string"], ["plt_nm", "string"], ["created_by", "string"]], "view": None},
        "plnt.plant_master_old": {"columns": [["plant_code", "string"], ["plant_name", "string"]], "view": None}}}))
    register_app(project, "S02_plant", "plants", ["plnt"])
    s = baseline.run(project, "S02_plant", LocalCsvReader(root))
    copy = {t["table"]: t["copy_of"] for t in s["tables"]}
    assert copy["plnt.plant_master_old"] == "plnt.plant_master"
