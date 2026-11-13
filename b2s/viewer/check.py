"""check-views: the .mmd, the HTML's embedded graph and the model YAML must describe the same graph."""
from __future__ import annotations

import html as _html
import json
import re

from .. import models, versions
from .html import render_html

_GRAPH = re.compile(r'<script type="application/json" id="graph">(.*?)</script>', re.S)
_MMD = re.compile(r'<pre id="mermaid-source">(.*?)</pre>', re.S)


def _edge_key(e: dict) -> str:
    return json.dumps(e, sort_keys=True)


def _compare(name_a: str, a: dict, name_b: str, b: dict) -> list[str]:
    errs = []
    if a.get("type") != b.get("type"):
        errs.append(f"{name_a} is {a.get('type')} but {name_b} is {b.get('type')}")
    na, nb = a.get("nodes") or {}, b.get("nodes") or {}
    for n in sorted(na.keys() - nb.keys()):
        errs.append(f"node {n} is in {name_a} but not in {name_b}")
    for n in sorted(nb.keys() - na.keys()):
        errs.append(f"node {n} is in {name_b} but not in {name_a}")
    for n in sorted(na.keys() & nb.keys()):
        if na[n] != nb[n]:
            for k in sorted(set(na[n]) | set(nb[n])):
                if na[n].get(k) != nb[n].get(k):
                    errs.append(f"node {n}: {k} differs ({name_a}: {na[n].get(k)!r}; {name_b}: {nb[n].get(k)!r})")
    ea = sorted(_edge_key(e) for e in a.get("edges") or [])
    eb = sorted(_edge_key(e) for e in b.get("edges") or [])
    for e in sorted(set(ea) - set(eb)):
        errs.append(f"edge in {name_a} but not in {name_b}: {e}")
    for e in sorted(set(eb) - set(ea)):
        errs.append(f"edge in {name_b} but not in {name_a}: {e}")
    if not errs and ea != eb:
        errs.append(f"edge multiset differs between {name_a} and {name_b}")
    return errs


def check_views(kind: str, model: dict, mmd_text: str, html_text: str) -> list[str]:
    """Errors when the Mermaid file, the HTML viewer and the model disagree. Empty list = pass."""
    errs: list[str] = []
    expected = models.graph_of(kind, model)
    try:
        g_mmd = models.parse_mermaid(mmd_text)
    except models.ModelError as ex:
        return [f".mmd is not in the framework Mermaid subset: {ex}"]
    m = _GRAPH.search(html_text)
    if not m:
        return errs + _compare("model", expected, ".mmd", g_mmd) + ["HTML has no embedded graph (script#graph)"]
    try:
        g_html = json.loads(m.group(1))
    except json.JSONDecodeError as ex:
        return [f"HTML embedded graph is not valid JSON: {ex}"]
    errs += _compare("model", expected, ".mmd", g_mmd)
    errs += _compare("model", expected, "html", g_html)
    src = _MMD.search(html_text)
    if not src:
        errs.append("HTML has no Mermaid tab (pre#mermaid-source)")
    elif _html.unescape(src.group(1)).strip() != mmd_text.strip():
        errs.append("HTML Mermaid tab text differs from the .mmd file")
    return errs


def write_views(v: versions.Version, kind: str, model: dict) -> dict:
    """Write <stem>.vNNN.mmd and <stem>.vNNN.html for a model version, then check they match."""
    mmd = models.to_mermaid(kind, model)
    page = render_html(kind, model, title=f"{v.stem.name} model", version_label=v.label)
    p_mmd = versions.write_companion(v, "mmd", mmd)
    p_html = versions.write_companion(v, "html", page)
    errs = check_views(kind, model, p_mmd.read_text(encoding="utf-8"), p_html.read_text(encoding="utf-8"))
    return {"mmd": p_mmd, "html": p_html, "errors": errs}
