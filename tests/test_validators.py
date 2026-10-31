"""Tests for every code check behind the checkpoints. Run: python -m pytest -q tests/

Each test copies the repo to a temp folder, breaks one thing, and checks that the
code catches it. If a test fails, a checkpoint can be passed by mistake.
"""
import csv
import glob
import json
import re
import os
import shutil
import sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
import p1_1_inventory as inv  # noqa: E402
import p1_2_check_context as ctxc  # noqa: E402
import p2_1_extract_doc_profiles as dp  # noqa: E402
import p4_2_validate_sttm as vs  # noqa: E402
import x_feedback as fb  # noqa: E402
import x_ontology_check as oc  # noqa: E402
import x_validate_gate as vg  # noqa: E402
import x_checkpoint_pack as pkm  # noqa: E402
import p2_2_discover as discm  # noqa: E402

S07 = "sources/S07_container_moves/04_mapping/sttm.yaml"
S01 = "sources/S01_buyer_master/04_mapping/sttm.yaml"


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    dst = tmp_path / "repo"
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    for m in (inv, ctxc, dp, vs, fb, vg, oc, pkm, discm):
        monkeypatch.setattr(m, "ROOT", str(dst))
    return str(dst)


def _edit(path, fn):
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    fn(doc)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, sort_keys=False)


def _val(repo, rel):
    return vs.validate(os.path.join(repo, rel), vs.load_context(repo), repo)


def _has(res, text):
    errs = res.errors if hasattr(res, "errors") else res
    return any(text in e for e in errs)


def _col(doc, name, ti=0):
    return next(c for c in doc["tables"][ti]["columns"] if c["target"] == name)


# ---------------- P4.2 STTM: structure, keys, central model ----------------

def test_examples_pass(repo):
    assert _val(repo, S01).ok, _val(repo, S01).errors
    assert _val(repo, S07).ok, _val(repo, S07).errors


def test_fk_to_unknown_entity_fails(repo):
    _edit(os.path.join(repo, S07), lambda d: _col(d, "container_sk")["fk"].update(entity="Warehouse"))
    assert _has(_val(repo, S07), "not in registry/entities.yaml")


def test_fk_must_use_entity_surrogate_key(repo):
    _edit(os.path.join(repo, S07), lambda d: _col(d, "origin_location_sk")["fk"].update(column="location_code"))
    assert _has(_val(repo, S07), "surrogate key of entity Location: 'location_sk'")


def test_pk_column_must_exist(repo):
    _edit(os.path.join(repo, S07), lambda d: d["tables"][0].update(primary_key=["missing_sk"]))
    assert _has(_val(repo, S07), "primary_key column 'missing_sk'")


def test_low_confidence_needs_question(repo):
    _edit(os.path.join(repo, S07), lambda d: _col(d, "eta_ts").update(open_question=None))
    assert _has(_val(repo, S07), "low confidence needs an open_question")


def test_cannot_approve_with_open_blocking_question(repo):
    _edit(os.path.join(repo, S07), lambda d: d.update(status="approved"))
    assert _has(_val(repo, S07), "blocking question Q-0001")


def test_scd2_needs_columns(repo):
    def drop(d):
        d["tables"][0]["columns"] = [c for c in d["tables"][0]["columns"] if c["target"] != "is_current"]
    _edit(os.path.join(repo, S01), drop)
    assert _has(_val(repo, S01), "scd_type 2 needs column 'is_current'")


def test_master_must_match_registry(repo):
    _edit(os.path.join(repo, S01), lambda d: d["tables"][0].update(business_key=["buyer_name"]))
    assert _has(_val(repo, S01), "business_key must match registry")


def test_naming_rule(repo):
    _edit(os.path.join(repo, S07), lambda d: d["tables"][0].update(target_table="ShipmentLegs"))
    assert _has(_val(repo, S07), "table name breaks naming rule")


def test_unknown_key_rule(repo):
    _edit(os.path.join(repo, S07), lambda d: _col(d, "container_number").update(key_rule="iso_container"))
    assert _has(_val(repo, S07), "key_rule 'iso_container'")


# ---------------- Ontology coherence ----------------

def test_unknown_business_object(repo):
    _edit(os.path.join(repo, S07), lambda d: d["tables"][0].update(business_object="Voyage"))
    assert _has(_val(repo, S07), "business_object 'Voyage'")


def test_load_pattern_must_fit_data_class(repo):
    _edit(os.path.join(repo, S07), lambda d: d["tables"][0].update(load_pattern="overwrite"))
    assert _has(_val(repo, S07), "not allowed for data_class 'event'")


def test_fk_needs_business_relationship(repo):
    def fn(d):
        b = yaml.safe_load(open(os.path.join(repo, "registry/ontology/business.yaml")))
        b["relationships"] = {k: v for k, v in b["relationships"].items() if k != "R10"}
        yaml.safe_dump(b, open(os.path.join(repo, "registry/ontology/business.yaml"), "w"), sort_keys=False)
    fn(None)
    assert _has(_val(repo, S07), "no N:1 or 1:1 business relationship from 'ShipmentLeg' to 'Container'")


def test_business_logic_needs_rule(repo):
    _edit(os.path.join(repo, S07), lambda d: _col(d, "transit_days").update(business_rule=None))
    assert _has(_val(repo, S07), "needs business_rule")


def test_evidence_id_must_exist(repo):
    _edit(os.path.join(repo, S07), lambda d: _col(d, "shipment_id")["provenance"].update(evidence=["E-0999"]))
    assert _has(_val(repo, S07), "evidence E-0999 is not in")


def test_key_cannot_rest_on_low_confidence(repo):
    _edit(os.path.join(repo, S07), lambda d: _col(d, "leg_seq").update(provenance={"evidence": ["E-0008"]}))
    assert _has(_val(repo, S07), "has no valid support")


def test_ontology_check_coherent(repo):
    errs, _ = oc.check(repo)
    assert errs == []


def test_synonym_collision(repo):
    p = os.path.join(repo, "registry/ontology/business.yaml")
    _edit(p, lambda d: d["business_objects"]["Part"]["synonyms"].append("vendor"))
    errs, _ = oc.check(repo)
    assert any("synonym 'vendor'" in e for e in errs)


# ---------------- P1 context: inventory, triage, brief, evidence ----------------

def test_inventory_flags_duplicates_and_old_versions(repo):
    rows = inv.build("S07_container_moves")
    by = {r["name"]: r for r in rows}
    assert by["Copy of CNTRK_profiling_v3_FINAL.xlsx"]["duplicate_of"]
    assert by["CNTRK_solution_overview_draft.docx"]["suggested_relevance"] == "ignore"
    assert by["CNTRK_profiling_v3_FINAL.xlsx"]["suggested_type"] == "profiling_workbook"
    assert by["KPI definitions logistics.docx"]["suggested_type"] == "business_rules_doc"


def test_context_examples_pass(repo):
    for s in ("S01_buyer_master", "S07_container_moves"):
        e = ctxc.check(s, repo)
        assert all(not v for v in e.values()), e


def test_core_budget(repo):
    p = os.path.join(repo, "registry/ontology/information.yaml")
    _edit(p, lambda d: d["budgets"].update(max_core_files=2))
    assert _has(ctxc.check("S07_container_moves", repo)["triage"], "core files > budget 2")


def test_evidence_cannot_cite_ignored_file(repo):
    p = os.path.join(repo, "sources/S07_container_moves/02_evidence/evidence_register.csv")
    rows = list(csv.DictReader(open(p)))
    rows[2]["file_id"] = "IF-0010"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    assert _has(ctxc.check("S07_container_moves", repo)["evidence"], "triage marks 'ignore'")


def test_brief_word_budget(repo):
    p = os.path.join(repo, "registry/ontology/information.yaml")
    _edit(p, lambda d: d["budgets"].update(source_brief_max_words=50))
    assert _has(ctxc.check("S07_container_moves", repo)["brief"], "words > budget 50")


def test_confidence_normalisation():
    assert dp.norm_confidence("High") == "high"
    assert dp.norm_confidence("40%") == "low"
    assert dp.norm_confidence(0.65) == "medium"
    assert dp.norm_confidence("amber") == "medium"
    assert dp.norm_confidence(None) == "unknown"


def test_extract_doc_profiles(repo):
    out, unmapped = dp.extract("S07_container_moves", root=repo)
    conf = {r["column"]: r["confidence"] for r in out}
    assert conf["CNTR_NO"] == "high" and conf["ETA_TS"] == "low" and conf["CARRIER_REF"] == "low"


# ---------------- Feedback and checkpoints ----------------

def _set_cp(repo, sid, cp, status="approved", meta=True):
    def fn(d):
        for s in d["sources"]:
            if s["id"] == sid:
                s["checkpoints"][cp].update(status=status, **({"approved_by": "x", "date": "2026-11-01", "pr": 1} if meta else {}))
    _edit(os.path.join(repo, "registry/sources.yaml"), fn)


def test_initial_state_consistent(repo):
    errors, _ = vg.check(repo)
    assert errors == [], errors


def test_cp1_can_be_approved_when_context_ok(repo):
    _set_cp(repo, "S01_buyer_master", "CP1_source_brief")
    errors, _ = vg.check(repo)
    assert errors == [], errors


def test_open_feedback_blocks_checkpoint(repo):
    _set_cp(repo, "S07_container_moves", "CP1_source_brief")
    _set_cp(repo, "S07_container_moves", "CP2_evidence")
    errors, _ = vg.check(repo)
    assert any("feedback still open" in e and "FB-0001" in e for e in errors)


def test_verified_feedback_unblocks(repo):
    p = os.path.join(repo, "sources/S07_container_moves/02_evidence/feedback/CP2_evidence/FB-0001.yaml")
    _edit(p, lambda d: d.update(status="verified", verified_by="reviewer1"))
    _set_cp(repo, "S07_container_moves", "CP1_source_brief")
    _set_cp(repo, "S07_container_moves", "CP2_evidence")
    errors, _ = vg.check(repo)
    assert not any("FB-0001" in e for e in errors)
    assert any("discovery cards not answered" in e for e in errors)   # T-004 still open
    assert any("upstream issues raised from this phase" in e and "FB-0003" in e for e in errors)


def test_cp4_before_cp1_fails(repo):
    _set_cp(repo, "S01_buyer_master", "CP4_sttm")
    errors, _ = vg.check(repo)
    assert any("approved before CP1_source_brief" in e for e in errors)
    assert any("global CP3" in e for e in errors)
    assert any("sttm_review.md" in e for e in errors)


def test_cp4b_not_required_with_business_logic_fails(repo):
    _set_cp(repo, "S07_container_moves", "CP4b_business_logic", status="not_required")
    errors, _ = vg.check(repo)
    assert any("business_logic columns" in e for e in errors)


def test_cp6_blocked_by_open_question(repo):
    for cp in vg.ORDER:
        _set_cp(repo, "S07_container_moves", cp)
    errors, _ = vg.check(repo)
    assert any("blocking questions still open" in e for e in errors)


def test_feedback_plan_and_reset(repo):
    _set_cp(repo, "S07_container_moves", "CP1_source_brief")
    _set_cp(repo, "S07_container_moves", "CP2_evidence")
    d = next(x for x in fb.all_feedback(repo) if x["id"] == "FB-0001")
    pl = fb.plan(d)
    assert pl["rerun_now"] == ["p2-3-evidence-reconcile"]
    assert "p3-1-entity-model" not in pl["then_recheck"]
    changed = fb.reset("S07_container_moves", pl["reset_checkpoints"], repo)
    assert changed == ["CP2_evidence"]


def test_feedback_needs_content():
    errs = fb.validate_item({"_path": "x", "id": "FB-0009", "source_id": "S07_container_moves",
                             "checkpoint": "CP4_sttm", "raised_by": "a", "status": "open"})
    assert any("give at least one of" in e for e in errs)


# ---------------- Keys ----------------

def test_key_normalisation_examples():
    from lib import keys
    assert keys.normalise_py("container_number", " abcu-1234567 ") == "ABCU1234567"
    assert keys.normalise_py("supplier_code", "4711") == "00004711"
    assert keys.normalise_py("part_number", "N/A") is None


# ---------------------------------------------------------------- skills
def test_skills_match_step_catalogue_and_frontmatter():
    import glob as _g
    import x_feedback as _fb
    real = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    names = set()
    for p in _g.glob(os.path.join(real, "skills", "*", "SKILL.md")):
        fm = yaml.safe_load(open(p, encoding="utf-8").read().split("---")[1])
        assert set(fm) == {"name", "description"}, p
        assert fm["name"] == os.path.basename(os.path.dirname(p))
        assert len(fm["description"]) <= 1024
        names.add(fm["name"])
    assert {s for s, _, _ in _fb.STEPS} | {"x-feedback-rerun", "x-clarify"} == names


def test_agents_md_under_genie_limit():
    real = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert len(open(os.path.join(real, "AGENTS.md"), encoding="utf-8").read()) < 20000



# ---------------------------------------------------------------- upstream issues, packs
def test_raise_accept_and_repeat_guard(repo):
    fid = fb.raise_item("S07_container_moves", "CP2_evidence", "p4-1-sttm-author", "No evidence for CARRIER_REF", blocks="CP4_sttm", root=repo)
    d = fb._find(fid, "S07_container_moves", repo)
    assert d["status"] == "proposed" and d["raised_by"] == "agent:p4-1-sttm-author"
    f2 = fb.raise_item("S07_container_moves", "CP2_evidence", "p4-1-sttm-author", "again", related=fid, root=repo)
    f3 = fb.raise_item("S07_container_moves", "CP2_evidence", "p4-1-sttm-author", "and again", related=f2, root=repo)
    errors, _ = vg.check(repo)
    assert any(f3 in e and "a person must decide" in e for e in errors)
    _set_cp(repo, "S07_container_moves", "CP4_sttm")
    errors, _ = vg.check(repo)
    assert any("upstream issues raised from this phase" in e and fid in e for e in errors)


def test_proposed_only_for_agents(repo):
    d = {"id": "FB-0099", "source_id": "S07_container_moves", "checkpoint": "CP2_evidence", "raised_by": "reviewer1",
         "status": "proposed", "comment": "x", "_path": "x"}
    assert any("only agent-raised" in e for e in fb.validate_item(d))


def test_checkpoint_pack_written_and_stale_detected(repo):
    import x_checkpoint_pack as pk
    p, d = pk.write("S01_buyer_master", "CP1_source_brief", repo)
    for ext in ("json", "xlsx", "md", "html"):
        assert os.path.exists(os.path.join(d, f"CP1_source_brief.{ext}"))
    assert pk.stale("S01_buyer_master", "CP1_source_brief", repo) is None
    with open(os.path.join(repo, "sources/S01_buyer_master/01_intake/source_brief.md"), "a") as f:
        f.write("\nchange\n")
    assert "stale" in pk.stale("S01_buyer_master", "CP1_source_brief", repo)
    _set_cp(repo, "S01_buyer_master", "CP1_source_brief")
    errors, _ = vg.check(repo)
    assert any("stale" in e for e in errors)


def test_every_checkpoint_pack_builds(repo):
    import x_checkpoint_pack as pk
    for cp in fb.SOURCE_CP_ORDER:
        p = pk.build("S07_container_moves", cp, repo)
        assert p["metrics"] and p["decide"] and p["tables"]
    for cp in fb.GLOBAL_CPS:
        assert pk.build("global", cp, repo)["tables"]


# ---------------------------------------------------------------- bronze discovery (pure logic, no Spark)
from discovery import core as dcore  # noqa: E402

B = {"sample_rows": 1000, "max_key_checks": 15, "max_key_size": 3, "key_pool_size": 8, "fk_containment_high": 0.98,
     "fk_containment_low": 0.8, "min_link_score": 0.3, "max_link_checks": 50, "reference_max_rows": 1000}


def _p(col, fam="str", nd=1000, null=0.0, **kw):
    return {"column": col, "family": fam, "approx_distinct": nd, "null_pct": null, "sample_rows": 1000,
            "min_len": 5, "max_len": 12, "avg_len": 8, "min": "A", "max": "Z", "patterns": kw.pop("patterns", []), **kw}


def test_find_keys_single_then_composite_minimal():
    prof = [_p("ORDER_NO", nd=400), _p("LINE_NO", "int", nd=10, min=1, max=10), _p("QTY", "num", nd=300), _p("_ingest_ts", "date")]
    truth = {("LINE_NO", "ORDER_NO"), ("ORDER_NO", "LINE_NO")}
    calls = []

    def verify(cols):
        calls.append(tuple(cols))
        return tuple(cols) in truth
    r = dcore.find_keys(prof, 1000, verify, B)
    assert sorted(r["best"]) == ["LINE_NO", "ORDER_NO"]
    assert not any("QTY" in c or "_ingest_ts" in c for c in calls)     # measures and technical columns never tested


def test_find_keys_respects_budget():
    prof = [_p(f"C{i}", nd=50) for i in range(8)]
    r = dcore.find_keys(prof, 1000, lambda c: False, {**B, "max_key_checks": 5})
    assert r["checks"] == 5 and r["best"] is None


def test_judge_link_normalisation_and_partial():
    j = dcore.judge_link({"containment_raw": 0.86, "containment_norm": 1.0}, False, B)
    assert j["status"] == "fk" and "normalisation" in j["note"] and j["cardinality"] == "N:1"
    j = dcore.judge_link({"containment_raw": 0.85, "containment_norm": 0.9}, True, B)
    assert j["status"] == "fk_partial" and j["cardinality"] == "1:1"
    assert dcore.judge_link({"containment_raw": 0.2, "containment_norm": 0.3}, False, B)["status"] == "no_link"


def test_link_candidates_need_a_key_and_similar_names():
    tables = {"s.locations": {"row_count": 10, "columns": [_p("LOC_CD", nd=10), _p("LOC_NAME", nd=10)]},
              "s.legs": {"row_count": 5000, "columns": [_p("FROM_LOC", nd=18), _p("CUSTOMER", nd=4), _p("AMOUNT", "num", nd=900)]}}
    keys = {"s.locations": {"keys": [["LOC_CD"]], "best": ["LOC_CD"]}, "s.legs": {"keys": [], "best": None}}
    c = dcore.link_candidates(tables, keys, B, {"loc": "location"})
    pairs = {(x["dep_column"], x["ref_column"]) for x in c}
    assert ("FROM_LOC", "LOC_CD") in pairs and not any(x[0] == "AMOUNT" for x in pairs)


def test_classify_roles():
    legs = {"row_count": 5000, "columns": [_p("SHPMT_ID"), _p("LEG_NO", "int", nd=3), _p("ATD_TS", "date"), _p("FROM_LOC")]}
    out = [{"dep_column": "SHPMT_ID"}, {"dep_column": "FROM_LOC"}]
    r = dcore.classify("legs", legs, ["SHPMT_ID", "LEG_NO"], out, [], B)
    assert r["role"] == "transaction_line" and r["data_class"] == "event"
    codes = {"row_count": 5, "columns": [_p("TYPE_CD", nd=5), _p("TYPE_DESC", nd=5)]}
    assert dcore.classify("container_types", codes, ["TYPE_CD"], [], [{"dep_unique": False}], B)["role"] == "reference"
    assert dcore.classify("legs_bkp_2025", legs, ["SHPMT_ID", "LEG_NO"], out, [], B)["role"] == "staging"
    agg = {"row_count": 300, "columns": [_p("DEP_DATE", "date"), _p("FROM_LOC"), _p("N_LEGS", "int"), _p("AVG_DAYS", "num")]}
    assert dcore.classify("leg_daily_summary", agg, ["DEP_DATE", "FROM_LOC"], [{"dep_column": "FROM_LOC"}], [], B)["role"] == "aggregate"


def test_ontology_mapping_uses_synonyms_and_penalises_code_lists():
    bus = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "registry/ontology/business.yaml")))
    legs = {"row_count": 5000, "columns": [_p("CNTR_NO"), _p("SHPMT_ID"), _p("LEG_NO", "int")]}
    m = dcore.map_ontology("legs", legs, {"role": "event"}, bus)
    assert m[0]["business_object"] == "ShipmentLeg"
    types = {"row_count": 5, "columns": [_p("TYPE_CD"), _p("TYPE_DESC")]}
    m = dcore.map_ontology("container_types", types, {"role": "reference"}, bus)
    assert not m or m[0]["business_object"] != "Container" or dcore.ontology_confidence(m) != "high"


def test_lineage_levels():
    lv = dcore.lineage_levels(["a", "b", "c"], [{"dep_table": "c", "ref_table": "b"}, {"dep_table": "b", "ref_table": "a"}])
    assert lv == {"a": 0, "b": 1, "c": 2}


@pytest.mark.skipif(not os.environ.get("RUN_SPARK"), reason="set RUN_SPARK=1 to run the Spark end-to-end discovery test (~90 s)")
def test_discovery_end_to_end_spark(repo, tmp_path):
    from pyspark.sql import SparkSession
    spark = (SparkSession.builder.master("local[2]").config("spark.sql.warehouse.dir", str(tmp_path / "wh"))
             .config("spark.ui.enabled", "false").config("spark.sql.shuffle.partitions", "2").getOrCreate())
    sys.path.insert(0, repo)
    from tests.fixtures.make_bronze_s07 import make
    make(spark, "ct_test")
    sp = os.path.join(repo, "registry/sources.yaml")
    with open(sp) as f:
        s = f.read().replace("bronze_schema: bronze.container_track", "bronze_schema: ct_test")
    with open(sp, "w") as f:
        f.write(s)
    import shutil as _sh
    _sh.rmtree(os.path.join(repo, "sources/S07_container_moves/02_evidence/discovery"))
    import p2_2_discover as disc
    disc.run(spark, "S07_container_moves", "all", root=repo)
    import csv as _csv
    rows = {r["table"].split(".")[-1]: r for r in _csv.DictReader(open(os.path.join(repo, "sources/S07_container_moves/02_evidence/discovery/tables.csv")))}
    assert rows["legs_bkp_2025"]["role"] == "staging"
    assert rows["containers"]["key"] == "CNTR_NO"
    links = list(_csv.DictReader(open(os.path.join(repo, "sources/S07_container_moves/02_evidence/discovery/links.csv"))))
    assert any(l["dep_column"] == "CNTR_NO" and l["status"] == "fk" and "normalisation" in l["note"] for l in links)


def test_card_runner_validates_and_retries(repo):
    from discovery import card_runner as cr
    calls = []

    def fake_llm(system, user):
        calls.append(user)
        cid = re.search(r"# Card (T-\d+)", user).group(1)
        if len(calls) == 1:
            return "```yaml\ncard: %s\nrole: wizard\n```" % cid               # invalid first answer -> retry
        return ("```yaml\ncard: %s\nrole: master\nbusiness_object: Container\ngrain_key: [CNTR_NO]\naccept_links: []\n"
                "reject_links: []\nload_to_silver: yes\nreason: Container master referenced by legs.\nevidence: []\nraise_upstream: null\n```" % cid)
    res = cr.run("S07_container_moves", fake_llm, root=repo, max_workers=1, only=["T-004"])
    assert res[0]["ok"] and len(calls) == 2
    assert os.path.exists(os.path.join(repo, "sources/S07_container_moves/02_evidence/discovery/cards/T-004.result.yaml"))


# ---------------------------------------------------------------- review fixes: validator keys/evidence
def test_pk_column_must_have_pk_role(repo):
    p = os.path.join(repo, S07)
    _edit(p, lambda d: next(c for c in d["tables"][0]["columns"] if c["target"] == "shipment_leg_sk").update(key_role="none"))
    r = _val(repo, S07)
    assert any("in primary_key but key_role is 'none'" in e for e in r.errors)


def test_bk_column_must_have_bk_role(repo):
    p = os.path.join(repo, S07)
    _edit(p, lambda d: next(c for c in d["tables"][0]["columns"] if c["target"] == "leg_seq").update(key_role="none"))
    assert any("in business_key but key_role is 'none'" in e for e in _val(repo, S07).errors)


def test_superseded_evidence_does_not_support_a_key(repo):
    reg = os.path.join(repo, "sources/S07_container_moves/02_evidence/evidence_register.csv")
    rows = list(csv.DictReader(open(reg)))
    for r in rows:
        if r["evidence_id"] == "E-0004":
            r.update(status="superseded", confidence="high", origin="document", corroborated_by="")
    w = csv.DictWriter(open(reg, "w", newline=""), fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    p = os.path.join(repo, S07)
    def fn(d):
        c = next(c for c in d["tables"][0]["columns"] if c["target"] == "leg_seq")
        c["provenance"] = {"evidence": ["E-0004"]}
    _edit(p, fn)
    r = _val(repo, S07)
    assert any("leg_seq" in e and "no valid support" in e for e in r.errors)


def test_profiling_path_must_exist_to_count(repo):
    p = os.path.join(repo, S07)
    def fn(d):
        c = next(c for c in d["tables"][0]["columns"] if c["target"] == "leg_seq")
        c["provenance"] = {"evidence": [], "profiling": "02_evidence/profiling/does_not_exist.json"}
    _edit(p, fn)
    assert any("leg_seq" in e and "no valid support" in e for e in _val(repo, S07).errors)


# ---------------------------------------------------------------- review fixes: CP5 QA coverage (pure)
def _qa_summary(repo, checks):
    d = os.path.join(repo, "sources/S07_container_moves/05_build/qa_results")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "summary.json"), "w") as f:
        json.dump({"checks": checks}, f)


def test_qa_rules_required_checks():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from lib import qa_rules
    t = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), S07)))["tables"][0]
    req = qa_rules.required_checks(t)
    assert {"QA-01", "QA-02", "QA-03", "QA-04", "QA-05", "QA-07"} <= set(req) and "QA-06" not in req


def test_cp5_gate_needs_every_applicable_check(repo):
    tbl = "dev.silver.slv_cnt_shipment_leg"
    _qa_summary(repo, [{"check": "QA-02 schema", "table": tbl, "status": "pass"}, {"check": "QA-03 pk", "table": tbl, "status": "pass"}])
    for cp in ("CP1_source_brief", "CP2_evidence", "CP4_sttm", "CP4b_business_logic", "CP5_code_qa"):
        _set_cp(repo, "S07_container_moves", cp)
    errors, _ = vg.check(repo)
    miss = [e for e in errors if "QA missing for slv_cnt_shipment_leg" in e]
    assert miss and all(x in miss[0] for x in ("QA-01", "QA-04", "QA-05", "QA-07"))
    _qa_summary(repo, [{"check": f"QA-0{i} x", "table": tbl, "status": "pass"} for i in (1, 2, 3, 4, 5, 7)])
    errors, _ = vg.check(repo)
    assert not any("QA missing" in e or "QA not passing" in e for e in errors)
    _qa_summary(repo, [{"check": f"QA-0{i} x", "table": tbl, "status": "error" if i == 5 else "pass"} for i in (1, 2, 3, 4, 5, 7)])
    errors, _ = vg.check(repo)
    assert any("QA not passing" in e and "QA-05=error" in e for e in errors)


# ---------------------------------------------------------------- review fixes: non-destructive codegen
def test_codegen_keeps_todo_work_and_flags_spec_changes(repo, tmp_path):
    import p5_1_gen_notebook as g
    doc = yaml.safe_load(open(os.path.join(repo, S07)))
    t = doc["tables"][0]
    nb = str(tmp_path / "nb.py")
    assert g.write_notebook(doc, t, nb)["action"] == "created"
    with open(nb) as f:
        s = f.read().replace("df = df  # replace", "df = df.withColumn('eta_ts', F.lit(None))  # MY WORK")
    with open(nb, "w") as f:
        f.write(s)
    assert g.write_notebook(doc, t, nb)["action"] == "unchanged"
    t["columns"][-1]["transform"] = "NEW FORMULA"
    rep = g.write_notebook(doc, t, nb)
    s = open(nb).read()
    assert "MY WORK" in s and "REVIEW(STTM changed)" in s and "NEW FORMULA" in s and rep["todo_review"] == ["derived"]
    with open(nb, "w") as f:
        f.write(s.replace('"catalog", "dev"', '"catalog", "prod"'))
    rep = g.write_notebook(doc, t, nb)
    assert rep["generated_hand_edited"] == ["parameters"] and os.path.exists(nb + ".bak")
    s = open(nb).read()
    assert '"catalog", "dev"' in s and "MY WORK" in s
    assert g.write_notebook(doc, t, nb, dry_run=True)["action"] == "unchanged"


def test_gate_blocks_review_blocks_in_notebooks(repo):
    d = os.path.join(repo, "sources/S07_container_moves/05_build")
    with open(os.path.join(d, "nb_x.py"), "w") as f:
        f.write("# Databricks notebook source\n# COMMAND ----------\n# TODO(genie): derived\n# REVIEW(STTM changed): x\n")
    for cp in ("CP1_source_brief", "CP2_evidence", "CP4_sttm", "CP4b_business_logic", "CP5_code_qa"):
        _set_cp(repo, "S07_container_moves", cp)
    errors, _ = vg.check(repo)
    assert any("REVIEW blocks" in e for e in errors)


# ---------------------------------------------------------------- review fixes: SCD2 timeline + QA-06 (needs pyspark)
pyspark_missing = __import__("importlib").util.find_spec("pyspark") is None


@pytest.fixture(scope="module")
def spark():
    from pyspark.sql import SparkSession
    s = (SparkSession.builder.master("local[1]").config("spark.ui.enabled", "false")
         .config("spark.sql.shuffle.partitions", "1").getOrCreate())
    yield s


def _rows(df):
    return sorted((r["k"], str(r["effective_from"])[:10], r["v"], str(r["effective_to"])[:10] if r["effective_to"] else None, r["is_current"])
                  for r in df.collect())


@pytest.mark.skipif(pyspark_missing, reason="pyspark not installed")
def test_scd2_late_arriving_out_of_order_and_corrections(spark):
    from datetime import datetime as dt
    from lib.load_patterns import scd2_timeline
    sch = "k string, v string, effective_from timestamp, effective_to timestamp, is_current boolean"
    existing = spark.createDataFrame([("A", "v1", dt(2026, 1, 1), dt(2026, 3, 1), False), ("A", "v3", dt(2026, 3, 1), None, True)], sch)
    incoming = spark.createDataFrame([
        ("A", "v2", dt(2026, 2, 1)),      # late-arriving, between v1 and v3
        ("A", "v0", dt(2025, 12, 1)),     # earlier than all history
        ("A", "v3x", dt(2026, 4, 1)),     # no change vs the (corrected) previous version -> dropped
        ("A", "v4", dt(2026, 5, 1)),      # newest
        ("A", "v3x", dt(2026, 3, 1)),     # correction of a stored version
        ("B", "b2", dt(2026, 2, 1)), ("B", "b1", dt(2026, 1, 1)),   # new key, out of order in one batch
    ], "k string, v string, effective_from timestamp")
    out = _rows(scd2_timeline(existing, incoming, ["k"], ["v"]))
    assert out == [
        ("A", "2025-12-01", "v0", "2026-01-01", False), ("A", "2026-01-01", "v1", "2026-02-01", False),
        ("A", "2026-02-01", "v2", "2026-03-01", False), ("A", "2026-03-01", "v3x", "2026-05-01", False),
        ("A", "2026-05-01", "v4", None, True),
        ("B", "2026-01-01", "b1", "2026-02-01", False), ("B", "2026-02-01", "b2", None, True)]
    with pytest.raises(ValueError):
        scd2_timeline(None, spark.createDataFrame([("C", "c", None)], "k string, v string, effective_from timestamp"), ["k"], ["v"])


@pytest.mark.skipif(pyspark_missing, reason="pyspark not installed")
def test_qa06_detects_inverted_and_wrong_current(spark):
    from datetime import datetime as dt
    from lib import qa_checks as qa
    sch = "k string, v string, effective_from timestamp, effective_to timestamp, is_current boolean"
    # what the OLD scd2 produced for a late record: older row marked current, inverted period on the closed row
    spark.createDataFrame([("A", "v3", dt(2026, 3, 1), dt(2026, 2, 1), False), ("A", "v2", dt(2026, 2, 1), None, True)], sch) \
        .createOrReplaceTempView("bad_scd2")
    t = {"load_pattern": "scd2", "business_key": ["k"], "columns": []}
    r = qa.qa06_scd2_validity(spark, t, "bad_scd2")
    assert r["status"] == "fail" and "inverted=1" in r["evidence"] and "bad_current=1" in r["evidence"]
    spark.createDataFrame([("A", "v2", dt(2026, 2, 1), dt(2026, 3, 1), False), ("A", "v3", dt(2026, 3, 1), None, True)], sch) \
        .createOrReplaceTempView("good_scd2")
    assert qa.qa06_scd2_validity(spark, t, "good_scd2")["status"] == "pass"


@pytest.mark.skipif(pyspark_missing, reason="pyspark not installed")
def test_qa_runner_reports_checks_it_cannot_run(spark):
    from lib import qa_checks as qa
    t = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), S07)))["tables"][0]
    cols = ", ".join(f"cast(null as string) as {c['target']}" for c in t["columns"])
    spark.sql(f"select {cols}").createOrReplaceTempView("slv_cnt_shipment_leg")
    res = qa.run_table_checks(spark, t, "slv_cnt_shipment_leg", bronze_count=None, entity_tables=None)
    by = {r["check"].split()[0]: r for r in res}
    assert by["QA-01"]["status"] == "error" and "bronze_count" in by["QA-01"]["evidence"]
    assert by["QA-05"]["status"] == "error" and "ENTITY_TABLES" in by["QA-05"]["evidence"]



# ---------------------------------------------------------------- second review: bugs
def test_fk_direction_is_checked(repo):
    p = os.path.join(repo, "registry/ontology/business.yaml")
    _edit(p, lambda b: b["relationships"]["R10"].update(subject="Container", object="ShipmentLeg"))   # now Container is the N side
    assert _has(_val(repo, S07), "FK points the wrong way")
    _edit(p, lambda b: b["relationships"]["R10"].update(cardinality="1:N"))                           # 1:N object->subject: OK again
    assert not _has(_val(repo, S07), "FK points the wrong way")


def test_directed_pairs():
    rel = {"a": {"subject": "Buyer", "object": "Department", "cardinality": "N:1"},
           "b": {"subject": "Buyer", "object": "Supplier", "cardinality": "1:N"},
           "c": {"subject": "X", "object": "Y", "cardinality": "1:1"}, "d": {"subject": "P", "object": "Q", "cardinality": "N:M"}}
    assert vs.directed_pairs(rel) == {("Buyer", "Department"), ("Supplier", "Buyer"), ("X", "Y"), ("Y", "X")}


def test_cp1_pack_counts_old_versions(repo):
    p = pkm.build("S07_container_moves", "CP1_source_brief", repo)
    m = next(x for x in p["metrics"] if x["label"] == "Duplicates / old versions")
    assert m["value"].endswith("/ 1")


def test_business_rule_id_in_generated_notebook():
    import p5_1_gen_notebook as g
    doc = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), S07)))
    txt = g.render(doc, doc["tables"][0])
    assert "BUSINESS LOGIC BR-LOGI-001" in txt and "{c.get" not in txt


def test_global_reset_cascades_to_all_sources(repo):
    def fn(d):
        d["global_checkpoints"]["CP3_central_model"].update(status="approved", approved_by="x", date="d", pr=1)
        for s_ in d["sources"]:
            s_["checkpoints"]["CP4_sttm"].update(status="approved")
            s_["checkpoints"]["CP1_source_brief"].update(status="approved")
    _edit(os.path.join(repo, "registry/sources.yaml"), fn)
    ch = fb.reset("global", ["CP3_central_model", "CP3b_key_rules"], repo)
    assert "CP3_central_model" in ch and "S01_buyer_master.CP4_sttm" in ch and "S07_container_moves.CP4_sttm" in ch
    reg = yaml.safe_load(open(os.path.join(repo, "registry/sources.yaml")))
    assert all(s_["checkpoints"]["CP1_source_brief"]["status"] == "approved" for s_ in reg["sources"])   # earlier CPs untouched


# ---------------------------------------------------------------- second review: ids, unknown member
def test_feedback_ids_are_scoped_and_unique(repo):
    ids = {fb.next_id(repo, "S07_container_moves") for _ in range(200)}
    assert len(ids) == 200 and all(re.match(r"^FB-S07-[a-z2-9]{4}$", i) for i in ids)
    assert fb.next_id(repo, "global").startswith("FB-GLB-")


def test_gate_flags_duplicate_feedback_ids(repo):
    src = os.path.join(repo, "sources/S07_container_moves/02_evidence/feedback/CP2_evidence/FB-0001.yaml")
    shutil.copy(src, os.path.join(repo, "sources/S07_container_moves/01_intake/feedback/FB-0001.yaml"))
    os.makedirs(os.path.join(repo, "sources/S07_container_moves/01_intake/feedback/CP1_source_brief"), exist_ok=True)
    shutil.move(os.path.join(repo, "sources/S07_container_moves/01_intake/feedback/FB-0001.yaml"),
                os.path.join(repo, "sources/S07_container_moves/01_intake/feedback/CP1_source_brief/FB-0001.yaml"))
    errors, _ = vg.check(repo)
    assert any("id FB-0001 is used by 2 files" in e for e in errors)


def test_unknown_sk_matches_spark_sha2():
    from lib.keys import UNKNOWN_SK
    import hashlib as _h
    assert UNKNOWN_SK == _h.sha256(b"#UNKNOWN").hexdigest()


@pytest.mark.skipif(pyspark_missing, reason="pyspark not installed")
def test_unknown_member_row_and_qa(spark):
    from datetime import datetime as dt
    from lib.keys import UNKNOWN_SK
    from lib.load_patterns import unknown_member_row
    from lib import qa_checks as qa
    from pyspark.sql import functions as F
    assert spark.range(1).select(F.sha2(F.lit("#UNKNOWN"), 256)).first()[0] == UNKNOWN_SK
    sch = "buyer_sk string, buyer_id string, n int, effective_from timestamp, effective_to timestamp, is_current boolean, _src_system string"
    t = {"surrogate_key": {"column": "buyer_sk"}, "primary_key": ["buyer_sk"], "business_key": ["buyer_id"], "load_pattern": "scd2",
         "columns": [{"target": "buyer_sk", "nullable": False, "rule": "technical"}, {"target": "buyer_id", "nullable": False, "rule": "direct"},
                     {"target": "n", "nullable": False, "rule": "direct"}]}
    real = spark.createDataFrame([("a", "B1", 1, dt(2026, 1, 1), None, True, "S01")], sch)
    unk = spark.createDataFrame([unknown_member_row(real.schema, t)], real.schema)
    row = unk.first()
    assert row["buyer_sk"] == UNKNOWN_SK and row["buyer_id"] == "#UNKNOWN" and row["n"] is None and row["is_current"]
    real.unionByName(unk).createOrReplaceTempView("mst_buyer")
    assert qa.qa04_not_null(spark, t, "mst_buyer")["status"] == "pass"            # unknown row's NULLs are excluded
    assert qa.qa01_row_count_reconciliation(spark, t, "mst_buyer", 1)["status"] == "pass"
    child = {"columns": [{"target": "buyer_sk", "fk": {"entity": "Buyer", "column": "buyer_sk", "orphan_policy": "reject"}}]}
    spark.createDataFrame([(UNKNOWN_SK,), ("a",)], "buyer_sk string").createOrReplaceTempView("child_t")
    r = qa.qa05_fk_integrity(spark, child, "child_t", {"Buyer": "mst_buyer"})
    assert r["status"] == "fail" and "unknown_member_not_allowed" in r["evidence"]   # policy 'reject' must not use it
    child["columns"][0]["fk"]["orphan_policy"] = "unknown_member"
    assert qa.qa05_fk_integrity(spark, child, "child_t", {"Buyer": "mst_buyer"})["status"] == "pass"


@pytest.mark.skipif(pyspark_missing, reason="pyspark not installed")
def test_scd2_column_order_puts_history_before_audit(spark):
    from datetime import datetime as dt
    from lib.load_patterns import scd2_timeline
    inc = spark.createDataFrame([("A", "v", dt(2026, 1, 1), "S01")], "k string, v string, effective_from timestamp, _src_system string")
    assert scd2_timeline(None, inc, ["k"], ["v"]).columns == ["k", "v", "effective_from", "effective_to", "is_current", "_src_system"]


# ---------------------------------------------------------------- survivorship (shared masters)
def test_staging_names_and_spec():
    from lib.survivorship import staging_table, staging_spec
    from lib import qa_rules
    assert staging_table("slv_mst_part", "S03_part_catalogue") == "slv_stg_mst_part_s03"
    t = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), S01)))["tables"][0]
    sp = staging_spec(t)
    names = [c["target"] for c in sp["columns"]]
    assert "buyer_sk" not in names and "effective_to" not in names and sp["primary_key"] == ["buyer_id"]
    assert "QA-06" not in qa_rules.required_checks(sp)                    # staging is current state, no SCD2


def test_master_source_qa_is_checked_on_staging(repo):
    from lib import qa_rules
    doc = yaml.safe_load(open(os.path.join(repo, S01)))
    names = [n for n, _ in qa_rules.expected_results(doc)]
    assert names == ["slv_stg_mst_buyer_s01"]


def test_codegen_writes_masters_to_staging():
    import p5_1_gen_notebook as g
    doc = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), S01)))
    txt = g.render(doc, doc["tables"][0])
    assert "slv_stg_mst_buyer_s01" in txt and "load_staging(" in txt and "QT = staging_spec(T)" in txt
    assert "effective_from: change timestamp" in txt                     # the SCD2 change time is now a TODO


def test_cp5_needs_master_build_qa(repo):
    for cp in ("CP1_source_brief", "CP2_evidence", "CP4_sttm", "CP5_code_qa"):
        _set_cp(repo, "S01_buyer_master", cp)
    errors, _ = vg.check(repo)
    assert any("master build QA missing: masters/slv_mst_buyer" in e for e in errors)


def test_ontology_requires_survivorship_for_multi_source_entities(repo):
    d = os.path.join(repo, "sources/S09_hr_feed/04_mapping")
    os.makedirs(d)
    shutil.copy(os.path.join(repo, S01), os.path.join(d, "sttm.yaml"))
    _edit(os.path.join(d, "sttm.yaml"), lambda x: x.update(source_id="S09_hr_feed"))
    errs, _ = oc.check(repo)
    assert any("entity Buyer is mapped by 2 sources" in e for e in errs)
    _edit(os.path.join(d, "sttm.yaml"), lambda x: _col(x, "buyer_name").update(type="INT"))
    errs, _ = oc.check(repo)
    assert any("column buyer_name has different types" in e for e in errs)


def test_master_build_generator(repo):
    import p5_4_gen_master_build as mb
    out = mb.render("Buyer", {"target_table": "slv_mst_buyer"}, ["S01_buyer_master"])
    assert "build_master(" in out and "qa_results/summary.json" in out and "ENTITY_TABLES" in out


@pytest.mark.skipif(pyspark_missing, reason="pyspark not installed")
def test_survive_priority_recency_and_nulls(spark):
    from datetime import datetime as dt
    from lib.survivorship import survive
    rows = [  # part P1 from three sources
        ("P1", "Bolt M8 (catalogue)", 1.0, "S03_part_catalogue", dt(2026, 1, 1)),
        ("P1", "bolt m8", 2.0, "S01_buyer_master", dt(2026, 3, 1)),
        ("P1", None, 3.0, "S05_erp", dt(2026, 2, 1)),
        ("P2", None, None, "S03_part_catalogue", dt(2026, 1, 1)),      # catalogue has no description for P2
        ("P2", "nut", None, "S01_buyer_master", dt(2026, 1, 5)),
    ]
    staged = spark.createDataFrame(rows, "part_number string, description string, weight_kg double, _src_id string, _src_changed_ts timestamp")
    rules = {"default": "most_recent_update", "source_priority": ["S03_part_catalogue", "S01_buyer_master"],
             "attributes": {"description": {"priority": ["S03_part_catalogue", "S01_buyer_master"]}}}
    out = {r["part_number"]: r for r in survive(staged, ["part_number"], ["description", "weight_kg"], rules).collect()}
    assert out["P1"]["description"] == "Bolt M8 (catalogue)"             # priority beats recency
    assert out["P1"]["weight_kg"] == 2.0                                 # most recent non-null (S01, March)
    assert str(out["P1"]["effective_from"])[:10] == "2026-03-01"
    assert out["P2"]["description"] == "nut"                             # a NULL never wins
    assert out["P2"]["weight_kg"] is None
    assert out["P1"]["_survivor"] == "description=S03_part_catalogue;weight_kg=S01_buyer_master"


# ---------------------------------------------------------------- composite foreign keys
def test_composite_link_candidates_header_line():
    ekko = {"row_count": 600, "columns": [_p("MANDT", nd=2), _p("EBELN", nd=300), _p("LIFNR", nd=50), _p("BEDAT", "date")]}
    ekpo = {"row_count": 1200, "columns": [_p("MANDT", nd=2), _p("EBELN", nd=300), _p("EBELP", nd=3), _p("MATNR", nd=400), _p("MENGE", "num")]}
    tables = {"s.ekko": ekko, "s.ekpo": ekpo}
    keys = {"s.ekko": {"keys": [["MANDT", "EBELN"]], "best": ["MANDT", "EBELN"]}, "s.ekpo": {"keys": [["MANDT", "EBELN", "EBELP"]]}}
    c = dcore.composite_link_candidates(tables, keys, {**B, "composite_min_name_score": 0.5})
    assert any(x["dep_table"] == "s.ekpo" and x["dep_column"] == "MANDT+EBELN" and x["ref_column"] == "MANDT+EBELN" for x in c)
    assert not any("MATNR" in x["dep_column"] for x in c)
    assert dcore.link_cols("MANDT+EBELN") == ["MANDT", "EBELN"]


def test_classify_line_by_structure_and_header_by_children():
    ekpo = {"row_count": 1200, "columns": [_p("MANDT", nd=2), _p("EBELN", nd=300), _p("EBELP", nd=3), _p("MATNR", nd=400)]}
    r = dcore.classify("ekpo", ekpo, ["MANDT", "EBELN", "EBELP"], [{"dep_column": "MANDT+EBELN"}], [], B)
    assert r["role"] == "transaction_line"
    ekko = {"row_count": 600, "columns": [_p("MANDT", nd=2), _p("EBELN", nd=300), _p("LIFNR", nd=50), _p("BEDAT", "date")]}
    r = dcore.classify("ekko", ekko, ["MANDT", "EBELN"], [], [{"dep_column": "MANDT+EBELN", "dep_unique": False}], B)
    assert r["role"] == "transaction_header"


def test_find_keys_prefers_shared_names():
    prof = [_p("MANDT", nd=2), _p("EBELN", nd=300), _p("EBELP", nd=3), _p("MATNR", nd=400)]
    truth = {frozenset(["MANDT", "EBELN", "EBELP"]), frozenset(["MATNR", "EBELN", "EBELP"])}
    r = dcore.find_keys(prof, 1200, lambda cols: frozenset(cols) in truth, {**B, "max_key_size": 3}, shared={"MANDT", "EBELN", "EBELP"})
    assert r["best"] == ["MANDT", "EBELN", "EBELP"]                    # table column order, shared names preferred


def _sap_repo(repo):
    """Add a fake SAP purchasing source with a header and a line table (composite keys) to a repo copy."""
    bp = os.path.join(repo, "registry/ontology/business.yaml")
    def fb_(b):
        b["business_objects"]["PurchaseOrder"] = {"kind": "event", "domain": "PROC", "definition": "An order to a supplier.", "synonyms": ["po", "ekko"]}
        b["business_objects"]["PurchaseOrderLine"] = {"kind": "event", "domain": "PROC", "definition": "One item of an order.", "synonyms": ["po line", "ekpo"]}
        b["relationships"]["R18"] = {"subject": "PurchaseOrderLine", "verb": "part_of", "object": "PurchaseOrder", "cardinality": "N:1"}
    _edit(bp, fb_)
    d = os.path.join(repo, "sources/S20_sap_po")
    os.makedirs(os.path.join(d, "02_evidence"))
    os.makedirs(os.path.join(d, "04_mapping"))
    with open(os.path.join(d, "02_evidence/evidence_register.csv"), "w") as f:
        f.write("evidence_id,claim,about_type,about,origin,file_id,location,doc_type,confidence,status,corroborated_by,notes\n"
                "E-0001,MANDT+EBELN unique in EKKO.,key,ekko,bronze_profile,,02_evidence/discovery/keys.csv#ekko,,high,confirmed_by_bronze,02_evidence/discovery/keys.csv#ekko,\n")
    def col(name, typ="STRING", role="BK", src=None, rule="direct", **kw):
        return {"target": name, "type": typ, "nullable": False, "rule": rule, "source": src, "transform": src, "key_role": role,
                "description": f"{name} column.", "provenance": {"evidence": ["E-0001"]} if rule != "technical" else None, "confidence": "high", **kw}
    hdr = {"target_table": "slv_po_header", "business_object": "PurchaseOrder", "data_class": "event", "target_kind": "process",
           "conformed_entity": None, "grain": "One row per client and order.", "load_pattern": "merge", "scd_type": None,
           "primary_key": ["po_header_sk"], "business_key": ["client", "po_number"],
           "surrogate_key": {"column": "po_header_sk", "method": "hash", "of": ["client", "po_number"]}, "partition_by": None,
           "sources": [{"table": "bronze.sap.ekko", "alias": "h", "filter": None, "dedup": None}], "joins": None,
           "columns": [col("po_header_sk", role="PK", rule="technical", src=None), col("client", src="h.MANDT"), col("po_number", src="h.EBELN")]}
    line = {**hdr, "target_table": "slv_po_line", "business_object": "PurchaseOrderLine", "grain": "One row per client, order, and item.",
            "primary_key": ["po_line_sk"], "business_key": ["client", "po_number", "po_item"],
            "surrogate_key": {"column": "po_line_sk", "method": "hash", "of": ["client", "po_number", "po_item"]},
            "sources": [{"table": "bronze.sap.ekpo", "alias": "l", "filter": None, "dedup": None}],
            "columns": [col("po_line_sk", role="PK", rule="technical", src=None), col("client", src="l.MANDT"), col("po_number", src="l.EBELN"),
                        col("po_item", src="l.EBELP"),
                        col("po_header_sk", role="FK", rule="lookup", src="l.MANDT, l.EBELN",
                            fk={"table": "slv_po_header", "column": "po_header_sk", "cardinality": "N:1", "orphan_policy": "reject",
                                "lookup_on": ["l.MANDT", "l.EBELN"]})]}
    line["columns"][-1]["transform"] = "lookup slv_po_header on (client, po_number)"
    doc = {"source_id": "S20_sap_po", "source_system": "SAP", "version": "0.1", "status": "draft", "owner": "x", "notes": "test",
           "tables": [hdr, line]}
    p = os.path.join(d, "04_mapping/sttm.yaml")
    with open(p, "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False)
    return "sources/S20_sap_po/04_mapping/sttm.yaml"


def test_composite_fk_to_same_source_table_is_valid(repo):
    rel = _sap_repo(repo)
    r = _val(repo, rel)
    assert r.ok, r.errors


def test_composite_fk_rules(repo):
    rel = _sap_repo(repo)
    p = os.path.join(repo, rel)
    fk = lambda d: next(c for c in d["tables"][1]["columns"] if c["target"] == "po_header_sk")["fk"]
    _edit(p, lambda d: fk(d).update(lookup_on=["l.EBELN"]))
    assert _has(_val(repo, rel), "lookup_on has 1 item(s)")
    _edit(p, lambda d: fk(d).pop("lookup_on"))
    assert _has(_val(repo, rel), "composite business key")
    _edit(p, lambda d: fk(d).update(lookup_on=["l.MANDT", "l.EBELN"], orphan_policy="unknown_member"))
    assert _has(_val(repo, rel), "only for shared masters")
    _edit(p, lambda d: fk(d).update(orphan_policy="reject", table="slv_nope"))
    assert _has(_val(repo, rel), "not a target_table in this STTM")
    _edit(p, lambda d: fk(d).update(table="slv_po_header", entity="Part"))
    assert _has(_val(repo, rel), "exactly one of 'entity'")


def test_codegen_generates_composite_lookup(repo):
    import p5_1_gen_notebook as g
    rel = _sap_repo(repo)
    doc = yaml.safe_load(open(os.path.join(repo, rel)))
    txt = g.render(doc, doc["tables"][1])
    assert "lookup_sk(df, spark.table(f'{catalog}.{silver_schema}.slv_po_header')" in txt
    assert "['client', 'po_number']" in txt and "orphan_policy='reject'" in txt and "rejected_count" in txt
    s07 = yaml.safe_load(open(os.path.join(repo, S07)))
    t7 = g.render(s07, s07["tables"][0])
    assert "spark.table(ENTITY_TABLES['Container'])" in t7 and "container_sk: lookup" not in t7   # generated, not a TODO


@pytest.mark.skipif(pyspark_missing, reason="pyspark not installed")
def test_lookup_sk_composite_policies(spark):
    from lib.keys import lookup_sk, UNKNOWN_SK
    parent = spark.createDataFrame([("100", "4500", "H1", True), ("200", "4500", "H2", True), ("100", "4600", "OLD", False), ("100", "4600", "H3", True)],
                                   "client string, po_number string, po_header_sk string, is_current boolean")
    child = spark.createDataFrame([("100", "4500", 1), ("200", "4500", 2), ("100", "4600", 3), ("300", "4500", 4), (None, "4500", 5)],
                                  "MANDT string, EBELN string, i int")
    on = ["MANDT", "EBELN"]
    df, n = lookup_sk(child, parent, on, ["client", "po_number"], "po_header_sk", "po_header_sk", "reject")
    got = {r["i"]: r["po_header_sk"] for r in df.collect()}
    assert n == 1 and got == {1: "H1", 2: "H2", 3: "H3", 5: None}          # same EBELN, different client -> different header; current row only
    df, n = lookup_sk(child, parent, on, ["client", "po_number"], "po_header_sk", "po_header_sk", "unknown_member")
    assert n == 0 and {r["i"]: r["po_header_sk"] for r in df.collect()}[4] == UNKNOWN_SK
    with pytest.raises(ValueError):
        lookup_sk(child, parent, ["MANDT"], ["client", "po_number"], "po_header_sk", "x")


@pytest.mark.skipif(not os.environ.get("RUN_SPARK"), reason="set RUN_SPARK=1 to run the Spark composite discovery test")
def test_discovery_composite_keys_sap_like(repo, tmp_path):
    from pyspark.sql import SparkSession
    spark = (SparkSession.builder.master("local[2]").config("spark.sql.warehouse.dir", str(tmp_path / "wh"))
             .config("spark.ui.enabled", "false").config("spark.sql.shuffle.partitions", "2").getOrCreate())
    sys.path.insert(0, repo)
    from tests.fixtures.make_bronze_s07 import make_sap_po
    make_sap_po(spark, "sap_t")
    def fn(d):
        d["sources"].append({"id": "S20_sap_po", "name": "SAP", "domains": ["PROC"], "processes": ["P-PROC-02"],
                             "business_objects": [], "bronze_schema": "sap_t", "checkpoints": {}})
    _edit(os.path.join(repo, "registry/sources.yaml"), fn)
    import p2_2_discover as disc
    disc.run(spark, "S20_sap_po", "all", root=repo)
    import csv as _csv
    base = os.path.join(repo, "sources/S20_sap_po/02_evidence/discovery")
    t = {r["table"].split(".")[-1]: r for r in _csv.DictReader(open(os.path.join(base, "tables.csv")))}
    assert t["ekko"]["key"] == "MANDT + EBELN" and t["ekko"]["role"] == "transaction_header"
    assert t["ekpo"]["key"] == "MANDT + EBELN + EBELP" and t["ekpo"]["role"] == "transaction_line"
    assert t["eket"]["key"] == "MANDT + EBELN + EBELP + ETENR"
    links = {(l["dep_table"].split(".")[-1], l["dep_column"], l["ref_table"].split(".")[-1]) for l in _csv.DictReader(open(os.path.join(base, "links.csv"))) if l["status"] == "fk"}
    assert ("ekpo", "MANDT+EBELN", "ekko") in links and ("eket", "MANDT+EBELN+EBELP", "ekpo") in links


# ---------------------------------------------------------------- navigator (00_start_here)
def _no_clarify(repo, sid):
    import x_clarify as qz
    import x_navigator as nav
    for _ in range(20):
        if qz.skip(sid, reason="test", root=repo) == "Nothing to clarify.":
            break
    assert not qz.needs(sid, nav.steps(sid, repo)["checkpoint"], repo)


def test_navigator_status_and_next(repo):
    import x_navigator as nav
    nx0 = nav.next_step(nav.steps("S07_container_moves", repo))
    assert nx0["who"] == "agent" and nx0["how"].startswith("@x-clarify kickoff")
    _no_clarify(repo, "S07_container_moves")
    info = nav.steps("S07_container_moves", repo)
    assert info["checkpoint"] == "CP1_source_brief"
    nx = nav.next_step(info)
    assert nx["who"] == "human" and "approve CP1" in nx["step"], nx
    assert "a person" in nav.run("next", "S07_container_moves", repo)
    assert "S07_container_moves" in nav.html("S07_container_moves", repo) and "Needs attention" in nav.html("S07_container_moves", repo)


def test_navigator_runs_next_code_step_and_moves_on(repo):
    import x_navigator as nav
    for f in glob.glob(os.path.join(repo, "sources/S01_buyer_master/01_intake/checkpoint/*")):
        os.remove(f)
    _no_clarify(repo, "S01_buyer_master")
    assert nav.next_step(nav.steps("S01_buyer_master", repo))["how"] == "pack"
    out = nav.run("next", "S01_buyer_master", repo)
    assert "CP1_source_brief" in out
    assert nav.next_step(nav.steps("S01_buyer_master", repo))["who"] == "human"


def test_navigator_new_source_and_later_phases(repo):
    import x_navigator as nav
    assert "must look like" in nav.add_source("bad id", "bronze.x", root=repo)
    msg = nav.add_source("S12_part_catalogue", "bronze.part_cat", root=repo)
    assert "Created" in msg and os.path.isdir(os.path.join(repo, "sources/S12_part_catalogue/02_evidence/discovery"))
    assert nav.next_step(nav.steps("S12_part_catalogue", repo))["how"] == "@x-clarify kickoff for S12_part_catalogue"
    _no_clarify(repo, "S12_part_catalogue")
    nx = nav.next_step(nav.steps("S12_part_catalogue", repo))
    assert nx["how"] == "inventory"
    assert "needs Spark" in nav.run("discover", "S12_part_catalogue", repo)
    for cp in ("CP1_source_brief", "CP2_evidence"):
        _set_cp(repo, "S07_container_moves", cp)
    assert nav.steps("S07_container_moves", repo)["checkpoint"] == "CP3_central_model"


def test_start_here_notebook_is_valid_python_source():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "00_start_here.py")
    s = open(p).read()
    assert s.startswith("# Databricks notebook source")
    compile("\n".join(l for l in s.splitlines() if not l.startswith("# MAGIC")), p, "exec")


# ---------------------------------------------------------------- person input: instructions, feedback, uploads, clarify
def test_instructions_feedback_and_uploads(repo):
    import x_navigator as nav
    sid = "S07_container_moves"
    assert "Type the instruction" in nav.add_instruction(sid, "", root=repo)
    assert "Unknown step" in nav.add_instruction(sid, "Leave the login columns out", "p9-bad", root=repo)
    assert "IN-001" in nav.add_instruction(sid, "Leave the login columns out of silver", "p2-2-bronze-discovery", root=repo)
    assert [i["id"] for i in nav.instructions(sid, repo, "p2-2-bronze-discovery")] == ["IN-001"]
    assert nav.instructions(sid, repo, "p4-1-sttm-author") == []
    out = nav.give_feedback(sid, "ETA text is local port time, not UTC", root=repo)
    assert out.startswith("Saved FB-S07-")
    up = os.path.join(repo, "sources", sid, "uploads")
    assert "No new files" in nav.register_uploads(sid, "feedback", root=repo)
    with open(os.path.join(up, "scope.csv"), "w") as f:
        f.write("table,column,scope\nbronze.container_track.legs,CARRIER_REF,out_of_scope\n")
    with open(os.path.join(up, "notes.txt"), "w") as f:
        f.write("carrier codes are from the 2025 list")
    res = nav.register_uploads(sid, "handover", root=repo)
    assert "handover" in res and os.path.exists(os.path.join(repo, "sources", sid, "01_intake", "handover", "notes.txt"))
    assert "No new files" in nav.register_uploads(sid, "handover", root=repo)      # each file once
    pk = pkm.build(sid, "CP1_source_brief", repo)
    assert any(f.endswith("notes.txt") for f in pk["handover_files"]) and "Instructions" in pk["tables"]


def test_clarify_kickoff_input_record_and_no_loop(repo):
    import x_clarify as qz
    import x_navigator as nav
    sid = "S07_container_moves"
    cp = nav.steps(sid, repo)["checkpoint"]
    assert ("kickoff", cp) in qz.needs(sid, cp, repo)
    qid, path, n = qz.brief(sid, root=repo)
    assert qid == "QZ-CP1-001" and os.path.exists(path) and n <= qz.MAX_Q
    assert qz.brief(sid, root=repo)[0] == qid                                   # rerun: same questionnaire
    assert "waiting for answers" in nav.next_step(nav.steps(sid, repo))["step"]
    nav.add_instruction(sid, "Use LEG_ID", root=repo)                            # no clear intent, unknown name
    assert ("input", "IN-001") in qz.needs(sid, cp, repo)
    q2, p2, _ = qz.brief(sid, "IN-001", root=repo)
    txt = open(p2).read()
    assert "LEG_ID" in txt and "What should change" in txt
    assert os.path.exists(os.path.join(os.path.dirname(p2), "IA-IN-001.yaml"))
    with open(p2.replace(".md", ".answers.yaml"), "w") as f:
        yaml.safe_dump({"answers": [
            {"q": 1, "answer": "LEG_ID is the new name of LEG_NO from release 7", "record_as": "evidence", "about": "legs.LEG_NO"},
            {"q": 2, "answer": "Apply it in the STTM only", "record_as": "instruction", "step": "p4-1-sttm-author"},
            {"q": 3, "answer": "I do not know when release 7 goes live", "record_as": "question"}]}, f)
    out = qz.record(sid, q2, root=repo)
    assert "team_knowledge" in out and "IN-002" in out and "client question" in out
    reg = list(csv.DictReader(open(os.path.join(repo, "sources", sid, "02_evidence", "evidence_register.csv"))))
    assert reg[-1]["origin"] == "team_knowledge" and reg[-1]["confidence"] == "medium"
    left = qz.needs(sid, cp, repo)
    assert ("input", "IN-001") not in left and ("input", "IN-002") not in left  # recorded answers do not ask again
    assert ("kickoff", cp) in left
    assert "Skipped" in qz.skip(sid, qid, "workshop covered it", root=repo)
    assert ("kickoff", cp) not in qz.needs(sid, cp, repo)
    import p1_2_check_context as cc
    assert not [e for e in cc.check(sid, repo, only="evidence")["evidence"] if reg[-1]["evidence_id"] in e]


def test_team_knowledge_cannot_be_high(repo):
    import p1_2_check_context as cc
    p = os.path.join(repo, "sources/S07_container_moves/02_evidence/evidence_register.csv")
    rows = list(csv.DictReader(open(p)))
    r = dict(rows[0], evidence_id="E-9999", origin="team_knowledge", confidence="high", status="unverified", corroborated_by="", file_id="")
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows + [r])
    assert any("E-9999" in e and "medium at most" in e for e in cc.check("S07_container_moves", repo, only="evidence")["evidence"])


# ---------------------------------------------------------------- Unity Catalog metadata, scope, column classes, privacy
def test_declared_keys_links_and_stats():
    from discovery import core
    rows = [{"table": "EKKO", "type": "PRIMARY KEY", "name": "pk", "columns": ["MANDT", "EBELN"]},
            {"table": "ekpo", "type": "FOREIGN KEY", "name": "fk1", "columns": ["MANDT", "EBELN"], "ref_table": "c.s.ekko", "ref_columns": ["MANDT", "EBELN"]}]
    assert core.declared_keys(rows) == {"ekko": [["MANDT", "EBELN"]]}
    dl = core.declared_links(rows, "c.s")
    assert dl[0]["dep_column"] == "MANDT+EBELN" and dl[0]["score"] == 9.0
    prof = {"table": "c.s.t", "columns": [{"column": "ID"}, {"column": "X"}]}
    core.apply_stats(prof, [{"table": "c.s.T", "column": "id", "distinct_count": 100, "num_nulls": 0, "num_rows": 100}])
    assert core.stats_unique(prof["columns"][0]) and not core.stats_unique(prof["columns"][1])


def test_lineage_view_and_related():
    from discovery import core
    ours = ["c.s.legs", "c.s.leg_daily_summary"]
    tl = [{"source_table_full_name": "c.raw.legs_feed", "target_table_full_name": "c.s.legs", "entity_type": "JOB", "job_id": "42"},
          {"source_table_full_name": "c.s.legs", "target_table_full_name": "c.mart.kpi", "entity_type": "NOTEBOOK"}]
    cl = [{"source_table_full_name": "c.s.legs", "target_table_full_name": "c.s.leg_daily_summary"}]
    v = core.lineage_view(tl, cl, ours)
    assert v["upstream_outside"] == ["c.raw.legs_feed"] and "JOB job 42" in v["writers"]["c.s.legs"]
    assert v["readers"]["c.s.legs"] == ["c.mart.kpi"] and v["derived"] == [("c.s.leg_daily_summary", "c.s.legs")]
    rel = core.score_related([{"table_catalog": "c", "table_schema": "x", "table_name": "legs_hist", "name_hit": 1, "key_cols_shared": 2,
                               "shared_columns": ["cntr_no", "shpmt_id"]}], ["c.raw.legs_feed"], {"related_min_score": 2.0})
    assert [r["table"] for r in rel] == ["c.x.legs_hist", "c.raw.legs_feed"]


def test_doc_gaps():
    from discovery import core
    g = core.doc_gaps({"T_LEGS", "VESSELS"}, {"T_LEGS": {"CNTR_NO", "SEAL_NO"}}, {"c.s.legs": {"CNTR_NO"}, "c.s.user_logins": {"USER_ID"}})
    assert g["documented_not_in_bronze"] == ["VESSELS"] and g["in_bronze_not_documented"] == ["c.s.user_logins"]
    assert g["columns"][0]["column"] == "SEAL_NO"


def test_table_scope_rules():
    from discovery import core
    assert core.scope({"role": "staging"}, set())[0] == "out_of_scope"
    assert core.scope({"role": "technical", "role_confidence": "high"}, set())[0] == "out_of_scope"
    assert core.scope({"role": "technical", "role_confidence": "medium"}, set())[0] == "review"
    assert core.scope({"role": "aggregate"}, set())[0] == "derive_instead"
    assert core.scope({"role": "master", "business_object": "Container", "ontology_confidence": "high"}, {"Container"})[0] == "in_scope"
    assert core.scope({"role": "master", "business_object": "Buyer", "ontology_confidence": "high"}, {"Container"})[0] == "review"


@pytest.mark.parametrize("col,kinds,extra,cls,use", [
    ("BOOKED_FROM", {"ip": 0.98}, {}, "application_log", "out_of_scope"),          # content, neutral name
    ("SESSION_ID", {}, {"table_log_names": 4}, "application_log", "out_of_scope"),  # name, log-heavy table
    ("SESSION_ID", {}, {}, "application_log", "review"),                            # name only
    ("CONTACT", {"email": 0.9}, {}, "personal_data", "review"),                     # content, neutral name
    ("TEL", {"phone": 0.95}, {}, "personal_data", "review"),
    ("REF", {}, {"tags": ["class.email_address"]}, "personal_data", "review"),       # UC data classification tag
    ("API_TOKEN", {}, {}, "secret_or_token", "out_of_scope"),
    ("CREATED_BY", {}, {}, "audit_metadata", "technical_only"),
    ("OWNER", {}, {}, "business_attribute", "map"),
])
def test_classify_column_name_content_and_tags(col, kinds, extra, cls, use):
    from discovery import core
    p = {"column": col, "kinds": kinds, "approx_distinct": 50, "null_pct": 0, "avg_len": 12, "family": "str"}
    r = core.classify_column(p, **extra)
    assert (r["column_class"], r["use"]) == (cls, use), r


def _with_column_scope(repo, rows):
    d = os.path.join(repo, "sources/S07_container_moves/02_evidence/discovery")
    with open(os.path.join(d, "column_scope.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["table", "column", "column_class", "scope", "reason", "decided_by"])
        w.writeheader()
        w.writerows(rows)


def test_validator_column_scope_and_privacy(repo):
    doc = yaml.safe_load(open(os.path.join(repo, S07)))
    t = doc["tables"][0]
    src = t["sources"][0]
    tb = ".".join(src["table"].lower().split(".")[-2:])
    c = next(c for c in t["columns"] if re.search(rf"\b{src['alias']}\.\w+", str(c.get("source") or "")) and not c.get("fk"))
    col = re.search(rf"\b{src['alias']}\.(\w+)", str(c["source"])).group(1)
    base = {"table": f"x.{tb}", "column": col, "decided_by": "code", "reason": "test"}
    _with_column_scope(repo, [dict(base, column_class="application_log", scope="out_of_scope")])
    assert _has(_val(repo, S07), "out of scope")
    _with_column_scope(repo, [dict(base, column_class="secret_or_token", scope="out_of_scope")])
    assert _has(_val(repo, S07), "never map secrets")
    _with_column_scope(repo, [dict(base, column_class="personal_data", scope="in_scope")])
    assert _has(_val(repo, S07), "add privacy")

    def fix(d):
        for cc in d["tables"][0]["columns"]:                       # every column that uses the bronze column
            if re.search(rf"\b{src['alias']}\.{col}\b", str(cc.get("source") or "") + " " + str(cc.get("transform") or "")):
                cc["privacy"] = {"class": "personal", "handling": "keep_tagged", "reason": "contact for dispatch"}
    _edit(os.path.join(repo, S07), fix)
    assert not _has(_val(repo, S07), "add privacy")
    _with_column_scope(repo, [dict(base, column_class="personal_data", scope="in_scope_masked")])
    assert _has(_val(repo, S07), "must be mask or hash")


def test_validator_table_scope(repo):
    doc = yaml.safe_load(open(os.path.join(repo, S07)))
    src = doc["tables"][0]["sources"][0]["table"]
    p = os.path.join(repo, "sources/S07_container_moves/02_evidence/discovery/tables.csv")
    rows = list(csv.DictReader(open(p)))
    for r in rows:
        if ".".join(r["table"].lower().split(".")[-2:]) == ".".join(src.lower().split(".")[-2:]):
            r["scope"], r["scope_reason"] = "out_of_scope", "application log"
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    assert _has(_val(repo, S07), "cannot feed silver")

    def ov(d):
        d["tables"][0]["sources"][0]["scope_override"] = {"reason": "client confirmed it is the movement table"}
    _edit(os.path.join(repo, S07), ov)
    assert not _has(_val(repo, S07), "cannot feed silver")


def test_uc_publish_statements(repo):
    from lib import uc_publish
    t = {"grain": "One container move", "business_object": "ContainerMove", "data_class": "event", "load_pattern": "append",
         "primary_key": ["move_sk"],
         "columns": [{"target": "move_sk", "description": "surrogate key"},
                     {"target": "contact_email", "privacy": {"class": "personal", "handling": "mask"}},
                     {"target": "location_sk", "fk": {"entity": "Location", "column": "location_sk"}}]}
    st = uc_publish.statements("dev.silver.slv_evt_move", t, "S07", {"Location": "dev.silver.slv_mst_location"}, repo)
    j = "\n".join(st)
    assert "COMMENT ON TABLE dev.silver.slv_evt_move IS 'One container move'" in j
    assert "SET MASK" in j and "PRIMARY KEY (move_sk)" in j and "REFERENCES dev.silver.slv_mst_location (location_sk)" in j
    assert st.index(next(s for s in st if "SET NOT NULL" in s)) < st.index(next(s for s in st if "PRIMARY KEY" in s))

    class Boom:
        def sql(self, q):
            raise RuntimeError("no privilege")
    rep = uc_publish.publish(Boom(), "dev.silver.t", t, "S07", {}, repo)
    assert rep and all(r["status"] in ("error", "skipped") for r in rep)


def test_uc_harvest_degrades_without_unity_catalog():
    from discovery import uc

    class NoUC:
        class catalog:
            @staticmethod
            def currentCatalog():
                return "spark_catalog"

        def sql(self, q):
            raise RuntimeError("TABLE_OR_VIEW_NOT_FOUND")

        def table(self, n):
            raise RuntimeError("TABLE_OR_VIEW_NOT_FOUND")
    h = uc.harvest(NoUC(), ["s.legs", "s.shipments"], {"lineage_days": 30})
    assert set(h) >= {"tables", "columns", "tags", "constraints", "lineage", "column_lineage", "column_stats"}
    assert all(not v["available"] or v["rows"] == [] for v in h.values())
    assert not h["lineage"]["available"] and "TABLE_OR_VIEW_NOT_FOUND" in h["lineage"]["reason"]


@pytest.mark.skipif(not os.environ.get("RUN_SPARK"), reason="set RUN_SPARK=1 to run the Spark log and personal-data discovery test")
def test_discovery_finds_logs_and_personal_data(repo, tmp_path):
    from pyspark.sql import SparkSession
    spark = (SparkSession.builder.master("local[2]").config("spark.sql.warehouse.dir", str(tmp_path / "wh"))
             .config("spark.ui.enabled", "false").config("spark.sql.shuffle.partitions", "2").getOrCreate())
    sys.path.insert(0, repo)
    from tests.fixtures.make_bronze_s07 import make
    make(spark, "ct_pii")
    sp = os.path.join(repo, "registry/sources.yaml")
    s = open(sp).read().replace("bronze_schema: bronze.container_track", "bronze_schema: ct_pii")
    open(sp, "w").write(s)
    shutil.rmtree(os.path.join(repo, "sources/S07_container_moves/02_evidence/discovery"))
    import p2_2_discover as disc
    disc.run(spark, "S07_container_moves", "all", root=repo)
    base = os.path.join(repo, "sources/S07_container_moves/02_evidence/discovery")
    t = {r["table"].split(".")[-1]: r for r in csv.DictReader(open(os.path.join(base, "tables.csv")))}
    assert t["user_logins"]["scope"] in ("out_of_scope", "review") and t["user_logins"]["role"] == "technical"
    cs = {(r["table"].split(".")[-1], r["column"]): r for r in csv.DictReader(open(os.path.join(base, "column_scope.csv")))}
    assert cs[("shipments", "BOOKED_FROM")]["column_class"] == "application_log"
    assert cs[("shipments", "BOOKED_FROM")]["scope"] == "out_of_scope"
    assert cs[("carrier_contacts", "EMAIL_ADDR")]["column_class"] == "personal_data"
    assert cs[("carrier_contacts", "TEL")]["column_class"] == "personal_data"
    for f in glob.glob(os.path.join(base, "**", "*.*"), recursive=True):    # no raw personal values in any file
        assert "-line.example" not in open(f, encoding="utf-8", errors="ignore").read(), f
    dom = list(csv.DictReader(open(os.path.join(base, "domains.csv"))))
    assert not any("REDACTED" in str(r.get("shared_values", "")).upper() for r in dom)    # redacted columns are not a value domain
    av = list(csv.DictReader(open(os.path.join(base, "metadata", "availability.csv"))))
    assert av and all(r["section"] for r in av)


# ---------------------------------------------------------------- every input is checked against the 3-level ontology
def _ia(repo, text, step="all"):
    import x_clarify as qz
    import x_navigator as nav
    ref = nav.add_instruction("S07_container_moves", text, step, root=repo).split()[1]
    return ref, qz.analyse_ref("S07_container_moves", ref, repo)


def test_input_clear_and_known_gets_no_questions(repo):
    ref, a = _ia(repo, "Leave CARRIER_REF out of silver")
    assert a["intents"] == ["scope"] and a["questions"] == []
    assert any(d["kind"] == "bronze_column" for d in a["levels"]["data"])
    assert a["route"]["earliest_step"] == "p2-2-bronze-discovery" and not a["route"]["rerun_needed"]


def test_input_conflicts_with_instruction_relationship_and_rule(repo):
    _ia(repo, "Leave CARRIER_REF out of silver")
    _, a = _ia(repo, "Include CARRIER_REF in silver")
    assert any(c["with"] == "IN-001" for c in a["conflicts"]) and a["questions"]
    _, a = _ia(repo, "Shipment to leg is many to many")
    assert any(c["with"] == "R09" for c in a["conflicts"]) and any("R09" in x for x in a["route"]["change_requests"])
    _, a = _ia(repo, "Transit days are calculated as ATA minus ATD in hours")
    assert any(c["with"] == "BR-LOGI-001" for c in a["conflicts"]) and {"ATA", "ATD"} <= set(a["unknown"])


def test_input_new_concept_synonym_and_global_rule(repo):
    _, a = _ia(repo, "A consignment can have many containers. Vessel is a new object")
    assert "Vessel" in a["new_concepts"] and any(d["match"] == "Shipment" and d["kind"] == "synonym" for d in a["levels"]["business"])
    _, a = _ia(repo, "Use leading zeros for the container key in all sources")
    assert a["route"]["global"] and a["route"]["earliest_step"] == "p3-1-entity-model"
    assert not any("this source only" in q["q"] for q in a["questions"])          # already said: all sources


def test_input_rerun_of_approved_work_is_asked_and_route_applied(repo):
    import x_clarify as qz
    import x_navigator as nav
    sid = "S07_container_moves"
    _set_cp(repo, sid, "CP1_source_brief")
    _set_cp(repo, sid, "CP2_evidence")
    ref, a = _ia(repo, "Leave CARRIER_REF out of silver", "p2-2-bronze-discovery")
    assert a["route"]["rerun_needed"] and "CP2_evidence" in a["route"]["reset_checkpoints"]
    assert any("Rerun now" in q["q"] for q in a["questions"])
    qid, path, _ = qz.brief(sid, ref, root=repo)
    with open(path.replace(".md", ".answers.yaml"), "w") as f:
        yaml.safe_dump({"answers": [{"q": 1, "answer": "Rerun now", "record_as": "none"}]}, f)
    out = qz.record(sid, qid, root=repo)
    assert "route set" in out
    ins = {i["id"]: i for i in nav.instructions(sid, repo)}
    assert ins[ref]["route_steps"] == ["p2-2-bronze-discovery"] and "scope" in ins[ref]["intents"]


def test_input_file_headers_are_checked_without_reading_values(repo):
    import x_navigator as nav
    sid = "S07_container_moves"
    up = os.path.join(repo, "sources", sid, "uploads")
    with open(os.path.join(up, "carrier_list.csv"), "w") as f:
        f.write("CARRIER_REF,VESSEL_IMO\nCR123,9876543\n")
    nav.register_uploads(sid, "instruction", "New carrier list", root=repo)
    ref = nav.instructions(sid, repo)[-1]["id"]
    import x_clarify as qz
    a = qz.analyse_ref(sid, ref, repo)
    assert any("carrier_list.csv" in n for n in a["files"]) and "VESSEL_IMO" in a["unknown"]
    assert "CR123" not in yaml.safe_dump(a)
