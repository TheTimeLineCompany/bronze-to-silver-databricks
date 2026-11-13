"""M1.3: P2 bronze baseline on the fake application S90_yardops."""
import csv
import json
from pathlib import Path

import pytest
import yaml

from b2s import items, versions
from b2s.baseline import LocalCsvReader, RedactionError, run
from b2s.demo.fake_app import APP, install, make_fake_app
from b2s.project import init_project
from b2s.store import list_events


@pytest.fixture
def env(tmp_path):
    fake = make_fake_app(tmp_path / "fake")              # bronze lives outside the project folder
    layout = init_project(tmp_path / "proj", "Test")
    install(layout, fake)
    return layout, fake, LocalCsvReader(fake["bronze_root"])


def _by_table(summary):
    return {e["table"]: e for e in summary["tables"]}


def _table(layout, t):
    return versions.read(versions.latest(layout.stem(APP, f"baseline/tables/{t}"), "json"))


def _version_files(layout):
    return sorted(p.name for p in layout.app_dir(APP).rglob("*.v[0-9][0-9][0-9].*") if not p.name.endswith(".meta.json"))


def test_key_results(env):
    layout, _, reader = env
    s = _by_table(run(layout, APP, reader))
    assert s["yard.cntr_mst"]["key_result"] == "key" and s["yard.cntr_mst"]["key"] == ["cntr_no"]
    assert s["yard.mv_leg"]["key"] == ["plan_id", "leg_no"]                      # composite
    assert s["yard.mv_plan"]["key_result"] == "near_key" and s["yard.mv_plan"]["key"] == ["plan_id"]
    assert _table(layout, "yard.mv_plan")["key_detail"]["duplicates"] == 2
    assert s["yard.rate_card"]["key_result"] == "no_key_within_limits"
    rc = _table(layout, "yard.rate_card")["key_detail"]
    assert rc["limits"]["max_key_size"] == 4 and len(rc["unique_over"]) == 5
    assert s["yard.yard_stat"]["key_result"] == "no_key"
    assert s["yard.empty_tbl"]["key_result"] == "empty" and s["yard.empty_tbl"]["empty"]


def test_removed_by_rule(env):
    layout, _, reader = env
    run(layout, APP, reader)
    assert _table(layout, "yard.cntr_mst")["removed_by_rule"]["AUDIT"] == ["created_by", "created_at"]
    leg = _table(layout, "yard.mv_leg")
    assert leg["removed_by_rule"]["CDC_LOAD_VERSION"] == ["load_version"]
    assert {c["column"]: c["column_class"] for c in leg["columns"]}["load_version"] == "cdc_metadata"
    assert _table(layout, "yard.loc")["removed_by_rule"]["DESC_NOT_KEY"] == ["loc_name"]
    berth = _table(layout, "yard.berth")
    assert berth["allowed_by_rule"]["NM_FALLBACK"] == ["berth_nm"] and berth["key"] == ["berth_nm"]


def test_copy_detection_and_open_points(env):
    layout, _, reader = env
    s = _by_table(run(layout, APP, reader))
    assert s["yard.mv_leg_bkp"]["copy_of"] == "yard.mv_leg" and s["yard.mv_leg"]["copy_of"] is None
    ops = {o["point"]: o for o in items.list_items(layout, APP, "open_point")}
    assert set(ops) == {"near_key", "no_key_within_limits", "no_key", "empty", "copy_of"}
    assert ops["copy_of"]["tables"] == ["yard.mv_leg_bkp", "yard.mv_leg"]


def test_classification(env):
    layout, _, reader = env
    run(layout, APP, reader)
    cls = lambda t: {c["column"]: c["column_class"] for c in _table(layout, t)["columns"]}
    sess, contact = cls("yard.usr_session"), cls("yard.contact")
    assert sess["user_ip"] == "application_log" and sess["user_agent"] == "application_log"
    assert contact["email"] == contact["phone"] == contact["contact_name"] == "personal_data"


def test_no_sensitive_value_in_any_written_file(env):
    """R-01: scan every file the framework wrote under the project folder (the inbox holds raw client input)."""
    layout, fake, reader = env
    run(layout, APP, reader)
    run(layout, APP, reader, fresh=True)
    hits = []
    for f in layout.root.rglob("*"):
        if f.is_file() and "inbox" not in f.relative_to(layout.root).parts:
            text = f.read_text(encoding="utf-8", errors="ignore")
            hits += [(f.name, v) for v in fake["sensitive_values"] if v in text]
    assert hits == []


def test_top_values_only_for_low_cardinality_codes(env):
    layout, _, reader = env
    run(layout, APP, reader)
    cols = {c["column"]: c for c in _table(layout, "yard.cntr_mst")["columns"]}
    assert cols["iso_type"]["topk"] and not cols["cntr_no"]["topk"]               # code yes, key no
    assert cols["created_by"]["topk"] == [] and cols["created_by"]["min"] is None


def test_redaction_cannot_be_switched_off_silently(env):
    layout, _, reader = env
    cfg = yaml.safe_load(layout.project_yaml.read_text())
    cfg["settings"]["redact_values"] = False
    layout.project_yaml.write_text(yaml.safe_dump(cfg))
    with pytest.raises(RedactionError):
        run(layout, APP, reader)
    run(layout, APP, reader, redact_off_reason="client approved for test data")
    assert list_events(layout, app=APP, action="redaction_off")


def test_rerun_unchanged_creates_no_versions(env):
    layout, _, reader = env
    s1 = run(layout, APP, reader)
    before = _version_files(layout)
    s2 = run(layout, APP, LocalCsvReader(reader.root))
    assert _version_files(layout) == before
    assert s1["open_points"] == s2["open_points"]                                   # stable ids
    ev = list_events(layout, app=APP, action="baseline_run")[-1]
    assert ev["created"] == [] and len(ev["skipped"]) == len(s1["tables"])


def test_changed_csv_new_version_of_that_table_only(env):
    layout, fake, reader = env
    run(layout, APP, reader)
    p = Path(fake["bronze_root"]) / "yard" / "loc.csv"
    with open(p, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["BLK-D", "Yard location BLK-D"])
    run(layout, APP, LocalCsvReader(fake["bronze_root"]))
    ev = list_events(layout, app=APP, action="baseline_run")[-1]
    assert ev["created"] == ["yard.loc"]
    assert versions.latest(layout.stem(APP, "baseline/tables/yard.loc"), "json").n == 2
    assert versions.latest(layout.stem(APP, "baseline/tables/yard.cntr_mst"), "json").n == 1
    summ = versions.latest(layout.stem(APP, "baseline/summary"), "json")
    assert summ.n == 2 and summ.meta["inputs"]["baseline/tables/yard.loc"] == "v002"


def test_time_budget_partial_then_resume(env):
    layout, _, reader = env
    s = run(layout, APP, reader, time_budget_s=0)
    assert s["partial"] and len(s["tables"]) == 1 and s["remaining"]
    s2 = run(layout, APP, reader)
    assert not s2["partial"] and len(s2["tables"]) == 13
    ev = list_events(layout, app=APP, action="baseline_run")[-1]
    assert len(ev["skipped"]) == 1 and len(ev["created"]) == 12


def test_summary_is_small(env):
    layout, _, reader = env
    run(layout, APP, reader)
    v = versions.latest(layout.stem(APP, "baseline/summary"), "json")
    assert v.path.stat().st_size < 20_000
    e = json.loads(v.path.read_text())["tables"][0]
    assert set(e) >= {"table", "row_count", "n_columns", "key", "key_result", "copy_of", "empty", "version", "open_points"}


def test_view_fingerprint_follows_base_table(env):
    layout, fake, reader = env
    run(layout, APP, reader)
    st = reader.state("yard.v_cntr")
    assert st["view_text"] and st["base_tables"] == ["yard.cntr_mst"] and st["base_versions"]["yard.cntr_mst"]
