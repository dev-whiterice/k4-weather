"""Provino delle icone: le disegna alle dimensioni con cui appaiono davvero
sulla dashboard, cosi' i problemi di leggibilita' si vedono prima di andare in CI.

    PYTHONPATH=src python tools/icon_sheet.py out/icons.png
"""

from __future__ import annotations

import sys
from pathlib import Path

from k4weather.config import Config, Display, Location
from k4weather.render import ICONS, _font_face_css, _icon_markup
from k4weather.postprocess import to_eink_png

SIZES = [112, 26, 15]

CSS = """
body { margin:0; background:#fff; color:#000; font-family:Inter, sans-serif;
       -webkit-font-smoothing:antialiased; padding:16px 20px; }
.row { display:flex; align-items:flex-end; gap:18px; padding:10px 0;
       border-bottom:1px solid #ddd; }
.name { width:150px; font-size:11px; font-weight:600; letter-spacing:.04em; color:#444; }
.box { display:flex; align-items:center; justify-content:center; }
svg { display:block; }
"""


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

    height = 60 + len(names) * 135
    cfg = Config(
        location=Location("provino", 0, 0),
        display=Display(width=600, height=height, gray_levels=16),
    )

    from k4weather.render import html_to_png

    raw = Path(out).with_suffix(".raw.png")
    html_to_png(html, raw, cfg)
    report = to_eink_png(raw, Path(out), cfg)
    raw.unlink(missing_ok=True)
    print(report.describe())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out/icons.png")
