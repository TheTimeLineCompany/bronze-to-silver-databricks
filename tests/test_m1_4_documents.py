"""M1.4: P2.1 documents — inventory, triage, extract on the fake application's inbox."""
import pytest

from b2s import documents, items, versions
from b2s.demo.fake_app import APP, install, make_fake_app
from b2s.project import init_project


@pytest.fixture
def env(tmp_path):
    fake = make_fake_app(tmp_path / "fake")
    layout = init_project(tmp_path / "proj", "Test")
    install(layout, fake)
    return layout


def test_inventory(env):
    inv = documents.inventory(env, APP)
    assert inv["duplicates"] == ["overview (copy).md"]                       # the clean name is kept
    assert inv["compare"] == [["archive/notes.md", "notes.md"]]
    assert inv["unreadable"] == [{"path": "yard_layout.png", "reason": "image"}]
    docs = items.list_items(env, APP, "document")
    assert len(docs) == 6                                                    # 7 files, one exact copy
    by = {f["path"]: f for f in inv["files"]}
    assert by["overview (copy).md"]["doc_id"] == by["overview.md"]["doc_id"]


def test_inventory_idempotent(env):
    documents.inventory(env, APP)
    documents.inventory(env, APP)
    assert len(items.list_items(env, APP, "document")) == 6
    assert versions.latest(env.stem(APP, "documents/inventory"), "json").n == 1


def test_triage(env):
    documents.inventory(env, APP)
    t = {e["path"]: e for e in documents.triage(env, APP)["documents"]}
    assert t["overview (copy).md"]["relevance"] == "ignore"
    assert t["slides_old_v1.md"]["relevance"] == "ignore"
    assert t["archive/notes.md"]["relevance"] == "ignore"
    assert t["notes.md"]["relevance"] == "background"                        # minutes
    assert t["yard_layout.png"]["relevance"] == "background"
    assert t["overview.md"]["relevance"] == "core" and "Workflow" in t["overview.md"]["reading_plan"]
    assert t["data_dictionary.md"]["type"] == "data_dictionary"


def test_triage_core_budget(env):
    import yaml
    info = env.ontology_dir / "information.yaml"
    d = yaml.safe_load(info.read_text(encoding="utf-8"))
    d["budgets"]["max_core_files"] = 1
    info.write_text(yaml.safe_dump(d), encoding="utf-8")
    documents.inventory(env, APP)
    res = documents.triage(env, APP)
    assert res["counts"]["core"] == 1


def test_extract_redacts_personal_data(env):
    documents.inventory(env, APP)
    documents.triage(env, APP)
    res = documents.extract(env, APP)
    assert len(res["extracted"]) == 2
    texts = [p.read_text(encoding="utf-8") for p in env.stem(APP, "documents/extracts/x").parent.glob("*.md")]
    joined = "\n".join(texts)
    assert "ops.lead@yardops.example" not in joined and "+49 40 555 0100" not in joined
    assert "aaa.aaaa@aaaaaaa.aaaaaaa" in joined and "mv_plan" in joined


def test_redact_text_keeps_dates():
    assert documents.redact_text("on 2026-02-10 call +49 170 5551234") == "on 2026-02-10 call +99 999 9999999"
