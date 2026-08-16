"""Client Open-Meteo.

Due endpoint distinti: previsioni e qualita dell'aria. La qualita dell'aria e'
un extra: se fallisce, il resto della dashboard viene generato comunque.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from .config import Config

log = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

TIMEOUT = 20

CURRENT_VARS = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "is_day",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
    "precipitation",
]

HOURLY_VARS = [
    "temperature_2m",
    "precipitation_probability",
    "weather_code",
]

DAILY_VARS = [
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
    "precipitation_sum",
    "wind_speed_10m_max",
    "uv_index_max",
    "sunrise",
    "sunset",
]


def fetch_forecast(cfg: Config, session: requests.Session | None = None) -> dict[str, Any]:
    params = {
        "latitude": cfg.location.latitude,
        "longitude": cfg.location.longitude,
        "current": ",".join(CURRENT_VARS),
        "hourly": ",".join(HOURLY_VARS),
        "daily": ",".join(DAILY_VARS),
        "timezone": cfg.location.timezone,
        "forecast_days": cfg.api_forecast_days,
        "temperature_unit": cfg.units.temperature,
        "wind_speed_unit": cfg.units.wind_speed,
        "precipitation_unit": cfg.units.precipitation,
    }
    http = session or requests
    response = http.get(FORECAST_URL, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def fetch_air_quality(
    cfg: Config, session: requests.Session | None = None
) -> dict[str, Any] | None:
    """Qualita dell'aria; None se disabilitata o non raggiungibile."""
    if not cfg.features.air_quality:
        return None
    params = {
        "latitude": cfg.location.latitude,
        "longitude": cfg.location.longitude,
        "current": "european_aqi,pm2_5",
        "timezone": cfg.location.timezone,
    }
    try:
        http = session or requests
        response = http.get(AIR_QUALITY_URL, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        log.warning("qualita dell'aria non disponibile: %s", exc)
        return None
