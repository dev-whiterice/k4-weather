"""Open-Meteo client.

Two separate endpoints: forecast and air quality. Air quality is a bonus — if
it fails the rest of the dashboard is still generated.

Both calls are retried: the workflow runs unattended every 30 minutes and a
single dropped connection would otherwise cost a whole refresh cycle.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .config import Config

log = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

TIMEOUT = 20
ATTEMPTS = 3
# Linear backoff between attempts; the API is rate-limited per minute, so
# retrying immediately would only burn the remaining budget.
RETRY_DELAY = 3


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


def _get_json(
    url: str,
    params: dict[str, Any],
    session: requests.Session | None,
    sleep: float = RETRY_DELAY,
) -> dict[str, Any]:
    """GET returning parsed JSON, retried on transport and 5xx errors.

    The last exception is re-raised, so the caller decides whether the failure
    is fatal (forecast) or merely degrades the output (air quality).
    """
    http = session or requests
    last: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            response = http.get(url, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last = exc
            if attempt < ATTEMPTS:
                log.warning("%s: attempt %d/%d failed (%s)", url, attempt, ATTEMPTS, exc)
                time.sleep(sleep)
    assert last is not None  # the loop only exits here after an exception
    raise last


def fetch_forecast(cfg: Config, session: requests.Session | None = None) -> dict[str, Any]:
    """Forecast payload: current observation, hourly series and daily series."""
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
    return _get_json(FORECAST_URL, params, session)


def fetch_air_quality(
    cfg: Config, session: requests.Session | None = None
) -> dict[str, Any] | None:
    """Air quality; None when disabled or unreachable."""
    if not cfg.features.air_quality:
        return None
    params = {
        "latitude": cfg.location.latitude,
        "longitude": cfg.location.longitude,
        "current": "european_aqi,pm2_5",
        "timezone": cfg.location.timezone,
    }
    try:
        return _get_json(AIR_QUALITY_URL, params, session)
    except requests.RequestException as exc:
        log.warning("air quality unavailable: %s", exc)
        return None
