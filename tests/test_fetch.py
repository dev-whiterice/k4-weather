"""The Open-Meteo client: query parameters and behaviour under failure.

The workflow runs unattended, so what matters most here is that a transient
error is retried and that a missing air quality reading never takes the whole
dashboard down with it.
"""

import pytest
import requests

from k4weather import fetch


class FakeSession:
    """Replays a canned sequence of outcomes and records the calls it got."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"status {self.status}")

    def json(self):
        return self.payload


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    """Retries are real, the waiting between them is not."""
    monkeypatch.setattr(fetch.time, "sleep", lambda _seconds: None)


def test_forecast_sends_the_configured_query(cfg):
    session = FakeSession([FakeResponse({"current": {}})])

    fetch.fetch_forecast(cfg, session=session)

    url, params, timeout = session.calls[0]
    assert url == fetch.FORECAST_URL
    assert params["latitude"] == cfg.location.latitude
    assert params["forecast_days"] == cfg.api_forecast_days
    assert params["wind_speed_unit"] == cfg.units.wind_speed
    # The daily wind is what the multi-day grid draws.
    assert "wind_speed_10m_max" in params["daily"]
    assert "apparent_temperature" in params["current"]
    assert timeout == fetch.TIMEOUT


def test_transient_failure_is_retried(cfg):
    session = FakeSession(
        [requests.ConnectionError("reset"), FakeResponse({"current": {"time": "now"}})]
    )

    assert fetch.fetch_forecast(cfg, session=session) == {"current": {"time": "now"}}
    assert len(session.calls) == 2


def test_forecast_gives_up_after_the_last_attempt(cfg):
    session = FakeSession([requests.ConnectionError("reset")] * fetch.ATTEMPTS)

    with pytest.raises(requests.ConnectionError):
        fetch.fetch_forecast(cfg, session=session)
    assert len(session.calls) == fetch.ATTEMPTS


def test_server_error_is_retried_then_raised(cfg):
    session = FakeSession([FakeResponse({}, status=503)] * fetch.ATTEMPTS)

    with pytest.raises(requests.HTTPError):
        fetch.fetch_forecast(cfg, session=session)
    assert len(session.calls) == fetch.ATTEMPTS


def test_air_quality_failure_is_not_fatal(cfg):
    session = FakeSession([requests.ConnectionError("down")] * fetch.ATTEMPTS)

    assert fetch.fetch_air_quality(cfg, session=session) is None


def test_air_quality_is_skipped_when_disabled(cfg):
    from dataclasses import replace

    disabled = replace(cfg, features=replace(cfg.features, air_quality=False))
    session = FakeSession([])

    assert fetch.fetch_air_quality(disabled, session=session) is None
    assert session.calls == []
