"""Rendering: the HTML must be self-contained, the PNG must satisfy `eips`."""

from datetime import datetime

import pytest

from dataclasses import replace

from k4weather import model
from k4weather.model import build_dashboard
from k4weather.postprocess import to_eink_png, validate
from k4weather.render import build_html, html_to_png


@pytest.fixture
def html(forecast, air_quality, cfg):
    now = datetime.fromisoformat(forecast["current"]["time"])
    return build_html(build_dashboard(forecast, air_quality, cfg, now=now), cfg)


def test_html_is_self_contained(html):
    # No external resource: CI renders the page offline, and the file has to
    # stay openable in a browser for design previews.
    assert "data:font/woff2;base64," in html
    # The xmlns of an SVG is a URL but is never fetched: only look for the
    # references a browser would actually try to load.
    for reference in ('src="http', 'href="http', "url(http", 'src="fonts/', 'href="style.css'):
        assert reference not in html


def test_html_carries_the_data(html):
    assert "CAORIA" not in html  # the uppercase is a CSS effect, not the datum
    assert "Caoria" in html
    assert "domenica 16 agosto" in html
    assert "percepita" in html


def test_html_carries_the_daily_wind(html, forecast, cfg):
    now = datetime.fromisoformat(forecast["current"]["time"])
    days = build_dashboard(forecast, None, cfg, now=now).days
    assert html.count('class="d-wind"') == len(days)
    assert html.count(">km/h<") == len(days)


def test_inline_svg_is_not_escaped(html):
    assert "&lt;svg" not in html
    assert html.count("<svg") >= 8  # main icon + 7 days


def test_jinja_comments_do_not_reach_the_output(html):
    assert "{#" not in html and "#}" not in html


@pytest.mark.slow
def test_the_indoor_slot_lands_on_the_eips_character_grid(forecast, cfg):
    """The blank left for the Kindle has to be where the Kindle writes.

    Everything about that position is implicit in the CSS — the padding of the
    footer, the width of the icon, the height of the band — so measuring it in
    a real browser is the only way to know it is still true.
    """
    from playwright.sync_api import sync_playwright

    cfg = replace(cfg, features=replace(cfg.features, indoor_temperature=True))
    now = datetime.fromisoformat(forecast["current"]["time"])
    page_html = build_html(build_dashboard(forecast, None, cfg, now=now), cfg)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_context(
                viewport={"width": cfg.display.width, "height": cfg.display.height}
            ).new_page()
            page.set_content(page_html, wait_until="load")
            page.evaluate("() => document.fonts.ready")
            box = page.evaluate(
                "() => {const r = document.querySelector('.indoor-slot')"
                ".getBoundingClientRect(); return [r.x, r.y, r.width, r.height];}"
            )
        finally:
            browser.close()

    assert box == [
        model.INDOOR_SLOT_COL * model.EIPS_CELL_WIDTH,
        model.INDOOR_SLOT_ROW * model.EIPS_CELL_HEIGHT,
        model.INDOOR_SLOT_CHARS * model.EIPS_CELL_WIDTH,
        model.EIPS_CELL_HEIGHT,
    ]


@pytest.mark.slow
def test_final_png_is_valid_for_eips(tmp_path, html, cfg):
    raw = html_to_png(html, tmp_path / "raw.png", cfg)
    report = to_eink_png(raw, tmp_path / "dashboard.png", cfg)

    assert validate(report, cfg) == []
    # A 16-level gray PNG of this complexity stays well below 100 kB; blowing
    # past that means colour or noise crept back in.
    assert report.size_bytes < 100_000
