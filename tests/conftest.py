import json
from pathlib import Path

import pytest

from k4weather.config import Config, Display, Features, Location, Units

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def cfg() -> Config:
    return Config(
        location=Location(name="Caoria", latitude=46.19647, longitude=11.67804),
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
