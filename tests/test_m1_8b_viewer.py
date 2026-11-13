"""M1.8b: model viewer — matches Mermaid, no overlaps, readable contrast, cardinality shown, check-views."""
import copy
import json
import re

import pytest

from b2s import models, versions
from b2s.viewer import check_views, layout_graph, overlaps, render_html, write_views
from b2s.viewer import palette
from fixtures_models import ALL


def big_logical(n_tables=40, n_rels=60):
    tables, rels = [], []
    for i in range(n_tables):
        cols = [{"name": f"t{i}_sk", "type": "string"}, {"name": f"t{i}_code", "type": "string"},
                {"name": f"attr_{i}", "type": "string"}]
        tables.append({"name": f"slv_table_{i:02d}", "business_object": f"Obj{i % 6}", "data_class": "event",
                       "grain": "One row per thing.", "primary_key": [f"t{i}_sk"], "business_key": [f"t{i}_code"],
                       "columns": cols})
    k = 0
    for a in range(n_tables):
        for step in (1, 3, 7):
            if k >= n_rels:
                break
            b = (a + step) % n_tables
            col = f"fk_{k}_sk"
            tables[a]["columns"].append({"name": col, "type": "string"})
            rels.append({"from": tables[a]["name"], "to": tables[b]["name"], "fk_column": col,
                         "cardinality": "N:1", "status": "known" if k % 3 else "assumed",
                         **({} if k % 3 else {"assumption": "A-0001"})})
            k += 1
    return {"tables": tables, "relationships": rels}


def big_mapping(n=30):
    return {"links": [{"business_object": f"Obj{i % 5}", "bronze_table": f"brz.t{i}", "bronze_columns": [f"id_{i}"],
                       "silver_table": f"slv_t{i % 12}", "silver_columns": [f"key_{i}"], "status": "known"}
                      for i in range(n)]}


CASES = dict(ALL)
CASES["logical_big"] = big_logical()
CASES["mapping_big"] = big_mapping()


def kind_of(case):
    return case.split("_big")[0]


# ------------------------------------------------------------------ palette (WCAG)
def test_luminance_known_pairs():
    assert palette.contrast("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)
    assert palette.contrast("#ffffff", "#ffffff") == pytest.approx(1.0)
    assert palette.contrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.02)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_all_text_pairs_meet_contrast(theme):
    bad = [(n, fg, bg, round(palette.contrast(fg, bg), 2), need) for n, fg, bg, need in palette.text_pairs(theme)
           if palette.contrast(fg, bg) < need]
    assert bad == []


def test_key_badges_need_seven_to_one():
    for theme in ("light", "dark"):
        badges = [p for p in palette.text_pairs(theme) if "badge" in p[0]]
        assert len(badges) == 3 and all(p[3] == 7.0 for p in badges)


# ------------------------------------------------------------------ layout
@pytest.mark.parametrize("case", sorted(CASES))
def test_no_box_or_label_overlap(case):
    kind = kind_of(case)
    model = CASES[case]
    assert models.validate(kind, model) == []
    lay = layout_graph(kind, models.graph_of(kind, model))
    boxes = list(lay["nodes"].items())
    for i, (a, ba) in enumerate(boxes):
        for b, bb in boxes[i + 1:]:
            assert not overlaps(ba, bb), f"boxes {a} and {b} overlap"
    for l in lay["labels"]:
        for n, b in boxes:
            assert not overlaps(l, b), f"label of edge {l['edge']} overlaps box {n}"
    for i, la in enumerate(lay["labels"]):
        for lb in lay["labels"][i + 1:]:
            assert not overlaps(la, lb), f"labels {la['edge']} and {lb['edge']} overlap"
    for n, b in boxes:     # text fits in its box
        assert max(len(t) for t in b["lines"]) * 7.8 <= b["w"]


def test_mapping_view_three_columns():
    lay = layout_graph("mapping", models.graph_of("mapping", ALL["mapping"]))
    xs = {p: {round(b["x"]) for n, b in lay["nodes"].items() if n.startswith(p)} for p in ("bo_", "s_", "b_")}
    assert max(xs["bo_"]) < min(xs["s_"]) and max(xs["s_"]) < min(xs["b_"])


# ------------------------------------------------------------------ HTML
@pytest.mark.parametrize("kind", models.MODELS)
def test_html_embeds_exact_graph_and_mermaid(kind):
    page = render_html(kind, ALL[kind], title=f"{kind} model", version_label=f"{kind}.v001")
    g = json.loads(re.search(r'<script type="application/json" id="graph">(.*?)</script>', page, re.S).group(1))
    assert g == models.graph_of(kind, ALL[kind])
    assert "<script src" not in page and "http://" not in page and "https://" not in page
    assert check_views(kind, ALL[kind], models.to_mermaid(kind, ALL[kind]), page) == []


def test_cardinality_text_and_notation_shown():
    page = render_html("logical", ALL["logical"], title="logical", version_label="logical.v001")
    assert "N:1 — many slv_shipment_leg, one slv_shipment" in page
    assert "}o--||" in page and "}o..||" in page                       # assumed relationship is dotted
    assert 'marker-start="url(#m-many)" marker-end="url(#m-one)"' in page


def test_status_not_by_colour_alone():
    page = render_html("dependencies", ALL["dependencies"], title="deps", version_label="dependencies.v001")
    assert "? Terminal operating system" in page and 'class="node st-unknown"' in page
    assert ".st-unknown .box { fill:var(--fill-unknown); stroke:var(--border-unknown); stroke-dasharray:4 3" in page
    page = render_html("process", ALL["process"], title="p", version_label="process.v001")
    assert "Execute leg (A-0001)" in page and 'class="node st-assumed"' in page


def test_large_logical_groups():
    page = render_html("logical", CASES["logical_big"], title="big", version_label="logical.v009")
    assert 'class="grp" data-group="Obj0"' in page
    vd = json.loads(re.search(r'id="viewdata">(.*?)</script>', page, re.S).group(1))
    assert sum(len(v) for v in vd["groups"].values()) == 40


def test_small_logical_has_no_groups():
    assert 'class="grp"' not in render_html("logical", ALL["logical"], title="l", version_label="v")


# ------------------------------------------------------------------ check-views fails on edits
def _pair(kind="logical"):
    return models.to_mermaid(kind, ALL[kind]), render_html(kind, ALL[kind], title="t", version_label="v")


def test_check_fails_on_hand_edited_cardinality():
    mmd, page = _pair()
    edited = mmd.replace("slv_shipment_leg }o--|| slv_shipment", "slv_shipment_leg ||--|| slv_shipment")
    assert edited != mmd
    errs = check_views("logical", ALL["logical"], edited, page)
    assert any("edge" in e for e in errs)


def test_check_fails_on_label_edit_and_added_node():
    mmd, page = _pair("conceptual")
    errs = check_views("conceptual", ALL["conceptual"], mmd.replace("part_of N:1", "part_of 1:N"), page)
    assert errs
    errs = check_views("conceptual", ALL["conceptual"], mmd + '  Extra["Extra"]\n', page)
    assert any("node Extra" in e for e in errs)


def test_check_fails_on_tampered_html_json():
    mmd, page = _pair()
    m = re.search(r'(<script type="application/json" id="graph">)(.*?)(</script>)', page, re.S)
    g = json.loads(m.group(2))
    g["edges"][0]["card"] = "1:1"
    tampered = page[:m.start(2)] + json.dumps(g) + page[m.end(2):]
    assert any("html" in e for e in check_views("logical", ALL["logical"], mmd, tampered))
    assert check_views("logical", ALL["logical"], mmd, page.replace('id="graph"', 'id="x"'))


def test_check_fails_when_model_changed_after_views():
    mmd, page = _pair()
    m2 = copy.deepcopy(ALL["logical"])
    m2["tables"][0]["columns"].append({"name": "new_col", "type": "string"})
    assert check_views("logical", m2, mmd, page)


def test_check_fails_when_mermaid_tab_differs():
    mmd, page = _pair()
    page2 = page.replace("erDiagram\n", "erDiagram\n%% edited\n", 1)
    assert "HTML Mermaid tab text differs from the .mmd file" in check_views("logical", ALL["logical"], mmd, page2)


# ------------------------------------------------------------------ write_views
def test_write_views_companions(project):
    stem = project.stem("S90_yardops", "models/logical")
    v = versions.save(project, stem, "yaml", ALL["logical"], reason="first", app="S90_yardops")
    out = write_views(v, "logical", ALL["logical"])
    assert out["errors"] == []
    assert out["mmd"].name == "logical.v001.mmd" and out["html"].name == "logical.v001.html"
    assert out["mmd"].read_text(encoding="utf-8") == models.to_mermaid("logical", ALL["logical"])
    assert "logical.v001" in out["html"].read_text(encoding="utf-8")
