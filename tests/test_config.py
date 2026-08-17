"""Configuration loading: defaults, and rejection of values that would only
break much later, in the middle of an unattended run."""

import pytest

from k4weather.config import load_config

VALID = """
location:
  name: "Torino"
  latitude: 45.07
  longitude: 7.69
"""


def _write(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_are_applied(tmp_path):
    cfg = load_config(_write(tmp_path, VALID))

    assert cfg.location.name == "Torino"
    assert cfg.units.temperature == "celsius"
    assert cfg.units.wind_symbol == "km/h"
    assert cfg.display.width == 600 and cfg.display.height == 800
    # Today is not a row of the grid but the API still has to return it.
    assert cfg.api_forecast_days == cfg.display.forecast_days + 1


def test_repository_config_is_valid():
    cfg = load_config("config.yaml")
    assert cfg.display.gray_levels == 16
    assert -90 <= cfg.location.latitude <= 90
    assert -180 <= cfg.location.longitude <= 180


def test_location_is_required(tmp_path):
    path = _write(tmp_path, "units:\n  temperature: celsius\n")
    with pytest.raises(ValueError, match="location"):
        load_config(path)


def test_unknown_key_is_reported_as_a_config_error(tmp_path):
    path = _write(tmp_path, VALID + "\ndisplay:\n  widht: 600\n")
    with pytest.raises(ValueError, match="widht"):
        load_config(path)


def test_section_that_is_not_a_mapping_is_rejected(tmp_path):
    path = _write(tmp_path, VALID + "\nunits: celsius\n")
    with pytest.raises(ValueError, match="units"):
        load_config(path)


@pytest.mark.parametrize(
    "extra,message",
    [
        ("display:\n  forecast_days: 40\n", "forecast_days"),
        ("display:\n  hourly_hours: 0\n", "hourly_hours"),
        ("display:\n  gray_levels: 1\n", "gray_levels"),
        ("display:\n  scale_factor: 0\n", "scale_factor"),
        ("units:\n  wind_speed: knots\n", "wind_speed"),
        ("units:\n  temperature: kelvin\n", "temperature"),
    ],
)
def test_out_of_range_values_are_rejected(tmp_path, extra, message):
    path = _write(tmp_path, VALID + "\n" + extra)
    with pytest.raises(ValueError, match=message):
        load_config(path)


def test_impossible_coordinates_are_rejected(tmp_path):
    path = _write(tmp_path, "location:\n  name: x\n  latitude: 120\n  longitude: 7\n")
    with pytest.raises(ValueError, match="latitude"):
        load_config(path)
