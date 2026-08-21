"""Rendering: the HTML must be self-contained, the PNG must satisfy `eips`."""

from datetime import datetime

import pytest

from dataclasses import replace

from k4weather import model
from k4weather.model import build_dashboard
from k4weather.postprocess import to_eink_png, validate
from k4weather.render import build_html, html_to_png
from k4weather.wmo import WMO_CODES


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
def test_the_indoor_slot_lands_where_the_kindle_writes(forecast, cfg):
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

    slot = model.indoor_slot()
    assert box == [slot.x, slot.y, slot.width, slot.height]


@pytest.mark.slow
def test_the_longest_condition_does_not_push_the_band_off_the_panel(forecast, cfg):
    """The widest text on the page must not be able to widen the page.

    `body` is a grid, and an implicit column sizes itself to its widest content:
    one long weather description would then stretch every section at once and
    carry the right-hand side of all of them past the panel — starting with the
    indoor temperature, which is positioned in absolute page pixels and would be
    the one thing that did not move with it.
    """
    from playwright.sync_api import sync_playwright

    cfg = replace(cfg, features=replace(cfg.features, indoor_temperature=True))
    now = datetime.fromisoformat(forecast["current"]["time"])
    d = build_dashboard(forecast, None, cfg, now=now)
    d.condition = max((c[0] for c in WMO_CODES.values()), key=len)
    # Negative and three digits wide, which is as much room as the figure ever
    # asks for.
    d.temperature = "-19"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_context(
                viewport={"width": cfg.display.width, "height": cfg.display.height}
            ).new_page()
            page.set_content(build_html(d, cfg), wait_until="load")
            page.evaluate("() => document.fonts.ready")
            measured = page.evaluate(
                """() => ({
                    page: document.body.scrollWidth,
                    range: document.querySelector('.now-range').getBoundingClientRect().right,
                    rule: document.querySelector('.indoor-rule').getBoundingClientRect().x,
                })"""
            )
        finally:
            browser.close()

    assert measured["page"] == cfg.display.width
    # And the outdoor half stays on its own side of the dividing rule.
    assert measured["range"] <= measured["rule"]


@pytest.mark.slow
def test_final_png_is_valid_for_eips(tmp_path, html, cfg):
    raw = html_to_png(html, tmp_path / "raw.png", cfg)
    report = to_eink_png(raw, tmp_path / "dashboard.png", cfg)

    assert validate(report, cfg) == []
    # A 16-level gray PNG of this complexity stays well below 100 kB; blowing
    # past that means colour or noise crept back in.
    assert report.size_bytes < 100_000


def test_every_configured_location_name_fits_beside_the_date(forecast, cfg):
    """The header holds the place on the left and the date on the right.

    They are the two ends of a flex row, so a name too long for the panel does
    not wrap or clip: it pushes the date until the two touch, and the first
    thing lost is the date. The check is against the real `config.yaml` because
    that is where the risk is — the layout was designed around "Caoria" and
    somebody will eventually add a name four times as long.
    """
    from playwright.sync_api import sync_playwright

    from k4weather.config import load_config

    configured = load_config("config.yaml").locations
    now = datetime.fromisoformat(forecast["current"]["time"])
    # The longest date the calendar produces, so the measurement is not flattered
    # by whichever day the fixture happens to fall on.
    longest_date = f"mercoledì 28 {max(model.MESI, key=len)}"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_context(
                viewport={"width": cfg.display.width, "height": cfg.display.height}
            ).new_page()

            for location in configured:
                d = build_dashboard(forecast, None, cfg, now=now, location=location)
                d.date_long = longest_date
                page.set_content(build_html(d, cfg), wait_until="load")
                page.evaluate("() => document.fonts.ready")
                measured = page.evaluate(
                    """() => ({
                        name: document.querySelector('.location').getBoundingClientRect(),
                        date: document.querySelector('.date').getBoundingClientRect(),
                        page: document.body.scrollWidth,
                    })"""
                )
                # A gap, not merely an absence of overlap: two words that touch
                # read as one, and there is no second line to fall onto.
                gap = measured["date"]["x"] - measured["name"]["right"]
                assert gap >= 16, f"{location.name}: only {gap:.0f}px before the date"
                assert measured["page"] == cfg.display.width, location.name
        finally:
            browser.close()
