"""M1.1: layout, write guard, atomic and write-once files, ids, events, leases, versions, items."""
import json
import os
from concurrent.futures import ProcessPoolExecutor

import pytest

import _workers
from b2s import items, versions
from b2s.layout import Layout, WriteGuardError, guard_write
from b2s.store import (LeaseHeld, acquire_lease, atomic_write, emit_event, list_events, next_id, stable_id,
                       write_once)


# ----------------------------------------------------------------- write guard (DC-02)
def test_guard_blocks_write_outside_test_root(tmp_path, monkeypatch):
    outside = tmp_path.parent / "not_the_test_root" / "sources.yaml"
    with pytest.raises(WriteGuardError):
        atomic_write(outside, b"x")
    assert not outside.exists()


def test_guard_blocks_everything_in_test_mode_without_root(tmp_path, monkeypatch):
    monkeypatch.delenv("B2S_TEST_ROOT")
    with pytest.raises(WriteGuardError):
        guard_write(tmp_path / "a.txt")


def test_guard_normal_mode_only_project_root(tmp_path, monkeypatch):
    monkeypatch.delenv("B2S_TEST")
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    Layout(tmp_path / "proj")
    guard_write(tmp_path / "proj" / "x.json")              # allowed
    with pytest.raises(WriteGuardError):
        guard_write(tmp_path / "elsewhere" / "x.json")


# ----------------------------------------------------------------- files
def test_atomic_write_leaves_no_temp_files(tmp_path):
    p = atomic_write(tmp_path / "d" / "f.json", b"{}")
    assert p.read_bytes() == b"{}"
    assert [f.name for f in p.parent.iterdir()] == ["f.json"]


def test_write_once_refuses_overwrite(tmp_path):
    write_once(tmp_path / "e.json", b"1")
    with pytest.raises(FileExistsError):
        write_once(tmp_path / "e.json", b"2")
    assert (tmp_path / "e.json").read_bytes() == b"1"


# ----------------------------------------------------------------- ids (DC-09)
def test_sequential_ids(project):
    assert [next_id(project, "Q") for _ in range(3)] == ["Q-0001", "Q-0002", "Q-0003"]
    assert next_id(project, "E") == "E-0001"


def test_parallel_id_allocation_with_contention(project):
    """Parallel processes force contention on the lock; every id must be unique and none skipped."""
    with ProcessPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(_workers.alloc_ids, [str(project.root)] * 6, [40] * 6))
    ids = [i for r in results for i in r]
    assert len(ids) == 240
    assert len(set(ids)) == 240
    assert sorted(ids) == [f"E-{n:04d}" for n in range(1, 241)]


def test_stable_id_same_identity_same_id():
    a = stable_id("OP", {"kind": "no_key", "tables": ["t1"]})
    b = stable_id("OP", {"tables": ["t1"], "kind": "no_key"})
    c = stable_id("OP", {"kind": "no_key", "tables": ["t2"]})
    assert a == b != c and a.startswith("OP-") and len(a) == 9


# ----------------------------------------------------------------- events
def test_events_are_one_file_each_and_carry_user(project):
    emit_event(project, "x", app="S01_a", via="genie")
    emit_event(project, "y", app="S01_a")
    evs = list_events(project, app="S01_a")
    assert [e["action"] for e in evs] == ["x", "y"]
    assert evs[0]["user"] == "worker@example.com" and evs[0]["via"] == "genie"


# ----------------------------------------------------------------- lease
def test_lease_refuses_other_user(project, monkeypatch):
    acquire_lease(project, "S01_a")
    acquire_lease(project, "S01_a")                       # renew own lease
    monkeypatch.setenv("B2S_USER", "someone.else@example.com")
    with pytest.raises(LeaseHeld):
        acquire_lease(project, "S01_a")


# ----------------------------------------------------------------- versions (design §7.5)
def test_versions_written_only_when_content_changes(project):
    stem = project.stem("S01_a", "models/logical")
    v1 = versions.save(project, stem, "yaml", {"tables": [1]}, reason="first", app="S01_a")
    v1b = versions.save(project, stem, "yaml", {"tables": [1]}, reason="rerun", app="S01_a")
    v2 = versions.save(project, stem, "yaml", {"tables": [1, 2]}, reason="input IN-0001", app="S01_a",
                       inputs={"models/conceptual": "v003"})
    assert (v1.n, v1.created, v1b.n, v1b.created, v2.n, v2.created) == (1, True, 1, False, 2, True)
    assert v2.path.name == "logical.v002.yaml" and v2.meta_path.name == "logical.v002.meta.json"
    assert v2.meta["inputs"] == {"models/conceptual": "v003"} and v2.meta["reason"] == "input IN-0001"
    assert versions.latest(stem).n == 2
    assert v2.label == "logical.v002"
    actions = [e["action"] for e in list_events(project, app="S01_a")]
    assert actions.count("version_created") == 2 and actions.count("version_unchanged") == 1


def test_version_files_are_never_overwritten(project):
    stem = project.stem("S01_a", "sttm/sttm")
    v = versions.save(project, stem, "json", {"a": 1}, reason="first")
    with pytest.raises(FileExistsError):
        write_once(v.path, b"{}")


def test_tamper_detection(project):
    stem = project.stem("S01_a", "models/logical")
    v = versions.save(project, stem, "yaml", {"x": 1}, reason="first")
    assert versions.verify(v)
    os.chmod(v.path, 0o666)
    v.path.write_text("x: 2\n")                           # a hand edit of a version file
    assert not versions.verify(versions.latest(stem))


def test_parallel_version_allocation(project):
    with ProcessPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(_workers.save_versions, [str(project.root)] * 4, range(4), [10] * 4))
    ns = sorted(n for r in results for n in r)
    assert ns == list(range(1, 41))


def test_same_output_new_inputs_refreshes_fingerprint(project):
    stem = project.stem("S01_a", "models/logical")
    versions.save(project, stem, "yaml", {"x": 1}, reason="first", fingerprint="fp1")
    v = versions.save(project, stem, "yaml", {"x": 1}, reason="rerun", fingerprint="fp2")
    assert v.n == 1 and versions.latest(stem).meta["fingerprint"] == "fp2"
    assert versions.latest(stem).meta["fingerprint_history"][0]["fingerprint"] == "fp1"


def test_diff_structured(project):
    stem = project.stem("S01_a", "models/logical")
    versions.save(project, stem, "yaml", {"tables": [{"name": "a"}, {"name": "b", "grain": "x"}]}, reason="first")
    versions.save(project, stem, "yaml", {"tables": [{"name": "b", "grain": "y"}, {"name": "c"}]}, reason="rerun")
    d = versions.diff(stem, 1, 2)
    assert d["from"] == "logical.v001" and d["to"] == "logical.v002"
    assert d["added"] == ["/tables[name=c]"] and d["removed"] == ["/tables[name=a]"]
    assert d["changed"] == ["/tables[name=b]/grain"]


# ----------------------------------------------------------------- items
def test_item_create_update_versions(project):
    e = items.create(project, "S01_a", "evidence", {
        "statement": "One row of mv_plan is one planned move.", "confidence": "medium",
        "origin": {"type": "document", "ref": "IF-0001"}, "root_source": "IF-0001"}, via="genie")
    assert e["id"] == "E-0001" and e["status"] == "unverified" and e["created"]["via"] == "genie"
    items.update(project, "S01_a", "E-0001", {"status": "confirmed_by_bronze"}, reason="bronze check")
    assert items.get(project, "S01_a", "E-0001")["status"] == "confirmed_by_bronze"
    assert items.get(project, "S01_a", "E-0001", version=1)["status"] == "unverified"
    assert items.get_version(project, "S01_a", "E-0001").path.name == "E-0001.v002.json"


def test_item_rules(project):
    with pytest.raises(items.ItemError):            # no root source
        items.create(project, "S01_a", "evidence", {"statement": "s", "confidence": "low", "origin": {"type": "document"}})
    with pytest.raises(items.ItemError):            # Glean is medium at most
        items.create(project, "S01_a", "evidence", {"statement": "s", "confidence": "high",
                                                     "origin": {"type": "glean"}, "root_source": "glean:GR-0001"})


def test_derived_item_keeps_decision_and_id(project):
    op, created = items.upsert_derived(project, "S01_a", "open_point", {"kind": "no_key", "tables": ["t1"]},
                                       {"point": "no_key", "tables": ["t1"], "detail": {"rows": 10}})
    items.update(project, "S01_a", op["id"], {"status": "accepted", "decision": "keep without key"}, reason="CP1")
    op2, created2 = items.upsert_derived(project, "S01_a", "open_point", {"kind": "no_key", "tables": ["t1"]},
                                         {"point": "no_key", "tables": ["t1"], "detail": {"rows": 12}})
    assert op2["id"] == op["id"] and created2 and op2["status"] == "accepted"


def test_corroboration_needs_different_roots():
    same = [{"root_source": "IF-0021"}, {"root_source": "IF-0021"}]
    diff = [{"root_source": "IF-0021"}, {"root_source": "bronze"}]
    proposed = [{"root_source": "IF-0021", "authority_class": "proposed"}, {"root_source": "bronze"}]
    assert not items.corroborated(same) and items.corroborated(diff) and not items.corroborated(proposed)
