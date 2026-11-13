"""M1.10: AGENTS.md size and links, skills referenced exist, notebooks are Spark Connect safe, CLI smoke test."""
import ast
import re

import pytest

from b2s import FRAMEWORK_ROOT
from b2s.cli import main

AGENTS = FRAMEWORK_ROOT / "AGENTS.md"


def test_agents_core_is_short():
    assert len(AGENTS.read_text(encoding="utf-8")) < 6000


def test_rule_links_resolve_and_rules_are_small():
    text = AGENTS.read_text(encoding="utf-8")
    links = set(re.findall(r"`(rules/[a-z\-]+\.md)`", text))
    assert links, "AGENTS.md links its rule files"
    for l in links:
        assert (FRAMEWORK_ROOT / l).exists(), l
    for f in (FRAMEWORK_ROOT / "rules").glob("*.md"):
        assert len(f.read_text(encoding="utf-8")) < 4000, f.name
        assert "AGENTS.md" in f.read_text(encoding="utf-8"), f"{f.name} links back to AGENTS.md"


def test_every_skill_named_in_agents_exists_with_front_matter():
    text = AGENTS.read_text(encoding="utf-8")
    for name in set(re.findall(r"`@([a-z0-9\-]+)`", text)) - {"skill-name"}:
        skill = FRAMEWORK_ROOT / "skills" / name / "SKILL.md"
        assert skill.exists(), name
        head = skill.read_text(encoding="utf-8").split("---")[1]
        assert f"name: {name}" in head and "description:" in head


@pytest.mark.parametrize("nb", sorted((FRAMEWORK_ROOT / "notebooks").glob("*.py")), ids=lambda p: p.name)
def test_notebooks_parse_and_are_spark_connect_safe(nb):
    src = nb.read_text(encoding="utf-8")
    assert src.startswith("# Databricks notebook source")
    assert _banned(src) == [], nb.name
    assert not re.search(r"^(# MAGIC )?%pip", src, re.M), f"{nb.name} installs with %pip (use the serverless environment)"


BANNED = {"sparkContext", "rdd", "_jvm", "_jsc"}


def _banned(src: str) -> list:
    """Attribute uses of Spark classic-only APIs (comments and docstrings do not count)."""
    return [n.attr for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Attribute) and n.attr in BANNED]


def test_engine_is_spark_connect_safe():
    for f in (FRAMEWORK_ROOT / "b2s").rglob("*.py"):
        assert _banned(f.read_text(encoding="utf-8")) == [], f.name


def test_cli_smoke(tmp_path, capsys):
    root = tmp_path / "p"
    main(["init", str(root), "Demo"])
    main(["--project", str(root), "register", "S01_demo", "Demo app", "--schemas", "demo"])
    main(["--project", str(root), "status", "S01_demo"])
    out = capsys.readouterr().out
    assert "registered S01_demo" in out and "P2" in out and "Approvals:" in out
    with pytest.raises(SystemExit, match="NOT RECORDED"):
        main(["--project", str(root), "approve", "request", "S01_demo", "CP3"])
