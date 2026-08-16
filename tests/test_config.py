import pytest

from k4weather.config import load_config

VALID = """
location:
  name: "Torino"
  latitude: 45.07
  longitude: 7.69
"""


def test_carica_i_valori_di_default(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(VALID, encoding="utf-8")

    cfg = load_config(path)

    assert cfg.location.name == "Torino"
    assert cfg.units.temperature == "celsius"
    assert cfg.display.width == 600 and cfg.display.height == 800
    # Oggi non e' una riga della griglia ma serve comunque all'API.
    assert cfg.api_forecast_days == cfg.display.forecast_days + 1


def test_config_reale_del_repo_e_valida():
    cfg = load_config("config.yaml")
    assert cfg.display.gray_levels == 16
    assert -90 <= cfg.location.latitude <= 90
    assert -180 <= cfg.location.longitude <= 180


def test_localita_obbligatoria(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("units:\n  temperature: celsius\n", encoding="utf-8")
    with pytest.raises(ValueError, match="location"):
        load_config(path)


def test_valori_fuori_range_vengono_respinti(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(VALID + "\ndisplay:\n  forecast_days: 40\n", encoding="utf-8")
    with pytest.raises(ValueError, match="forecast_days"):
        load_config(path)
