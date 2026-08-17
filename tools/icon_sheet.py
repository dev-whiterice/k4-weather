"""Icon contact sheet: draws every icon at the sizes it really appears on the
dashboard, so legibility problems show up before CI does.

    PYTHONPATH=src python tools/icon_sheet.py out/icons.png
"""

from __future__ import annotations

import sys
from pathlib import Path

from k4weather.config import Config, Display, Location
from k4weather.postprocess import to_eink_png
from k4weather.render import ICONS, _font_face_css, _icon_markup, html_to_png

# Current block, daily grid, footer. At 26px many ideas that work large stop
# working at all, which is the point of the sheet.
SIZES = [112, 26, 15]

# Deliberately plain: the sheet is a tool, not a design surface.
CSS = """
body { margin:0; background:#fff; color:#000; font-family:Inter, sans-serif;
       -webkit-font-smoothing:antialiased; padding:16px 20px; }
.row { display:flex; align-items:flex-end; gap:18px; padding:10px 0;
       border-bottom:1px solid #ddd; }
.name { width:150px; font-size:11px; font-weight:600; letter-spacing:.04em; color:#444; }
.box { display:flex; align-items:center; justify-content:center; }
svg { display:block; }
"""

# Page padding plus the height of one row at the largest size.
ROW_HEIGHT = 135
SHEET_MARGIN = 60


def main(out: str) -> None:
    names = sorted(p.stem for p in ICONS.glob("*.svg"))
    rows = []
    for name in names:
        cells = "".join(
            f'<div class="box" style="width:{s}px;height:{s}px">{_icon_markup(name)}</div>'
            for s in SIZES
        )
        rows.append(f'<div class="row"><div class="name">{name}</div>{cells}</div>')

    html = (
        f"<!DOCTYPE html><meta charset=utf-8><style>{_font_face_css()}</style>"
        f"<style>{CSS}</style>{''.join(rows)}"
    )

    # Same pipeline as the dashboard, so the sheet shows the icons exactly as
    # the panel will: 16 grays, no colour, no alpha.
    cfg = Config(
        location=Location("contact sheet", 0, 0),
        display=Display(width=600, height=SHEET_MARGIN + len(names) * ROW_HEIGHT,
                        gray_levels=16),
    )

    raw = Path(out).with_suffix(".raw.png")
    try:
        html_to_png(html, raw, cfg)
        report = to_eink_png(raw, Path(out), cfg)
    finally:
        raw.unlink(missing_ok=True)
    print(report.describe())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out/icons.png")
