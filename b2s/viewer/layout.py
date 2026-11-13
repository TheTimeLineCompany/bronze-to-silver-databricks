"""Layered (Sugiyama-type) layout computed in Python, so non-overlap can be tested.

Steps: break cycles (DFS) -> longest-path layers (or fixed layers for the mapping view) -> barycenter crossing
reduction -> coordinates. Layers run left to right. Boxes of a layer sit in a column; edge labels sit in the
channel between columns, stacked so they never touch each other or a box.
"""
from __future__ import annotations

CHAR_W = 7.8       # monospace 13px
LINE_H = 18.0
PAD = 10.0
NODE_GAP = 28.0     # vertical gap between boxes in a column
CH_MARGIN = 24.0    # space between a channel's labels and the columns around it
MIN_CHANNEL = 90.0
LABEL_GAP = 8.0
TOP = 40.0
LEFT = 30.0


def node_lines(kind: str, graph: dict, nid: str) -> list[str]:
    n = graph["nodes"][nid]
    if graph["type"] == "erDiagram":
        lines = [nid]
        for a in n.get("attrs", []):
            keys = list(a.get("keys") or [])
            if "BK" in (a.get("comment") or "").split():
                keys.append("BK")
            badge = ",".join(keys)
            extra = (a.get("comment") or "").replace("BK", "").strip()
            lines.append(f"{badge:<8} {a['name']}  {a['type']}" + (f"  {extra}" if extra else ""))
        return lines
    return str(n.get("label", nid)).split("<br/>")


def label_lines(graph: dict, e: dict) -> list[str]:
    out = []
    if e.get("label"):
        out.append(e["label"])
    if graph["type"] == "erDiagram" and e.get("card"):
        out.append(f"{e['card']}  {mermaid_symbol(e)}")
        out.append(cardinality_sentence(e))
    return out


_ER = {"1:1": "||--||", "1:N": "||--o{", "N:1": "}o--||", "N:M": "}o--o{"}


def mermaid_symbol(e: dict) -> str:
    s = _ER.get(e.get("card") or "", "")
    return s.replace("--", "..") if e.get("dashed") else s


def cardinality_sentence(e: dict) -> str:
    left, right = (e.get("card") or "?:?").split(":")
    word = {"1": "one", "N": "many", "M": "many"}
    return f"{e['card']} — {word.get(left, left)} {e['from']}, {word.get(right, right)} {e['to']}"


def _size(lines: list[str]) -> tuple[float, float]:
    w = max((len(l) for l in lines), default=1) * CHAR_W + 2 * PAD
    return max(w, 110.0), len(lines) * LINE_H + 2 * PAD


def _fixed_layer(nid: str) -> int | None:
    for i, p in enumerate(("bo_", "s_", "b_")):
        if nid.startswith(p):
            return i
    return None


def _layers(kind: str, graph: dict) -> dict[str, int]:
    nodes = list(graph["nodes"])
    if kind == "mapping" and all(_fixed_layer(n) is not None for n in nodes):
        return {n: _fixed_layer(n) for n in nodes}
    out = {n: [] for n in nodes}
    for e in graph["edges"]:
        if e["from"] in out and e["to"] in out and e["from"] != e["to"]:
            out[e["from"]].append(e["to"])
    # break cycles: drop back edges found by DFS
    state, dag = {}, {n: [] for n in nodes}

    def dfs(u):
        state[u] = 1
        for v in out[u]:
            if state.get(v) == 1:
                continue                      # back edge
            dag[u].append(v)
            if v not in state:
                dfs(v)
        state[u] = 2
    for n in nodes:
        if n not in state:
            dfs(n)
    # longest path from sources
    indeg = {n: 0 for n in nodes}
    for u in nodes:
        for v in dag[u]:
            indeg[v] += 1
    layer = {n: 0 for n in nodes}
    queue = [n for n in nodes if indeg[n] == 0]
    while queue:
        u = queue.pop(0)
        for v in dag[u]:
            layer[v] = max(layer[v], layer[u] + 1)
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    return layer


def _order(graph: dict, layer: dict[str, int]) -> list[list[str]]:
    n_layers = max(layer.values(), default=0) + 1
    cols = [[n for n in graph["nodes"] if layer[n] == i] for i in range(n_layers)]
    nbr = {n: set() for n in graph["nodes"]}
    for e in graph["edges"]:
        if e["from"] in nbr and e["to"] in nbr:
            nbr[e["from"]].add(e["to"])
            nbr[e["to"]].add(e["from"])
    for sweep in range(6):
        rng = range(1, n_layers) if sweep % 2 == 0 else range(n_layers - 2, -1, -1)
        for i in rng:
            ref = cols[i - 1] if sweep % 2 == 0 else cols[i + 1]
            pos = {n: k for k, n in enumerate(ref)}
            cur = {n: k for k, n in enumerate(cols[i])}

            def bary(n):
                ps = [pos[m] for m in nbr[n] if m in pos]
                return sum(ps) / len(ps) if ps else cur[n]
            cols[i].sort(key=lambda n: (bary(n), cur[n]))
    return cols


def layout_graph(kind: str, graph: dict) -> dict:
    """{"nodes": {id: {x,y,w,h,lines,layer}}, "labels": [{edge,x,y,w,h,lines}], "edges": [{edge, points}],
    "width", "height"}"""
    layer = _layers(kind, graph)
    cols = _order(graph, layer)
    n_layers = len(cols)
    lines = {n: node_lines(kind, graph, n) for n in graph["nodes"]}
    size = {n: _size(lines[n]) for n in graph["nodes"]}
    col_w = [max((size[n][0] for n in c), default=0) for c in cols]

    # labels per channel (channel i = space right of column i)
    lab = []
    for i, e in enumerate(graph["edges"]):
        ls = label_lines(graph, e)
        if not ls or e["from"] not in layer or e["to"] not in layer:
            continue
        ch = min(layer[e["from"]], layer[e["to"]])
        w, h = max(len(l) for l in ls) * CHAR_W + 2 * 6, len(ls) * LINE_H + 2 * 4
        lab.append({"edge": i, "channel": ch, "w": w, "h": h, "lines": ls})
    ch_w = [MIN_CHANNEL] * n_layers
    for l in lab:
        ch_w[l["channel"]] = max(ch_w[l["channel"]], l["w"] + 2 * CH_MARGIN)

    xs, x = [], LEFT
    for i in range(n_layers):
        xs.append(x)
        x += col_w[i] + ch_w[i]
    nodes = {}
    for i, c in enumerate(cols):
        y = TOP
        for n in c:
            w, h = size[n]
            nodes[n] = {"x": xs[i] + (col_w[i] - w) / 2, "y": y, "w": w, "h": h, "lines": lines[n], "layer": i}
            y += h + NODE_GAP

    def centre(n):
        b = nodes[n]
        return b["x"] + b["w"] / 2, b["y"] + b["h"] / 2

    # place labels in their channel near the mid y of the edge, then push apart
    for l in lab:
        e = graph["edges"][l["edge"]]
        y_mid = (centre(e["from"])[1] + centre(e["to"])[1]) / 2
        l["x"] = xs[l["channel"]] + col_w[l["channel"]] + CH_MARGIN
        l["y"] = y_mid - l["h"] / 2
    for ch in range(n_layers):
        ls = sorted((l for l in lab if l["channel"] == ch), key=lambda l: l["y"])
        floor = TOP
        for l in ls:
            l["y"] = max(l["y"], floor)
            floor = l["y"] + l["h"] + LABEL_GAP

    lab_by_edge = {l["edge"]: l for l in lab}
    edges = []
    for i, e in enumerate(graph["edges"]):
        if e["from"] not in nodes or e["to"] not in nodes:
            continue
        a, b = nodes[e["from"]], nodes[e["to"]]
        fwd = a["layer"] <= b["layer"]
        p0 = (a["x"] + a["w"], a["y"] + a["h"] / 2) if fwd else (a["x"], a["y"] + a["h"] / 2)
        p1 = (b["x"], b["y"] + b["h"] / 2) if fwd else (b["x"] + b["w"], b["y"] + b["h"] / 2)
        if a["layer"] == b["layer"]:
            p0 = (a["x"] + a["w"], a["y"] + a["h"] / 2)
            p1 = (b["x"] + b["w"], b["y"] + b["h"] / 2)
        pts = [p0]
        if i in lab_by_edge:
            l = lab_by_edge[i]
            pts += [(l["x"], l["y"] + l["h"] / 2), (l["x"] + l["w"], l["y"] + l["h"] / 2)] if fwd or a["layer"] == b["layer"] \
                else [(l["x"] + l["w"], l["y"] + l["h"] / 2), (l["x"], l["y"] + l["h"] / 2)]
        pts.append(p1)
        edges.append({"edge": i, "points": [[round(px, 1), round(py, 1)] for px, py in pts]})

    width = (xs[-1] + col_w[-1] + ch_w[-1]) if n_layers else 400
    height = max([b["y"] + b["h"] for b in nodes.values()] + [l["y"] + l["h"] for l in lab] + [200]) + TOP
    for b in nodes.values():
        for k in ("x", "y", "w", "h"):
            b[k] = round(b[k], 1)
    labels = [{"edge": l["edge"], "x": round(l["x"], 1), "y": round(l["y"], 1), "w": round(l["w"], 1),
               "h": round(l["h"], 1), "lines": l["lines"]} for l in lab]
    return {"nodes": nodes, "labels": labels, "edges": edges, "width": round(width, 1), "height": round(height, 1)}


def overlaps(a: dict, b: dict, gap: float = 0.0) -> bool:
    return not (a["x"] + a["w"] + gap <= b["x"] or b["x"] + b["w"] + gap <= a["x"] or
                a["y"] + a["h"] + gap <= b["y"] or b["y"] + b["h"] + gap <= a["y"])
