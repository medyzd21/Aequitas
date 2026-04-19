"""Design tokens for the Aequitas Reflex frontend.

Palette matches the Streamlit dark theme (`.streamlit/config.toml`) so that
the two apps feel like the same product during the migration period.
"""
from __future__ import annotations

PALETTE: dict[str, str] = {
    "bg":     "#0b1220",   # page background (deep navy slate)
    "panel":  "#111a2e",   # cards, sidebar, KPI tiles
    "edge":   "#1f2a44",   # 1px borders
    "text":   "#e2e8f0",   # primary text (slate-200)
    "muted":  "#94a3b8",   # secondary text (slate-400)
    "accent": "#38bdf8",   # cyan-400 — buttons, links, emphasis
    "good":   "#34d399",   # emerald — HEALTHY
    "warn":   "#f59e0b",   # amber — WATCH
    "bad":    "#ef4444",   # red — STRESS
}

SERIES: list[str] = [
    "#38bdf8",   # cyan
    "#a78bfa",   # violet
    "#34d399",   # emerald
    "#f59e0b",   # amber
    "#f472b6",   # pink
    "#60a5fa",   # blue
]

# ----------------------------------------------------------- shared style dicts
APP_STYLE: dict = {
    "background": PALETTE["bg"],
    "color":      PALETTE["text"],
    "font_family": "Inter, system-ui, -apple-system, Segoe UI, sans-serif",
    "min_height": "100vh",
}

CARD_STYLE: dict = {
    "background":    PALETTE["panel"],
    "border":        f"1px solid {PALETTE['edge']}",
    "border_radius": "10px",
    "padding":       "14px 16px",
    "box_shadow":    "0 2px 10px rgba(0,0,0,0.25)",
}

KPI_TILE_STYLE: dict = {
    **CARD_STYLE,
    "flex":    "1 1 0",
    "min_width": "140px",
}

RIBBON_STYLE: dict = {
    "background":    PALETTE["panel"],
    "border":        f"1px solid {PALETTE['edge']}",
    "border_radius": "8px",
    "padding":       "8px 12px",
    "font_size":     "12px",
    "color":         PALETTE["muted"],
}

PILL_STYLES: dict[str, dict] = {
    "good":  {"background": "rgba(52,211,153,0.15)", "color": PALETTE["good"],
              "border": f"1px solid {PALETTE['good']}"},
    "warn":  {"background": "rgba(245,158,11,0.15)", "color": PALETTE["warn"],
              "border": f"1px solid {PALETTE['warn']}"},
    "bad":   {"background": "rgba(239,68,68,0.15)",  "color": PALETTE["bad"],
              "border": f"1px solid {PALETTE['bad']}"},
    "muted": {"background": "rgba(148,163,184,0.12)", "color": PALETTE["muted"],
              "border": f"1px solid {PALETTE['edge']}"},
}
