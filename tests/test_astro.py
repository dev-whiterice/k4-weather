from datetime import datetime, timedelta, timezone

import pytest

from k4weather import astro


def _at(year, month, day, hour=12):
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def test_novilunio_noto_e_quasi_buio():
    # Novilunio del 6 gennaio 2000, usato come riferimento del ciclo.
    phase = astro.moon_phase(_at(2000, 1, 6, 18))
    assert phase.illumination < 0.01
    assert phase.name == "Luna nuova"


def test_plenilunio_a_meta_ciclo():
    phase = astro.moon_phase(_at(2000, 1, 21, 12))
    assert phase.illumination > 0.97
    assert phase.name == "Luna piena"


def test_crescente_prima_del_plenilunio():
    assert astro.moon_phase(_at(2000, 1, 13)).waxing is True
    assert astro.moon_phase(_at(2000, 1, 28)).waxing is False


def test_illuminazione_sempre_in_percentuale_valida():
    start = _at(2026, 1, 1)
    for day in range(60):
        phase = astro.moon_phase(start + timedelta(days=day))
        assert 0.0 <= phase.illumination <= 1.0


def test_svg_luna_e_ben_formato():
    markup = astro.moon_svg(astro.moon_phase(_at(2026, 3, 3)), size=20)
    assert markup.startswith("<svg") and markup.endswith("</svg>")
    assert "NaN" not in markup


@pytest.mark.parametrize(
    "gradi,atteso",
    [(0, "N"), (90, "E"), (180, "S"), (270, "O"), (315, "NO"), (359, "N"), (22, "NNE")],
)
def test_rosa_dei_venti(gradi, atteso):
    assert astro.compass_point(gradi) == atteso


def test_rosa_dei_venti_senza_dato():
    assert astro.compass_point(None) == ""
