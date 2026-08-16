"""Rendering: modello -> HTML autoconsistente -> screenshot PNG.

L'HTML incorpora font (base64) e icone (SVG inline) in modo da non dipendere da
risorse esterne: lo stesso file si apre nel browser per l'anteprima di design e
viene dato in pasto a Chromium headless in CI, con risultato identico.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from .config import Config
from .model import Dashboard

TEMPLATES = Path(__file__).parent / "templates"
FONTS = TEMPLATES / "fonts"
ICONS = TEMPLATES / "icons"

# (famiglia CSS, peso, file)
FONT_FACES = [
    ("Inter", 400, "Inter-Regular.woff2"),
    ("Inter", 500, "Inter-Medium.woff2"),
    ("Inter", 600, "Inter-SemiBold.woff2"),
    ("Inter", 700, "Inter-Bold.woff2"),
    ("Inter Display", 500, "InterDisplay-Medium.woff2"),
    ("Inter Display", 600, "InterDisplay-SemiBold.woff2"),
]


@lru_cache(maxsize=1)
def _font_face_css() -> str:
    blocks = []
    for family, weight, filename in FONT_FACES:
        encoded = base64.b64encode((FONTS / filename).read_bytes()).decode("ascii")
        blocks.append(
            f"@font-face{{font-family:'{family}';font-style:normal;"
            f"font-weight:{weight};font-display:block;"
            f"src:url(data:font/woff2;base64,{encoded}) format('woff2');}}"
        )
    return "".join(blocks)


@lru_cache(maxsize=64)
def _icon_markup(name: str) -> Markup:
    path = ICONS / f"{name}.svg"
    if not path.exists():
        path = ICONS / "unknown.svg"
    return Markup(path.read_text(encoding="utf-8").strip())


def build_html(dashboard: Dashboard, cfg: Config) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "j2"], default_for_string=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("dashboard.html.j2")
    return template.render(
        d=dashboard,
        cfg=cfg,
        icon=_icon_markup,
        styles=Markup((TEMPLATES / "style.css").read_text(encoding="utf-8")),
        font_face_css=Markup(_font_face_css()),
    )


def html_to_png(html: str, output: Path, cfg: Config) -> Path:
    """Screenshot dell'HTML con Chromium headless."""
    from playwright.sync_api import sync_playwright

    width, height = cfg.display.width, cfg.display.height
    scale = max(1, cfg.display.scale_factor)
    output.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb", "--font-render-hinting=full"])
        page = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=scale,
        ).new_page()
        page.set_content(html, wait_until="load")
        # I font sono inline, ma il layout va misurato solo a caricamento completo.
        page.evaluate("() => document.fonts.ready")
        page.screenshot(path=str(output), type="png",
                        clip={"x": 0, "y": 0, "width": width, "height": height})
        browser.close()
    return output
