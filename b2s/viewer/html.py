"""Self-contained interactive HTML for one model version (inline SVG, CSS, JS; no external scripts)."""
from __future__ import annotations

import html as _html
import json

from .. import models
from . import palette
from .layout import CHAR_W, LINE_H, PAD, cardinality_sentence, layout_graph, mermaid_symbol

GROUP_THRESHOLD = 25


def _e(s) -> str:
    return _html.escape(str(s), quote=True)


def _json_script(obj) -> str:
    # "</" must not appear inside a <script>; "\/" is a valid JSON escape, so json.loads still reads it.
    return json.dumps(obj, sort_keys=True, ensure_ascii=False).replace("</", "<\\/")


def edge_status(e: dict) -> str:
    if (e.get("label") or "").startswith("? "):
        return "unknown"
    return "assumed" if e.get("dashed") else "known"


def _details(kind: str, model: dict) -> dict:
    """Extra facts per node id, from the model (shown in the details panel)."""
    out = {}
    if kind == "logical":
        for t in model.get("tables") or []:
            out[t["name"]] = {k: t.get(k) for k in ("business_object", "data_class", "grain", "primary_key",
                                                    "business_key", "status", "assumption", "question") if t.get(k)}
    elif kind == "conceptual":
        for o in model.get("objects") or []:
            out[o["name"]] = {k: o.get(k) for k in ("status", "tables", "assumption", "question", "change_request")
                              if o.get(k)}
    elif kind == "dependencies":
        for s in model.get("systems") or []:
            out[s["id"]] = {k: s.get(k) for k in ("relation", "gives", "status", "evidence", "assumption", "question")
                            if s.get(k)}
    elif kind == "process":
        for p in model.get("processes") or []:
            for st in p.get("steps") or []:
                out[st["id"]] = {"process": p.get("name"), **{k: st.get(k) for k in ("records", "status", "assumption",
                                                                                     "question") if st.get(k)}}
    return out


def _groups(kind: str, model: dict, graph: dict) -> dict:
    if kind != "logical" or len(graph["nodes"]) <= GROUP_THRESHOLD:
        return {}
    g: dict[str, list] = {}
    for t in model.get("tables") or []:
        g.setdefault(t.get("business_object") or "(none)", []).append(t["name"])
    return g


def _node_svg(kind: str, graph: dict, nid: str, b: dict) -> str:
    n = graph["nodes"][nid]
    st = n.get("status", "known")
    x, y, w, h = b["x"], b["y"], b["w"], b["h"]
    out = [f'<g class="node st-{st}" data-id="{_e(nid)}" data-status="{st}" tabindex="0">',
           f'<rect class="box" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>']
    if graph["type"] == "erDiagram":
        hh = LINE_H + PAD
        out.append(f'<rect class="hdr" x="{x}" y="{y}" width="{w}" height="{hh}" rx="6"/>')
        out.append(f'<text class="hdr-t" x="{x + PAD}" y="{y + PAD + LINE_H - 5}">{_e(nid)}</text>')
        for i, a in enumerate(n.get("attrs", [])):
            ty = y + PAD + (i + 2) * LINE_H - 5
            keys = list(a.get("keys") or [])
            if "BK" in (a.get("comment") or "").split():
                keys.append("BK")
            off = 0
            for k in keys:
                bx = x + PAD + off * CHAR_W
                out.append(f'<rect class="badge b-{k.lower()}" x="{bx - 1}" y="{ty - 13}" width="{len(k) * CHAR_W + 2}" height="16" rx="3"/>')
                out.append(f'<text class="badge-t t-{k.lower()}" x="{bx}" y="{ty}">{_e(k)}</text>')
                off += len(k) + 1
            extra = (a.get("comment") or "").replace("BK", "").strip()
            rest = f"{a['name']}  {a['type']}" + (f"  {extra}" if extra else "")
            out.append(f'<text class="nt" x="{x + PAD + 9 * CHAR_W}" y="{ty}">{_e(rest)}</text>')
    else:
        for i, line in enumerate(b["lines"]):
            out.append(f'<text class="nt" x="{x + PAD}" y="{y + PAD + (i + 1) * LINE_H - 5}">{_e(line)}</text>')
    out.append(f"<title>{_e(nid)}</title></g>")
    return "".join(out)


def _markers(e: dict, er: bool) -> str:
    if er:
        sym = mermaid_symbol(e).replace("..", "--")
        left, right = sym[:2], sym[-2:]
        start = "m-many" if left in ("}o", "}|") else "m-one"
        end = "m-many" if right in ("o{", "|{") else "m-one"
        return f'marker-start="url(#{start})" marker-end="url(#{end})"'
    return 'marker-end="url(#m-arrow)"' if e.get("directed") else ""


def render_html(kind: str, model: dict, *, title: str, version_label: str) -> str:
    mmd = models.to_mermaid(kind, model)
    graph = models.parse_mermaid(mmd)
    lay = layout_graph(kind, graph)
    er = graph["type"] == "erDiagram"
    details = _details(kind, model)
    groups = _groups(kind, model, graph)

    edges_svg, labels_svg = [], []
    lab_by_edge = {l["edge"]: l for l in lay["labels"]}
    edge_meta = []
    for ed in lay["edges"]:
        e = graph["edges"][ed["edge"]]
        st = edge_status(e)
        pts = " ".join(f"{x},{y}" for x, y in ed["points"])
        dash = ' stroke-dasharray="6 4"' if e.get("dashed") else ""
        edges_svg.append(f'<polyline class="edge st-{st}" data-edge="{ed["edge"]}" data-from="{_e(e["from"])}" '
                         f'data-to="{_e(e["to"])}" data-status="{st}" points="{pts}"{dash} {_markers(e, er)}/>')
        meta = {"from": e["from"], "to": e["to"], "label": e.get("label", ""), "status": st}
        if er:
            meta.update({"cardinality": e.get("card"), "mermaid": mermaid_symbol(e), "reading": cardinality_sentence(e)})
        edge_meta.append(meta)
        if ed["edge"] in lab_by_edge:
            l = lab_by_edge[ed["edge"]]
            t = [f'<g class="elabel st-{st}" data-edge="{ed["edge"]}" data-status="{st}">',
                 f'<rect x="{l["x"]}" y="{l["y"]}" width="{l["w"]}" height="{l["h"]}" rx="4"{dash}/>']
            for i, line in enumerate(l["lines"]):
                t.append(f'<text x="{l["x"] + 6}" y="{l["y"] + 4 + (i + 1) * LINE_H - 5}">{_e(line)}</text>')
            labels_svg.append("".join(t) + "</g>")
    nodes_svg = [_node_svg(kind, graph, nid, b) for nid, b in lay["nodes"].items()]

    viewdata = {"kind": kind, "edges": edge_meta, "details": details, "groups": groups,
                "width": lay["width"], "height": lay["height"]}
    group_html = ""
    if groups:
        group_html = '<div class="groups"><b>Groups</b> ' + " ".join(
            f'<button class="grp" data-group="{_e(g)}" aria-pressed="false">{_e(g)} ({len(ts)})</button>'
            for g, ts in sorted(groups.items())) + "</div>"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title>
<style>
:root {{
{palette.css_variables("light")}
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
{palette.css_variables("dark")}
}} }}
:root[data-theme="dark"] {{
{palette.css_variables("dark")}
}}
body {{ margin:0; background:var(--page-bg); color:var(--page-text); font:14px system-ui, sans-serif; }}
header {{ padding:10px 16px; display:flex; flex-wrap:wrap; gap:10px; align-items:center; }}
header h1 {{ font-size:16px; margin:0 12px 0 0; }}
.muted {{ color:var(--muted-text); }}
button, .tab {{ background:var(--button-bg); color:var(--button-text); border:0; border-radius:4px; padding:4px 10px; cursor:pointer; font:inherit; }}
input[type=search] {{ padding:4px 8px; font:inherit; background:var(--page-bg); color:var(--page-text); border:1px solid var(--label-border); border-radius:4px; }}
.wrap {{ display:flex; height:calc(100vh - 110px); }}
#canvas {{ flex:1; overflow:hidden; border-top:1px solid var(--label-border); }}
#panel {{ width:320px; background:var(--panel-bg); color:var(--panel-text); padding:12px; overflow:auto; font-size:13px; }}
#panel pre {{ white-space:pre-wrap; margin:0; }}
svg {{ width:100%; height:100%; cursor:grab; font-family:ui-monospace, Consolas, monospace; font-size:13px; }}
.box {{ stroke-width:1.5; }}
.st-known .box {{ fill:var(--fill-known); stroke:var(--border-known); }}
.st-assumed .box {{ fill:var(--fill-assumed); stroke:var(--border-assumed); stroke-dasharray:6 3; }}
.st-unknown .box {{ fill:var(--fill-unknown); stroke:var(--border-unknown); stroke-dasharray:4 3; stroke-width:2; }}
.hdr {{ fill:var(--header-bg); }}
.hdr-t {{ fill:var(--header-text); font-weight:bold; }}
.nt {{ fill:var(--node-text); }}
.badge.b-pk {{ fill:var(--badge-pk-bg); }} .badge-t.t-pk {{ fill:var(--badge-pk-text); }}
.badge.b-fk {{ fill:var(--badge-fk-bg); }} .badge-t.t-fk {{ fill:var(--badge-fk-text); }}
.badge.b-bk {{ fill:var(--badge-bk-bg); }} .badge-t.t-bk {{ fill:var(--badge-bk-text); }}
.badge-t {{ font-weight:bold; font-size:12px; }}
.edge {{ fill:none; stroke:var(--edge); stroke-width:1.5; }}
.edge.st-unknown {{ stroke:var(--border-unknown); }}
.elabel rect {{ fill:var(--label-bg); stroke:var(--label-border); }}
.elabel.st-unknown rect {{ stroke:var(--border-unknown); }}
.elabel text {{ fill:var(--label-text); font-size:12px; }}
.marker {{ fill:none; stroke:var(--edge); stroke-width:1.5; }}
.marker-fill {{ fill:var(--edge); }}
.dim {{ opacity:.18; }}
.hidden {{ display:none; }}
.hl .box, .edge.hl {{ stroke:var(--highlight); stroke-width:3; }}
.groups {{ padding:4px 16px; }}
.groups button[aria-pressed=true] {{ opacity:.6; text-decoration:line-through; }}
#mermaid {{ display:none; padding:16px; }}
#mermaid pre {{ background:var(--panel-bg); color:var(--panel-text); padding:12px; overflow:auto; }}
.legend span {{ margin-right:10px; }}
</style></head>
<body>
<header>
  <h1>{_e(title)}</h1><span class="muted">version {_e(version_label)} · {_e(kind)} model · generated, do not edit</span>
  <button class="tab" data-tab="diagram">Diagram</button><button class="tab" data-tab="mermaid">Mermaid</button>
  <input type="search" id="search" placeholder="Search table, column, label" aria-label="Search">
  <span class="legend">Show:
    <label><input type="checkbox" class="sf" value="known" checked> known</label>
    <label><input type="checkbox" class="sf" value="assumed" checked> assumed (dashed, A-)</label>
    <label><input type="checkbox" class="sf" value="unknown" checked> unknown (? , red dashed)</label>
  </span>
  <button id="fit">Fit</button><button id="theme">Theme</button>
</header>
{group_html}
<div class="wrap" id="diagram">
<div id="canvas"><svg id="svg" viewBox="0 0 {lay['width']} {lay['height']}" role="img" aria-label="{_e(title)}">
<defs>
 <marker id="m-arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse"><path class="marker-fill" d="M0,0 L10,5 L0,10 z"/></marker>
 <marker id="m-one" viewBox="0 -1 14 12" refX="13" refY="5" markerWidth="14" markerHeight="12" orient="auto-start-reverse"><path class="marker" d="M0,5 L13,5 M6,0 L6,10 M10,0 L10,10"/></marker>
 <marker id="m-many" viewBox="-8 -1 22 12" refX="13" refY="5" markerWidth="22" markerHeight="12" orient="auto-start-reverse"><circle class="marker" cx="-3" cy="5" r="3"/><path class="marker" d="M0,5 L13,5 M3,5 L13,0 M3,5 L13,10"/></marker>
</defs>
<g id="vp">{''.join(edges_svg)}{''.join(nodes_svg)}{''.join(labels_svg)}</g></svg></div>
<aside id="panel"><b>Details</b><p class="muted">Click a box to see its connections, keys and evidence links.</p><pre id="det"></pre></aside>
</div>
<section id="mermaid"><p class="muted">Exact Mermaid source of this version (the accountability record).</p><pre id="mermaid-source">{_e(mmd)}</pre></section>
<script type="application/json" id="graph">{_json_script(graph)}</script>
<script type="application/json" id="viewdata">{_json_script(viewdata)}</script>
<script>
(function(){{
const G = JSON.parse(document.getElementById('graph').textContent);
const V = JSON.parse(document.getElementById('viewdata').textContent);
const svg = document.getElementById('svg'), det = document.getElementById('det');
let vb = [0, 0, V.width, V.height];
const setVB = () => svg.setAttribute('viewBox', vb.join(' '));
document.getElementById('fit').onclick = () => {{ vb = [0, 0, V.width, V.height]; setVB(); }};
svg.addEventListener('wheel', ev => {{ ev.preventDefault(); const k = ev.deltaY > 0 ? 1.1 : 0.9;
  const r = svg.getBoundingClientRect(); const mx = vb[0] + (ev.clientX - r.left) / r.width * vb[2], my = vb[1] + (ev.clientY - r.top) / r.height * vb[3];
  vb = [mx - (mx - vb[0]) * k, my - (my - vb[1]) * k, vb[2] * k, vb[3] * k]; setVB(); }}, {{passive:false}});
let drag = null;
svg.addEventListener('mousedown', ev => {{ drag = [ev.clientX, ev.clientY, vb[0], vb[1]]; }});
window.addEventListener('mouseup', () => drag = null);
window.addEventListener('mousemove', ev => {{ if (!drag) return; const r = svg.getBoundingClientRect();
  vb[0] = drag[2] - (ev.clientX - drag[0]) / r.width * vb[2]; vb[1] = drag[3] - (ev.clientY - drag[1]) / r.height * vb[3]; setVB(); }});
const all = sel => Array.from(document.querySelectorAll(sel));
function clearHL() {{ all('.dim,.hl').forEach(el => el.classList.remove('dim', 'hl')); }}
function select(id) {{
  clearHL(); const nb = new Set([id]); const lines = [];
  V.edges.forEach((e, i) => {{ if (e.from === id || e.to === id) {{ nb.add(e.from); nb.add(e.to);
    all('[data-edge="' + i + '"]').forEach(el => el.classList.add('hl'));
    lines.push('- ' + e.from + ' → ' + e.to + (e.label ? ' : ' + e.label : '') + (e.reading ? '\\n   ' + e.reading + '   ' + e.mermaid : '') + '   [' + e.status + ']'); }} }});
  all('.node').forEach(n => {{ if (!nb.has(n.dataset.id)) n.classList.add('dim'); }});
  all('.edge,.elabel').forEach(el => {{ if (!el.classList.contains('hl')) el.classList.add('dim'); }});
  document.querySelector('.node[data-id="' + CSS.escape(id) + '"]').classList.add('hl');
  const n = G.nodes[id] || {{}}; const d = V.details[id] || {{}};
  let txt = id + '\\n' + (n.label && n.label !== id ? n.label.replace(/<br\\/>/g, ' | ') + '\\n' : '') + 'status: ' + (n.status || d.status || 'known') + '\\n';
  if (n.attrs) txt += '\\ncolumns:\\n' + n.attrs.map(a => '  ' + (a.keys.join(',') || '  ') + ' ' + a.name + ' ' + a.type + (a.comment ? '  ' + a.comment : '')).join('\\n') + '\\n';
  Object.keys(d).forEach(k => txt += k + ': ' + JSON.stringify(d[k]) + '\\n');
  det.textContent = txt + '\\nconnections:\\n' + (lines.join('\\n') || '  none');
}}
all('.node').forEach(n => {{ n.addEventListener('click', ev => {{ ev.stopPropagation(); select(n.dataset.id); }});
  n.addEventListener('keydown', ev => {{ if (ev.key === 'Enter') select(n.dataset.id); }}); }});
svg.addEventListener('click', () => {{ clearHL(); det.textContent = ''; }});
function applyFilters() {{
  const on = new Set(all('.sf').filter(c => c.checked).map(c => c.value));
  const hiddenGroups = new Set(all('.grp[aria-pressed=true]').map(b => b.dataset.group));
  const hiddenNodes = new Set(); Object.keys(V.groups).forEach(g => {{ if (hiddenGroups.has(g)) V.groups[g].forEach(t => hiddenNodes.add(t)); }});
  all('.node').forEach(n => n.classList.toggle('hidden', !on.has(n.dataset.status) || hiddenNodes.has(n.dataset.id)));
  all('.edge,.elabel').forEach(el => {{ const e = V.edges[+el.dataset.edge];
    el.classList.toggle('hidden', !on.has(el.dataset.status) || hiddenNodes.has(e.from) || hiddenNodes.has(e.to)); }});
}}
all('.sf').forEach(c => c.addEventListener('change', applyFilters));
all('.grp').forEach(b => b.addEventListener('click', () => {{ b.setAttribute('aria-pressed', b.getAttribute('aria-pressed') === 'true' ? 'false' : 'true'); applyFilters(); }}));
document.getElementById('search').addEventListener('input', ev => {{ const q = ev.target.value.trim().toLowerCase(); clearHL();
  if (!q) return; all('.node').forEach(n => {{ const t = (n.dataset.id + ' ' + n.textContent).toLowerCase(); n.classList.add(t.includes(q) ? 'hl' : 'dim'); }}); }});
all('.tab').forEach(t => t.onclick = () => {{ const m = t.dataset.tab === 'mermaid';
  document.getElementById('mermaid').style.display = m ? 'block' : 'none'; document.getElementById('diagram').style.display = m ? 'none' : 'flex'; }});
document.getElementById('theme').onclick = () => {{ const r = document.documentElement;
  const dark = r.dataset.theme ? r.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches; r.dataset.theme = dark ? 'light' : 'dark'; }};
}})();
</script>
</body></html>
"""
