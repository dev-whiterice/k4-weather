"""Moon phase and compass rose."""

from datetime import datetime, timedelta, timezone

import pytest

from k4weather import astro


def _at(year, month, day, hour=12):
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def test_known_new_moon_is_almost_dark():
    # New moon of 6 January 2000, the reference point of the cycle.
    phase = astro.moon_phase(_at(2000, 1, 6, 18))
    assert phase.illumination < 0.01
    assert phase.name == "Luna nuova"


def test_full_moon_at_mid_cycle():
    phase = astro.moon_phase(_at(2000, 1, 21, 12))
    assert phase.illumination > 0.97
    assert phase.name == "Luna piena"


def test_waxing_before_the_full_moon():
    assert astro.moon_phase(_at(2000, 1, 13)).waxing is True
    assert astro.moon_phase(_at(2000, 1, 28)).waxing is False


def test_naive_datetimes_are_read_as_utc():
    aware = astro.moon_phase(_at(2026, 3, 3))
    naive = astro.moon_phase(datetime(2026, 3, 3, 12))
    assert aware == naive


def test_illumination_always_a_valid_fraction():
    start = _at(2026, 1, 1)
    for day in range(60):
        phase = astro.moon_phase(start + timedelta(days=day))
        assert 0.0 <= phase.illumination <= 1.0


def test_moon_svg_is_well_formed():
    markup = astro.moon_svg(astro.moon_phase(_at(2026, 3, 3)), size=20)
    assert markup.startswith("<svg") and markup.endswith("</svg>")
    assert "NaN" not in markup


def test_moon_svg_survives_every_phase_of_the_cycle():
    start = _at(2026, 1, 1)
    for hour in range(0, 30 * 24, 6):
        markup = astro.moon_svg(astro.moon_phase(start + timedelta(hours=hour)))
        assert "NaN" not in markup and markup.count("<path") == 1


@pytest.mark.parametrize(
    "degrees,expected",
    [(0, "N"), (90, "E"), (180, "S"), (270, "O"), (315, "NO"), (359, "N"), (22, "NNE")],
)
def test_compass_rose(degrees, expected):
    assert astro.compass_point(degrees) == expected


def test_compass_rose_without_data():
    assert astro.compass_point(None) == ""
