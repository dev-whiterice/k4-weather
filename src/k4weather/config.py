"""Caricamento e validazione della configurazione."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Location:
    name: str
    latitude: float
    longitude: float
    timezone: str = "auto"


@dataclass(frozen=True)
class Units:
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
    width: int = 600
    height: int = 800
    forecast_days: int = 7
    hourly_hours: int = 24
    gray_levels: int = 16
    scale_factor: int = 1


@dataclass(frozen=True)
class Features:
    air_quality: bool = True
    moon_phase: bool = True
    sun_times: bool = True


@dataclass(frozen=True)
class Config:
    location: Location
    units: Units = field(default_factory=Units)
    display: Display = field(default_factory=Display)
    features: Features = field(default_factory=Features)

    @property
    def api_forecast_days(self) -> int:
        """Giorni da chiedere all'API: oggi piu quelli mostrati in griglia."""
        return self.display.forecast_days + 1


def load_config(path: str | Path = "config.yaml") -> Config:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if "location" not in data:
        raise ValueError(f"{path}: manca la sezione 'location'")
    cfg = Config(
        location=Location(**data["location"]),
        units=Units(**data.get("units", {})),
        display=Display(**data.get("display", {})),
        features=Features(**data.get("features", {})),
    )
    if not 1 <= cfg.display.forecast_days <= 15:
        raise ValueError("display.forecast_days deve essere tra 1 e 15")
    if not 2 <= cfg.display.gray_levels <= 256:
        raise ValueError("display.gray_levels deve essere tra 2 e 256")
    return cfg
