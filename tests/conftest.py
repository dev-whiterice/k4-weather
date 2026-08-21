"""Shared fixtures.

The JSON files under `fixtures/` are real Open-Meteo responses, so previews and
tests are reproducible and never touch the network.
"""

import json
from pathlib import Path

import pytest

from k4weather.config import Config, Display, Features, Location, Units

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def cfg() -> Config:
    """The default configuration, pinned to the location of the fixtures."""
    return Config(
        locations=(Location(id="caoria", name="Caoria", latitude=46.19647, longitude=11.67804),),
        units=Units(),
        display=Display(),
        features=Features(),
    )


@pytest.fixture
def forecast() -> dict:
    return json.loads((FIXTURES / "forecast_caoria.json").read_text(encoding="utf-8"))


@pytest.fixture
def air_quality() -> dict:
    return json.loads((FIXTURES / "air_quality_caoria.json").read_text(encoding="utf-8"))
