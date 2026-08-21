"""Rendering: model -> self-contained HTML -> PNG screenshot.

The HTML embeds fonts (base64) and icons (inline SVG) so that it depends on no
external resource: the very same file opens in a browser for design previews
and is fed to headless Chromium in CI, with identical results.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from .config import Config
from .model import Dashboard

TEMPLATES = Path(__file__).parent / "templates"
FONTS = TEMPLATES / "fonts"
ICONS = TEMPLATES / "icons"

# (CSS family, weight, file)
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
    """`@font-face` rules with the woff2 files inlined as data URIs."""
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
    """Inline SVG for an icon name, falling back to `unknown.svg`.

    Marked safe on purpose: the files are part of the repository, never user
    input, and escaping them would print the markup instead of drawing it.
    """
    path = ICONS / f"{name}.svg"
    if not path.exists():
        path = ICONS / "unknown.svg"
    return Markup(path.read_text(encoding="utf-8").strip())


@lru_cache(maxsize=1)
def _environment() -> Environment:
    """Jinja environment for the bundled templates, built once per process."""
    return Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "j2"], default_for_string=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def build_html(dashboard: Dashboard, cfg: Config) -> str:
    """Render the dashboard model into a single self-contained HTML document."""
    template = _environment().get_template("dashboard.html.j2")
    return template.render(
        d=dashboard,
        cfg=cfg,
        icon=_icon_markup,
        styles=Markup((TEMPLATES / "style.css").read_text(encoding="utf-8")),
        font_face_css=Markup(_font_face_css()),
    )


@contextmanager
def screenshotter(cfg: Config) -> Iterator[Callable[[str, Path], Path]]:
    """One Chromium session, yielding a `take(html, output)` that reuses it.

    Launching the browser is by far the slowest part of a render — seconds,
    against tens of milliseconds for the screenshot itself — so a run that
    draws one image per location opens it once and keeps it. The page is reused
    too: `set_content` replaces the whole document, so nothing carries over
    between images except the font cache, which is exactly what we want warm.
    """
    from playwright.sync_api import sync_playwright

    width, height = cfg.display.width, cfg.display.height
    scale = max(1, cfg.display.scale_factor)

    with sync_playwright() as p:
        # sRGB and full hinting keep the output identical between a developer's
        # machine and the CI runner.
        browser = p.chromium.launch(
            args=["--force-color-profile=srgb", "--font-render-hinting=full"]
        )
        try:
            page = browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=scale,
            ).new_page()

            def take(html: str, output: Path) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                page.set_content(html, wait_until="load")
                # Fonts are inlined, but the layout must only be measured once
                # they are actually loaded.
                page.evaluate("() => document.fonts.ready")
                page.screenshot(path=str(output), type="png",
                                clip={"x": 0, "y": 0, "width": width, "height": height})
                return output

            yield take
        finally:
            # Without this a failed screenshot leaks a Chromium process and the
            # CI job hangs until its timeout.
            browser.close()


def html_to_png(html: str, output: Path, cfg: Config) -> Path:
    """Screenshot one HTML document with headless Chromium."""
    with screenshotter(cfg) as take:
        return take(html, output)
