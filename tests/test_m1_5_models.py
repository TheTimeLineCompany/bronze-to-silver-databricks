"""M1.5: model formats, status rules, Mermaid writers and the subset parser."""
import copy

import pytest
import yaml

from b2s import FRAMEWORK_ROOT, models
from fixtures_models import ALL

BUSINESS = yaml.safe_load((FRAMEWORK_ROOT / "registry_template" / "business.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("kind", models.MODELS)
def test_fixture_models_are_valid(kind):
    assert models.validate(kind, ALL[kind], BUSINESS) == []


def test_assumed_needs_assumption_and_unknown_needs_question():
    m = copy.deepcopy(ALL["logical"])
    m["tables"][0]["status"] = "assumed"
    m["tables"][1]["columns"][2].pop("question")
    errs = models.validate("logical", m)
    assert any("assumed needs" in e for e in errs) and any("unknown needs" in e for e in errs)


def test_never_invent_objects():
    m = copy.deepcopy(ALL["conceptual"])
    m["objects"].append({"name": "MovePlan", "status": "known"})
    assert any("change_request" in e for e in models.validate("conceptual", m, BUSINESS))
    m["objects"][-1]["change_request"] = "CR-0001"
    assert models.validate("conceptual", m, BUSINESS) == []


def test_logical_rules():
    m = copy.deepcopy(ALL["logical"])
    m["relationships"][0]["fk_column"] = "nope"
    m["relationships"][1]["cardinality"] = "N:M"
    m["tables"][0]["primary_key"] = []
    errs = models.validate("logical", m)
    assert any("fk_column" in e for e in errs) and any("N:M" in e for e in errs) and any("primary_key" in e for e in errs)


@pytest.mark.parametrize("kind", models.MODELS)
def test_mermaid_round_trip(kind):
    text = models.to_mermaid(kind, ALL[kind])
    g = models.parse_mermaid(text)
    assert g["nodes"] and g["edges"]


def test_logical_mermaid_content():
    text = models.to_mermaid("logical", ALL["logical"])
    assert 'slv_shipment_leg }o--|| slv_shipment : "part of"' in text
    assert 'slv_shipment_leg }o..|| slv_container : "moves (A-0005)"' in text     # assumed -> dotted
    g = models.parse_mermaid(text)
    leg = {a["name"]: a for a in g["nodes"]["slv_shipment_leg"]["attrs"]}
    assert leg["shipment_leg_sk"]["keys"] == ["PK"] and leg["shipment_sk"]["keys"] == ["FK"]
    assert "BK" in leg["plan_id"]["comment"] and "A-0004" in leg["moved_at"]["comment"]
    cards = {(e["from"], e["to"]): e["card"] for e in g["edges"]}
    assert cards[("slv_shipment_leg", "slv_shipment")] == "N:1"


def test_unknown_marked_with_question_mark():
    text = models.to_mermaid("dependencies", ALL["dependencies"])
    assert '"? Terminal operating system"' in text and "class TOS unknown;" in text
    assert "APP -.->" in text


def test_parser_rejects_lines_outside_subset():
    with pytest.raises(models.ModelError):
        models.parse_mermaid("flowchart LR\n  A[\"a\"] ==> B[\"b\"]\n")
