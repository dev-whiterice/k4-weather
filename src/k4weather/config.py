"""Loading and validation of `config.yaml`.

The config is read once per run and then passed around frozen: nothing in the
pipeline may mutate it, so a render is fully described by the file on disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Upper bound imposed by Open-Meteo on the `forecast_days` query parameter.
MAX_API_FORECAST_DAYS = 16


@dataclass(frozen=True)
class Location:
    """The place the dashboard is about. `timezone: auto` lets the API resolve it."""

    name: str
    latitude: float
    longitude: float
    timezone: str = "auto"


@dataclass(frozen=True)
class Units:
    """Measurement units, forwarded to the API and reused for the on-screen labels."""

    temperature: str = "celsius"
    wind_speed: str = "kmh"
    precipitation: str = "mm"

    @property
    def temperature_symbol(self) -> str:
        return "°F" if self.temperature == "fahrenheit" else "°C"

    @property
    def wind_symbol(self) -> str:
        return {"kmh": "km/h", "ms": "m/s", "mph": "mph", "kn": "kn"}[self.wind_speed]


@dataclass(frozen=True)
class Display:
    """Panel geometry and how much of the forecast fits on it."""

    width: int = 600
    height: int = 800
    forecast_days: int = 7
    hourly_hours: int = 24
    gray_levels: int = 16
    scale_factor: int = 1


@dataclass(frozen=True)
class Features:
    """Optional blocks. Turning one off removes it from the layout, not just its data."""

    air_quality: bool = True
    moon_phase: bool = True
    sun_times: bool = True
    # Off by default: the value is written by the Kindle itself, so on any
    # other screen the slot would stay empty for ever. See kindle/README.md.
    indoor_temperature: bool = False


@dataclass(frozen=True)
class Config:
    location: Location
    units: Units = field(default_factory=Units)
    display: Display = field(default_factory=Display)
    features: Features = field(default_factory=Features)

    @property
    def api_forecast_days(self) -> int:
        """Days to request from the API: today plus the ones shown in the grid."""
        return self.display.forecast_days + 1


def _section(data: dict, key: str) -> dict:
    """A mapping section of the YAML file, rejecting anything that is not one.

    Without this check a malformed section reaches the dataclass constructor and
    surfaces as an opaque `TypeError` from a stdlib frame.
    """
    value = data.get(key) or {}
    if not isinstance(value, dict):
        raise ValueError(f"section '{key}' must be a mapping, got {type(value).__name__}")
    return value


def load_config(path: str | Path = "config.yaml") -> Config:
    """Read and validate the configuration, raising ValueError on bad input."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: the file must contain a mapping")
    if "location" not in data:
        raise ValueError(f"{path}: missing 'location' section")

    try:
        cfg = Config(
            location=Location(**_section(data, "location")),
            units=Units(**_section(data, "units")),
            display=Display(**_section(data, "display")),
            features=Features(**_section(data, "features")),
        )
    except TypeError as exc:  # unknown or missing key in one of the sections
        raise ValueError(f"{path}: {exc}") from exc

    if not -90 <= cfg.location.latitude <= 90:
        raise ValueError("location.latitude must be between -90 and 90")
    if not -180 <= cfg.location.longitude <= 180:
        raise ValueError("location.longitude must be between -180 and 180")
    if cfg.units.wind_speed not in {"kmh", "ms", "mph", "kn"}:
        raise ValueError("units.wind_speed must be one of kmh, ms, mph, kn")
    if cfg.units.temperature not in {"celsius", "fahrenheit"}:
        raise ValueError("units.temperature must be celsius or fahrenheit")
    if cfg.units.precipitation not in {"mm", "inch"}:
        raise ValueError("units.precipitation must be mm or inch")
    # `api_forecast_days` is one more than the rows in the grid, so the ceiling
    # here is one below the API's own limit.
    if not 1 <= cfg.display.forecast_days <= MAX_API_FORECAST_DAYS - 1:
        raise ValueError(
            f"display.forecast_days must be between 1 and {MAX_API_FORECAST_DAYS - 1}"
        )
    if not 1 <= cfg.display.hourly_hours <= 48:
        raise ValueError("display.hourly_hours must be between 1 and 48")
    if not 2 <= cfg.display.gray_levels <= 256:
        raise ValueError("display.gray_levels must be between 2 and 256")
    if cfg.display.width <= 0 or cfg.display.height <= 0:
        raise ValueError("display.width and display.height must be positive")
    if cfg.display.scale_factor < 1:
        raise ValueError("display.scale_factor must be at least 1")
    return cfg
