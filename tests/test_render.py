from datetime import datetime

import pytest

from k4weather.model import build_dashboard
from k4weather.postprocess import to_eink_png, validate
from k4weather.render import build_html, html_to_png


@pytest.fixture
def html(forecast, air_quality, cfg):
    now = datetime.fromisoformat(forecast["current"]["time"])
    return build_html(build_dashboard(forecast, air_quality, cfg, now=now), cfg)


def test_html_e_autoconsistente(html):
    # Nessuna risorsa esterna: in CI la pagina viene renderizzata offline e
    # il file deve restare apribile nel browser per l'anteprima di design.
    assert "data:font/woff2;base64," in html
    # Il namespace xmlns degli SVG e' un URL ma non viene mai scaricato:
    # cerchiamo solo i riferimenti che il browser proverebbe a caricare.
    for reference in ('src="http', 'href="http', "url(http", 'src="fonts/', 'href="style.css'):
        assert reference not in html


def test_html_contiene_i_dati(html):
    assert "CAORIA" not in html  # il maiuscolo e' un effetto CSS, non del dato
    assert "Caoria" in html
    assert "domenica 16 agosto" in html
    assert "percepiti" in html


def test_svg_inline_non_viene_escapato(html):
    assert "&lt;svg" not in html
    assert html.count("<svg") >= 8  # icona principale + 7 giorni


@pytest.mark.slow
def test_png_finale_e_valido_per_eips(tmp_path, html, cfg):
    raw = html_to_png(html, tmp_path / "raw.png", cfg)
    report = to_eink_png(raw, tmp_path / "dashboard.png", cfg)

    assert validate(report, cfg) == []
    # Un PNG grigio a 16 livelli di questa complessita' resta ben sotto i 100 kB;
    # se sfonda, qualcosa e' tornato a colori o e' entrato del rumore.
    assert report.size_bytes < 100_000
