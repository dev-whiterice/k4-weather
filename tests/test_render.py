"""Rendering: the HTML must be self-contained, the PNG must satisfy `eips`."""

from datetime import datetime

import pytest

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
def test_final_png_is_valid_for_eips(tmp_path, html, cfg):
    raw = html_to_png(html, tmp_path / "raw.png", cfg)
    report = to_eink_png(raw, tmp_path / "dashboard.png", cfg)

    assert validate(report, cfg) == []
    # A 16-level gray PNG of this complexity stays well below 100 kB; blowing
    # past that means colour or noise crept back in.
    assert report.size_bytes < 100_000
