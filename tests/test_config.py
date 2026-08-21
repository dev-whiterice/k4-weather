"""Configuration loading: defaults, and rejection of values that would only
break much later, in the middle of an unattended run.

The location list gets the most attention here on purpose. A bad id is the one
mistake that survives every check downstream and shows up hours later as a 404
on a device with no screen to report it on.
"""

import pytest

from k4weather.config import MAX_LOCATIONS, load_config

VALID = """
locations:
  - id: torino
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
    for location in cfg.locations:
        assert -90 <= location.latitude <= 90
        assert -180 <= location.longitude <= 180


# ------------------------------------------------------------ the location list


def test_the_first_location_is_the_primary_one(tmp_path):
    path = _write(tmp_path, """
locations:
  - id: torino
    name: "Torino"
    latitude: 45.07
    longitude: 7.69
  - id: caoria
    name: "Caoria"
    latitude: 46.19
    longitude: 11.67
""")
    cfg = load_config(path)

    assert [location.id for location in cfg.locations] == ["torino", "caoria"]
    assert cfg.location.id == "torino"


def test_the_id_decides_the_file_name(tmp_path):
    # The whole naming scheme lives in one property; the manifest and the
    # device only ever read it back out of what CI published.
    cfg = load_config(_write(tmp_path, VALID))
    assert cfg.location.image == "dashboard-torino.png"


def test_locations_are_required(tmp_path):
    path = _write(tmp_path, "units:\n  temperature: celsius\n")
    with pytest.raises(ValueError, match="locations"):
        load_config(path)


def test_an_empty_location_list_is_rejected(tmp_path):
    path = _write(tmp_path, "locations: []\n")
    with pytest.raises(ValueError, match="non-empty"):
        load_config(path)


@pytest.mark.parametrize(
    "bad_id",
    ["Torino", "san remo", "città", "-torino", "torino/nord", ""],
)
def test_an_id_that_would_not_survive_a_url_is_rejected(tmp_path, bad_id):
    path = _write(tmp_path, f"""
locations:
  - id: "{bad_id}"
    name: "x"
    latitude: 45.07
    longitude: 7.69
""")
    with pytest.raises(ValueError, match="id"):
        load_config(path)


def test_duplicate_ids_are_rejected(tmp_path):
    # They would publish to the same file: the second render silently
    # overwrites the first and one place appears under two names.
    path = _write(tmp_path, """
locations:
  - id: torino
    name: "Torino"
    latitude: 45.07
    longitude: 7.69
  - id: torino
    name: "Torino centro"
    latitude: 45.08
    longitude: 7.70
""")
    with pytest.raises(ValueError, match="duplicate"):
        load_config(path)


def test_too_many_locations_are_rejected(tmp_path):
    entries = "".join(
        f'  - id: p{index}\n    name: "P{index}"\n    latitude: 45.0\n    longitude: 7.0\n'
        for index in range(MAX_LOCATIONS + 1)
    )
    with pytest.raises(ValueError, match=str(MAX_LOCATIONS)):
        load_config(_write(tmp_path, "locations:\n" + entries))


def test_impossible_coordinates_are_rejected(tmp_path):
    path = _write(tmp_path, """
locations:
  - id: x
    name: x
    latitude: 120
    longitude: 7
""")
    with pytest.raises(ValueError, match="latitude"):
        load_config(path)


def test_a_location_missing_a_key_names_the_entry(tmp_path):
    path = _write(tmp_path, """
locations:
  - id: torino
    name: "Torino"
    latitude: 45.07
  - id: caoria
    name: "Caoria"
    latitude: 46.19
    longitude: 11.67
""")
    with pytest.raises(ValueError, match=r"locations\[0\]"):
        load_config(path)


# ------------------------------------------------------------- everything else


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
