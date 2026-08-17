"""The model layer: rounding, chart geometry and tolerance to broken payloads."""

import copy
from datetime import datetime, timedelta

from k4weather.model import (
    CHART_WIDTH,
    DAY_BAR_WIDTH,
    MIN_DAY_BAR_WIDTH,
    STALE_AFTER,
    build_dashboard,
)


def _at_fixture_time(forecast):
    """The instant the fixture was captured, so renders are reproducible."""
    return datetime.fromisoformat(forecast["current"]["time"])


def test_full_dashboard(forecast, air_quality, cfg):
    d = build_dashboard(forecast, air_quality, cfg, now=_at_fixture_time(forecast))

    assert d.location == "Caoria"
    assert d.date_long == "domenica 16 agosto"
    assert d.temperature == "19"  # 18.8 in the fixture, rounded
    assert d.condition == "Temporale"
    assert d.icon == "thunderstorm"
    assert len(d.days) == cfg.display.forecast_days
    assert len(d.hours) == cfg.display.hourly_hours
    assert d.sunrise and d.sunset
    assert d.moon_name


def test_apparent_temperature_is_exposed(forecast, cfg):
    d = build_dashboard(forecast, None, cfg, now=_at_fixture_time(forecast))
    assert d.apparent.endswith("°")
    assert d.apparent != "–"


def test_missing_apparent_temperature_becomes_a_dash(forecast, cfg):
    broken = copy.deepcopy(forecast)
    broken["current"]["apparent_temperature"] = None
    d = build_dashboard(broken, None, cfg, now=_at_fixture_time(forecast))
    assert d.apparent == "–"


def test_day_rows_carry_the_wind(forecast, cfg):
    d = build_dashboard(forecast, None, cfg, now=_at_fixture_time(forecast))
    assert d.wind_unit == "km/h"
    for day in d.days:
        assert day.wind.isdigit(), day.wind


def test_missing_wind_series_becomes_a_dash(forecast, cfg):
    without_wind = copy.deepcopy(forecast)
    del without_wind["daily"]["wind_speed_10m_max"]
    d = build_dashboard(without_wind, None, cfg, now=_at_fixture_time(forecast))
    assert [day.wind for day in d.days] == ["–"] * len(d.days)


def test_day_grid_starts_tomorrow(forecast, cfg):
    d = build_dashboard(forecast, None, cfg, now=_at_fixture_time(forecast))
    # 16 August 2026 is a Sunday: the first row of the grid is Monday.
    assert d.days[0].name == "LUN"


def test_day_bars_stay_inside_the_track(forecast, cfg):
    d = build_dashboard(forecast, None, cfg, now=_at_fixture_time(forecast))
    for day in d.days:
        assert day.bar_x >= 0
        assert day.bar_width >= MIN_DAY_BAR_WIDTH
        assert day.bar_x + day.bar_width <= DAY_BAR_WIDTH + 0.01


def test_hourly_chart_stays_inside_its_box(forecast, cfg):
    d = build_dashboard(forecast, None, cfg, now=_at_fixture_time(forecast))
    for hour in d.hours:
        assert 0 <= hour.x <= CHART_WIDTH
        assert 0 <= hour.temp_y <= d.chart_temp_height
        assert 0 <= hour.bar_height <= d.chart_bars_height
    assert d.temp_path.startswith("M ")
    assert d.temp_area_path.endswith("Z")


def test_extreme_labels_do_not_escape_the_chart(forecast, cfg):
    d = build_dashboard(forecast, None, cfg, now=_at_fixture_time(forecast))
    extremes = [h for h in d.hours if h.is_extreme]
    assert len(extremes) == 2
    for hour in extremes:
        assert 15 <= hour.label_x <= CHART_WIDTH - 15
        assert 0 < hour.label_y < d.chart_temp_height


def test_chart_starts_at_the_current_hour(forecast, cfg):
    now = _at_fixture_time(forecast)
    d = build_dashboard(forecast, None, cfg, now=now)
    assert d.hours[0].label == f"{now.hour:02d}"


def test_title_counts_the_hours_actually_drawn(forecast, cfg):
    short = copy.deepcopy(forecast)
    # Keep only the six hours that follow the observation.
    start = short["hourly"]["time"].index(_at_fixture_time(forecast).replace(minute=0).isoformat(timespec="minutes"))
    for key in ("time", "temperature_2m", "precipitation_probability"):
        short["hourly"][key] = short["hourly"][key][: start + 6]

    d = build_dashboard(short, None, cfg, now=_at_fixture_time(forecast))
    assert len(d.hours) == 6
    assert d.hourly_title == "Prossime 6 ore"


def test_missing_values_become_dashes(forecast, cfg):
    broken = copy.deepcopy(forecast)
    broken["current"]["temperature_2m"] = None
    broken["current"]["relative_humidity_2m"] = None
    broken["daily"]["uv_index_max"] = [None] * len(broken["daily"]["time"])

    d = build_dashboard(broken, None, cfg, now=_at_fixture_time(forecast))
    assert d.temperature == "–"
    assert d.metrics[0].value == "–"
    assert d.metrics[2].value == "–"


def test_truncated_series_do_not_raise(forecast, cfg):
    """A short payload must degrade to dashes, never skip the whole refresh."""
    truncated = copy.deepcopy(forecast)
    truncated["hourly"]["temperature_2m"] = truncated["hourly"]["temperature_2m"][:3]
    truncated["hourly"]["precipitation_probability"] = []
    del truncated["daily"]["precipitation_probability_max"]

    d = build_dashboard(truncated, None, cfg, now=_at_fixture_time(forecast))
    assert len(d.hours) == cfg.display.hourly_hours
    assert all(day.precip_label == "–" for day in d.days)


def test_empty_payload_does_not_raise(cfg):
    d = build_dashboard({}, None, cfg, now=datetime(2026, 8, 16, 22, 45))
    assert d.temperature == "–"
    assert d.days == [] and d.hours == []
    assert d.stale is False


def test_missing_air_quality_keeps_the_strip(forecast, cfg):
    d = build_dashboard(forecast, None, cfg, now=_at_fixture_time(forecast))
    aria = [m for m in d.metrics if m.label == "Aria"]
    assert len(aria) == 1 and aria[0].value == "–"


def test_recent_observation_is_not_flagged(forecast, cfg):
    d = build_dashboard(forecast, None, cfg, now=_at_fixture_time(forecast))
    assert d.stale is False


def test_old_observation_is_flagged(forecast, cfg):
    later = _at_fixture_time(forecast) + STALE_AFTER + timedelta(minutes=1)
    d = build_dashboard(forecast, None, cfg, now=later)
    assert d.stale is True


def test_isothermal_day_still_shows_a_bar(forecast, cfg):
    flat = copy.deepcopy(forecast)
    flat["daily"]["temperature_2m_min"][1] = 20.0
    flat["daily"]["temperature_2m_max"][1] = 20.0
    d = build_dashboard(flat, None, cfg, now=_at_fixture_time(forecast))
    assert d.days[0].bar_width >= MIN_DAY_BAR_WIDTH


def test_day_at_the_top_of_the_scale_still_shows_a_bar(forecast, cfg):
    """The warmest low of the week lands at x = DAY_BAR_WIDTH before clamping."""
    peaked = copy.deepcopy(forecast)
    days = len(peaked["daily"]["time"])
    peaked["daily"]["temperature_2m_min"] = [10.0] * days
    peaked["daily"]["temperature_2m_max"] = [20.0] * days
    peaked["daily"]["temperature_2m_min"][1] = 20.0
    peaked["daily"]["temperature_2m_max"][1] = 20.0

    d = build_dashboard(peaked, None, cfg, now=_at_fixture_time(forecast))
    assert d.days[0].bar_width >= MIN_DAY_BAR_WIDTH
    assert d.days[0].bar_x + d.days[0].bar_width <= DAY_BAR_WIDTH + 0.01
