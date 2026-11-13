"""Colour palettes for the model viewer, light and dark, with a WCAG 2.x contrast check.

Every text/background pair used by the viewer is listed in `text_pairs(theme)`; tests require
>= 4.5:1 for normal text and >= 7:1 for the small PK/FK/BK key badges.
"""
from __future__ import annotations

THEMES: dict[str, dict[str, str]] = {
    "light": {
        "page_bg": "#ffffff", "page_text": "#111827", "muted_text": "#4b5563",
        "panel_bg": "#f3f4f6", "panel_text": "#111827",
        "button_bg": "#1f2937", "button_text": "#ffffff",
        "node_text": "#111827",
        "fill_known": "#ffffff", "fill_assumed": "#fff7e6", "fill_unknown": "#fdecec",
        "border_known": "#1f2937", "border_assumed": "#92400e", "border_unknown": "#b91c1c",
        "header_bg": "#1f2937", "header_text": "#ffffff",
        "group_bg": "#eef2ff", "group_text": "#1e1b4b",
        "edge": "#374151", "edge_dim": "#d1d5db", "highlight": "#2563eb",
        "label_bg": "#ffffff", "label_text": "#1f2937", "label_border": "#9ca3af",
        "badge_pk_bg": "#1e3a8a", "badge_pk_text": "#ffffff",
        "badge_fk_bg": "#065f46", "badge_fk_text": "#ffffff",
        "badge_bk_bg": "#6b21a8", "badge_bk_text": "#ffffff",
    },
    "dark": {
        "page_bg": "#0f172a", "page_text": "#e5e7eb", "muted_text": "#9ca3af",
        "panel_bg": "#1e293b", "panel_text": "#f3f4f6",
        "button_bg": "#e5e7eb", "button_text": "#0f172a",
        "node_text": "#f3f4f6",
        "fill_known": "#1e293b", "fill_assumed": "#3b2a0a", "fill_unknown": "#3f1515",
        "border_known": "#cbd5e1", "border_assumed": "#fbbf24", "border_unknown": "#f87171",
        "header_bg": "#e5e7eb", "header_text": "#0f172a",
        "group_bg": "#312e81", "group_text": "#e0e7ff",
        "edge": "#cbd5e1", "edge_dim": "#475569", "highlight": "#60a5fa",
        "label_bg": "#0f172a", "label_text": "#e5e7eb", "label_border": "#64748b",
        "badge_pk_bg": "#bfdbfe", "badge_pk_text": "#0b1f4d",
        "badge_fk_bg": "#a7f3d0", "badge_fk_text": "#053b2c",
        "badge_bk_bg": "#e9d5ff", "badge_bk_text": "#3b0764",
    },
}

NORMAL_MIN = 4.5
SMALL_MIN = 7.0


def _channel(c: int) -> float:
    s = c / 255.0
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def text_pairs(theme: str) -> list[tuple[str, str, str, float]]:
    """(name, foreground, background, minimum ratio) for every text the viewer draws."""
    t = THEMES[theme]
    pairs = [
        ("page text", t["page_text"], t["page_bg"], NORMAL_MIN),
        ("muted text", t["muted_text"], t["page_bg"], NORMAL_MIN),
        ("panel text", t["panel_text"], t["panel_bg"], NORMAL_MIN),
        ("button text", t["button_text"], t["button_bg"], NORMAL_MIN),
        ("table header", t["header_text"], t["header_bg"], NORMAL_MIN),
        ("group header", t["group_text"], t["group_bg"], NORMAL_MIN),
        ("edge label", t["label_text"], t["label_bg"], NORMAL_MIN),
        ("highlight on page", t["highlight"], t["page_bg"], 3.0),   # non-text UI: WCAG 1.4.11 3:1
    ]
    for st in ("known", "assumed", "unknown"):
        pairs.append((f"node text on {st}", t["node_text"], t[f"fill_{st}"], NORMAL_MIN))
        pairs.append((f"{st} border vs fill (UI)", t[f"border_{st}"], t[f"fill_{st}"], 3.0))
    for k in ("pk", "fk", "bk"):
        pairs.append((f"{k.upper()} badge", t[f"badge_{k}_text"], t[f"badge_{k}_bg"], SMALL_MIN))
    return pairs


def css_variables(theme: str) -> str:
    return "\n".join(f"  --{k.replace('_', '-')}: {v};" for k, v in THEMES[theme].items())
