"""Draw draft/assets/results.svg from output/results.json. Nothing in the figure is typed by hand."""
import argparse
import json
from html import escape
from pathlib import Path

from extractbench.config import OUTPUT_DIR

PATHS = [("scraper", "Built-in scraper", "#10b981"),
         ("autoparse", "autoparse", "#0ea5e9"),
         ("markdown_llm", "Markdown + LLM", "#f59e0b")]
SITES = [("amazon", "Amazon"), ("walmart", "Walmart")]
PANELS = [
    ("Mean fill rate, 8 keys", lambda s: s["fill_rate"]["mean"], "pct", 1.0),
    ("Identical across 3 runs", lambda s: s["consistency"]["rate"], "pct", 1.0),
    ("Non-null values not found in page text", lambda s: s["invented"]["rate"], "pct", None),
    ("Median latency per page", lambda s: s["latency"]["median_s"], "s", None),
]
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "draft" / "assets" / "results.svg"


def fmt(value, unit):
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%" if unit == "pct" else f"{value:.1f} s"


def panel(x, y, w, h, title, getter, unit, fixed_max, paths) -> list[str]:
    values = {}
    for key, _, _ in PATHS:
        for site, _ in SITES:
            block = paths.get(key, {}).get(site)
            values[(key, site)] = getter(block) if block else None
    present = [v for v in values.values() if v is not None]
    top = fixed_max or (max(present) * 1.15 if present and max(present) > 0 else 1)
    out = [f'<text x="{x}" y="{y}" class="h">{escape(title)}</text>']
    base = y + h
    out.append(f'<line x1="{x}" y1="{base}" x2="{x + w}" y2="{base}" stroke="#cbd5e1"/>')
    group_w = w / len(SITES)
    bar_w = (group_w - 36) / len(PATHS)
    for gi, (site, label) in enumerate(SITES):
        gx = x + gi * group_w + 12
        out.append(f'<text x="{gx + (group_w - 24) / 2}" y="{base + 18}" text-anchor="middle" class="s">{label}</text>')
        for pi, (key, _, colour) in enumerate(PATHS):
            bx = gx + pi * bar_w
            v = values[(key, site)]
            if v is None:
                out.append(f'<rect x="{bx + 3}" y="{base - 40}" width="{bar_w - 6}" height="40" fill="none" '
                           f'stroke="{colour}" stroke-dasharray="4 3"/>')
                out.append(f'<text x="{bx + bar_w / 2}" y="{base - 16}" text-anchor="middle" class="t">not run</text>')
                continue
            bh = max(1.5, (h - 30) * v / top)
            out.append(f'<rect x="{bx + 3}" y="{base - bh}" width="{bar_w - 6}" height="{bh}" fill="{colour}"/>')
            out.append(f'<text x="{bx + bar_w / 2}" y="{base - bh - 5}" text-anchor="middle" class="v">{fmt(v, unit)}</text>')
    return out


def render(results: dict) -> str:
    width, height = 760, 640
    paths = results["paths"]
    n = results.get("urls", {})
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        'role="img" aria-labelledby="t d">',
        '<title id="t">Measured results: three extraction paths on Amazon and Walmart product pages</title>',
        f'<desc id="d">Generated from results.json ({escape(results.get("generated_at", ""))}). '
        f'{n.get("amazon", 0)} Amazon and {n.get("walmart", 0)} Walmart URLs, {results.get("runs")} runs per path.</desc>',
        '<style>text{font-family:"Segoe UI",Helvetica,Arial,sans-serif;fill:#0f172a}'
        '.h{font-size:14px;font-weight:600}.s{font-size:12.5px;fill:#334155}.t{font-size:11px;fill:#64748b}'
        '.v{font-size:11.5px;font-weight:600}</style>',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
    ]
    lx = 40
    for key, label, colour in PATHS:
        status = "" if key in paths else " (not run)"
        parts.append(f'<rect x="{lx}" y="22" width="14" height="14" fill="{colour}"/>')
        parts.append(f'<text x="{lx + 20}" y="34" class="s">{escape(label + status)}</text>')
        lx += 210
    positions = [(40, 80), (410, 80), (40, 350), (410, 350)]
    for (px, py), (title, getter, unit, fixed_max) in zip(positions, PANELS):
        parts += panel(px, py, 310, 200, title, getter, unit, fixed_max, paths)
    model = results.get("llm_models_returned") or []
    notes = [
        "Page-text check: the LLM against the Markdown it read. The parsers against a separate Markdown",
        "crawl of the same run, so their bars also count page variation between two crawls.",
        f'{n.get("amazon", 0)} Amazon + {n.get("walmart", 0)} Walmart URLs, {results.get("runs")} runs per path. '
        f'LLM: {", ".join(model) if model else "not run"}. Source: code/final/output/results.json',
    ]
    for i, line in enumerate(notes):
        y = height - 14 - 16 * (len(notes) - 1 - i)
        parts.append(f'<text x="{width / 2}" y="{y}" text-anchor="middle" class="t">{escape(line)}</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=OUTPUT_DIR / "results.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    results = json.loads(args.results.read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(results), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
