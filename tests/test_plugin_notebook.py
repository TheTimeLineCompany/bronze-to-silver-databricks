"""First use: a client notebook (here a profiler) is integrated with @fw-integrate as a notebook plug-in, the agent runs
it (simulated), the adapter converts its output, and the baseline uses it — with framework redaction and key rules."""
import json

import pytest

from b2s import baseline, plugins, versions
from b2s.baseline.readers import LocalCsvReader
from b2s.demo import fake_app

APP = "S90_yardops"

ADAPTER = '''import json, pathlib
def convert(run_dir):
    """Client profiler writes one JSON per table: {"table": ..., "cols": [{"name", "dtype", "nulls_pct", "n_distinct"}]}"""
    out = {}
    for f in sorted(pathlib.Path(run_dir).glob("*.json")):
        if f.name == "plan.json":
            continue
        d = json.loads(f.read_text())
        out[d["table"]] = [{"column": c["name"], "family": {"string": "str", "int": "int"}.get(c["dtype"], "str"),
                            "null_pct": c["nulls_pct"], "approx_distinct": c["n_distinct"],
                            "min": None, "max": None, "topk": []} for c in d["cols"]]
    return out
'''


def _client_output(table, cols):
    return {"table": table, "cols": [{"name": n, "dtype": t, "nulls_pct": 0.0, "n_distinct": d} for n, t, d in cols]}


@pytest.fixture
def plugin_src(tmp_path):
    src = tmp_path / "client_profiler"
    (src / "sample_output").mkdir(parents=True)
    (src / "client_profiler.py").write_text("# Databricks notebook source\n# the client's profiler, unchanged\n")
    (src / "adapter.py").write_text(ADAPTER)
    (src / "sample_output" / "t.json").write_text(json.dumps(_client_output("s.t", [("id", "string", 10)])))
    (src / "plugin.yaml").write_text(
        "name: client_profiler\nslot: profiler\nkind: notebook\nversion: 2.1.0\nnotebook: client_profiler.py\n"
        "parameters: {schema: '{schema}', output_folder: '{run_dir}'}\nentry: adapter.py:convert\n"
        "description: The client's bronze profiler notebook.\n")
    return src


def test_notebook_plugin_needs_sample_output(project, plugin_src):
    import shutil
    shutil.rmtree(plugin_src / "sample_output")
    with pytest.raises(plugins.PluginError, match="sample_output"):
        plugins.install(project, plugin_src)


def test_first_use_profiler_notebook_feeds_the_baseline(project, plugin_src, tmp_path):
    fake = fake_app.make_fake_app(tmp_path / "fake")
    fake_app.install(project, fake)
    plugins.install(project, plugin_src)
    with pytest.raises(plugins.PluginError, match="no active notebook plug-in"):
        plugins.run_plan(project, APP, "profiler", {"schema": "yard"})
    plugins.activate(project, "client_profiler", "I, Jane Doe, approve PLUGIN client_profiler.v2.1.0.")
    plan = plugins.run_plan(project, APP, "profiler", {"schema": "yard"})
    assert plan["widgets"] == {"schema": "yard", "output_folder": plan["run_dir"]}
    assert plan["notebook"].endswith("client_profiler.py")
    # the agent runs the client notebook; it writes its own format into run_dir
    from pathlib import Path
    n = LocalCsvReader(fake["bronze_root"]).row_count("yard.cntr_mst")
    Path(plan["run_dir"], "cntr_mst.json").write_text(json.dumps(_client_output(
        "yard.cntr_mst", [("cntr_no", "string", n), ("iso_type", "string", 4), ("owner_cd", "string", 6)])))
    ext = plugins.collect(project, APP, plan)
    summary = baseline.run(project, APP, LocalCsvReader(fake["bronze_root"]), external_profiles=ext,
                           external_info={"name": plan["plugin"], "version": plan["version"]})
    t = versions.read(versions.latest(project.stem(APP, "baseline/tables/yard.cntr_mst"), "json"))
    assert t["profiler"] == "external" and t["profiler_plugin"]["version"] == "2.1.0"
    assert t["key"] == ["cntr_no"]                         # framework key search still ran (exact check on bronze)
    others = versions.read(versions.latest(project.stem(APP, "baseline/tables/yard.mv_leg"), "json"))
    assert others["profiler"] == "core"                    # tables the plug-in did not cover use the core profiler
    assert not summary["partial"]
