"""Normalisation of the Open-Meteo responses into the model that feeds the template.

All the logic (rounding, formatting, chart geometry) lives here: the template
stays declarative and only places values that are already print-ready.

The API payloads are treated as untrusted: every series is read through
`_series`/`_at`, so a missing or short array degrades to a dash on screen
instead of raising and skipping the whole 30-minute refresh.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from markupsafe import Markup

from . import astro, wmo
from .config import Config

# Hourly chart geometry, in SVG units (they match the pixels of the final PNG).
CHART_WIDTH = 556
CHART_TEMP_HEIGHT = 74
CHART_BARS_HEIGHT = 24
CHART_GAP = 6
CHART_HEIGHT = CHART_TEMP_HEIGHT + CHART_GAP + CHART_BARS_HEIGHT

# Width of the min/max bar in the daily grid.
DAY_BAR_WIDTH = 240
# Shortest bar we still draw: an isothermal day must not disappear.
MIN_DAY_BAR_WIDTH = 10.0

# Past this gap between observation and generation the dashboard declares
# itself out of date.
STALE_AFTER = timedelta(minutes=90)

# The indoor temperature is the one number this program cannot render: the
# sensor is on the Kindle and the image is built in the cloud. The device draws
# it itself with `eips`, which writes text on a fixed character grid — cells of
# 12x20 px, so 50 columns by 40 rows on this panel — and all the layout can do
# is leave a hole of exactly the right size in exactly the right place.
EIPS_CELL_WIDTH = 12
EIPS_CELL_HEIGHT = 20
# Position and width of that hole, in cells. These three numbers must match
# INDOOR_TEMP_COL/ROW/CHARS in `kindle/local/env.sh`: the Kindle writes at those
# coordinates and nothing here can tell it otherwise. `tests/test_kindle.py`
# keeps the two sides in step.
INDOOR_SLOT_COL = 4
INDOOR_SLOT_ROW = 38
# Four cells for at most three characters: the Kindle right-aligns the value
# and pads it with blanks, and that leading blank is what stops `eips` from
# reading a temperature below zero as an option of its own.
INDOOR_SLOT_CHARS = 4

# On-screen copy is Italian on purpose: the panel hangs on an Italian wall.
# Only code comments and documentation are in English.
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
GIORNI_BREVI = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"]
MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]

# European EAQI scale: upper threshold -> label
_AQI_BANDS = [(20, "Buona"), (40, "Discreta"), (60, "Media"),
              (80, "Scarsa"), (100, "Scadente")]


def _aqi_label(value: float | None) -> str:
    """Italian EAQI band for an air quality index, empty string when unknown."""
    if value is None:
        return ""
    for threshold, label in _AQI_BANDS:
        if value <= threshold:
            return label
    return "Pessima"


def _round(value: float | None) -> int | None:
    """Round to the nearest integer, preserving None."""
    return None if value is None else int(round(value))


def _fmt(value: float | None, suffix: str = "") -> str:
    """Render a number for the screen; missing values become an en dash."""
    return "–" if value is None else f"{int(round(value))}{suffix}"


def _series(source: dict[str, Any], key: str) -> Sequence[Any]:
    """A data series from an Open-Meteo block, or an empty one if absent.

    Open-Meteo also sends explicit `null` for variables it cannot compute, so
    `.get(key) or []` (not `.get(key, [])`) is what keeps callers safe.
    """
    return source.get(key) or []


def _at(values: Sequence[Any], index: int) -> Any:
    """Element at `index`, or None when the series is missing or too short."""
    return values[index] if 0 <= index < len(values) else None


@dataclass
class Metric:
    """One cell of the strip below the current conditions."""

    label: str
    value: str
    unit: str = ""
    note: str = ""


@dataclass
class HourPoint:
    """One sample of the hourly chart, already placed in SVG coordinates."""

    label: str
    x: float
    temp_y: float
    temp: int | None
    precip_probability: int
    bar_y: float
    bar_height: float
    show_label: bool
    is_extreme: bool = False
    # Position of the temperature label on the coldest/warmest points.
    label_x: float = 0.0
    label_y: float = 0.0


@dataclass
class DayRow:
    """One row of the multi-day forecast grid."""

    name: str
    date_label: str
    icon: str
    temp_min: str
    temp_max: str
    bar_x: float
    bar_width: float
    precip_probability: int
    precip_label: str
    wind: str


@dataclass
class EipsSlot:
    """A rectangle the layout leaves blank for text the Kindle draws itself.

    In pixels of the final PNG, so the template can place it directly.
    """

    x: int
    y: int
    width: int
    height: int


@dataclass
class Dashboard:
    """Everything the template needs, in the order it is rendered."""

    location: str
    date_long: str
    updated_at: str
    generated_iso: str

    temperature: str
    temperature_unit: str
    apparent: str
    condition: str
    icon: str
    today_max: str
    today_min: str

    metrics: list[Metric]

    chart_width: int
    chart_height: int
    chart_temp_height: int
    chart_bars_height: int
    temp_path: str
    temp_area_path: str
    hours: list[HourPoint]
    hourly_title: str

    days: list[DayRow]
    day_bar_width: int
    wind_unit: str

    sunrise: str = ""
    sunset: str = ""
    moon_svg: str = ""
    moon_name: str = ""
    moon_illumination: str = ""
    stale: bool = False
    # None when the indoor temperature is off: the footer then has no slot for
    # it, rather than an empty one.
    indoor: EipsSlot | None = None


def _parse_local(value: str) -> datetime:
    """Open-Meteo returns naive local timestamps (`2026-08-16T22:15`)."""
    return datetime.fromisoformat(value)


def _smooth_path(points: Sequence[tuple[float, float]], tension: float = 0.22) -> str:
    """Catmull-Rom curve converted into cubic beziers."""
    if not points:
        return ""
    if len(points) < 3:
        return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in points)

    parts = [f"M {points[0][0]:.2f} {points[0][1]:.2f}"]
    for i in range(len(points) - 1):
        # Endpoints repeat themselves as their own neighbour, which keeps the
        # tangent finite at both ends of the series.
        p0 = points[max(i - 1, 0)]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[min(i + 2, len(points) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) * tension, p1[1] + (p2[1] - p0[1]) * tension)
        c2 = (p2[0] - (p3[0] - p1[0]) * tension, p2[1] - (p3[1] - p1[1]) * tension)
        parts.append(
            f"C {c1[0]:.2f} {c1[1]:.2f}, {c2[0]:.2f} {c2[1]:.2f}, {p2[0]:.2f} {p2[1]:.2f}"
        )
    return " ".join(parts)


def _build_hourly(
    forecast: dict[str, Any], now: datetime, hours_count: int
) -> tuple[list[HourPoint], str, str]:
    """Temperature curve plus rain-probability bars for the next `hours_count` hours.

    Returns the points and the two SVG paths (line and filled area).
    """
    hourly = forecast.get("hourly", {})
    times = [_parse_local(t) for t in _series(hourly, "time")]
    temps = _series(hourly, "temperature_2m")
    probs = _series(hourly, "precipitation_probability")

    # The window starts at the current hour; if the series is already in the
    # past (stale payload) we fall back to its beginning.
    start = next(
        (i for i, t in enumerate(times) if t >= now.replace(minute=0, second=0, microsecond=0)),
        0,
    )
    window = list(range(start, min(start + hours_count, len(times))))
    if not window:
        return [], "", ""

    values = [v for v in (_at(temps, i) for i in window) if v is not None]
    lo, hi = (min(values), max(values)) if values else (0.0, 1.0)
    span = max(hi - lo, 1.0)
    # Vertical margin so the curve never touches the edges of its box.
    pad = 12.0
    usable = CHART_TEMP_HEIGHT - 2 * pad

    step = CHART_WIDTH / (len(window) - 1) if len(window) > 1 else CHART_WIDTH
    coords: list[tuple[float, float]] = []
    points: list[HourPoint] = []

    for slot, index in enumerate(window):
        temp = _at(temps, index)
        prob = _at(probs, index) or 0
        x = slot * step
        # Missing samples sit on the floor of the range rather than breaking
        # the path: a gap in the curve would read as a rendering fault.
        y = pad + (hi - (temp if temp is not None else lo)) / span * usable
        bar_h = CHART_BARS_HEIGHT * (prob / 100.0)
        coords.append((x, y))
        points.append(
            HourPoint(
                label=f"{times[index].hour:02d}",
                x=x,
                temp_y=y,
                temp=_round(temp),
                precip_probability=int(prob),
                bar_y=CHART_BARS_HEIGHT - bar_h,
                bar_height=bar_h,
                # One label every 3 hours, skipping the last one when it would
                # crowd the right edge.
                show_label=slot % 3 == 0 and slot < len(window) - 1,
            )
        )

    if values:
        warmest = max(points, key=lambda p: p.temp if p.temp is not None else -999)
        coldest = min(points, key=lambda p: p.temp if p.temp is not None else 999)
        for point in (warmest, coldest):
            point.is_extreme = True
            # Label above the point, but below it when it would escape the box,
            # and inset at the edges so it never gets clipped horizontally.
            point.label_x = min(max(point.x, 15.0), CHART_WIDTH - 15.0)
            point.label_y = point.temp_y - 10 if point.temp_y > 22 else point.temp_y + 19

    path = _smooth_path(coords)
    area = f"{path} L {coords[-1][0]:.2f} {CHART_TEMP_HEIGHT} L {coords[0][0]:.2f} {CHART_TEMP_HEIGHT} Z"
    return points, path, area


def _build_days(forecast: dict[str, Any], cfg: Config) -> list[DayRow]:
    """The multi-day grid: icon, min/max on a shared scale, rain and wind."""
    daily = forecast.get("daily", {})
    dates = _series(daily, "time")
    if len(dates) < 2:
        return []

    mins = _series(daily, "temperature_2m_min")
    maxs = _series(daily, "temperature_2m_max")
    codes = _series(daily, "weather_code")
    probs = _series(daily, "precipitation_probability_max")
    winds = _series(daily, "wind_speed_10m_max")

    # Index 0 is today, already covered by the current-conditions block.
    upcoming = list(range(1, min(1 + cfg.display.forecast_days, len(dates))))
    # One scale shared by every row: the shape of the week can be read from the
    # position of the bars alone, without reading the numbers.
    valid = [
        v
        for i in upcoming
        for v in (_at(mins, i), _at(maxs, i))
        if v is not None
    ]
    scale_lo, scale_hi = (min(valid), max(valid)) if valid else (0.0, 1.0)
    scale_span = max(scale_hi - scale_lo, 1.0)

    rows: list[DayRow] = []
    for i in upcoming:
        date = datetime.fromisoformat(dates[i]).date()
        tmin = _at(mins, i)
        tmax = _at(maxs, i)
        prob = _at(probs, i) or 0
        wind = _at(winds, i)

        left = (tmin - scale_lo) / scale_span if tmin is not None else 0.0
        right = (tmax - scale_lo) / scale_span if tmax is not None else 1.0
        # Leave room for the minimum bar even when the day sits at the very top
        # of the scale, otherwise the row would render as an empty track.
        bar_x = min(max(left * DAY_BAR_WIDTH, 0.0), DAY_BAR_WIDTH - MIN_DAY_BAR_WIDTH)
        bar_w = max((right - left) * DAY_BAR_WIDTH, MIN_DAY_BAR_WIDTH)
        bar_w = min(bar_w, DAY_BAR_WIDTH - bar_x)

        rows.append(
            DayRow(
                name=GIORNI_BREVI[date.weekday()],
                date_label=f"{date.day}",
                icon=wmo.icon_for(_at(codes, i), is_day=True),
                temp_min=_fmt(tmin, "°"),
                temp_max=_fmt(tmax, "°"),
                bar_x=bar_x,
                bar_width=bar_w,
                precip_probability=int(prob),
                precip_label=f"{int(prob)}%" if prob else "–",
                wind=_fmt(wind),
            )
        )
    return rows


def _build_metrics(
    forecast: dict[str, Any], air_quality: dict[str, Any] | None, cfg: Config
) -> list[Metric]:
    """The strip of secondary numbers between the current block and the chart."""
    current = forecast.get("current", {})
    daily = forecast.get("daily", {})

    def today(key: str) -> Any:
        return _at(_series(daily, key), 0)

    metrics = [
        Metric("Umidità", _fmt(current.get("relative_humidity_2m")), "%"),
        Metric(
            "Vento",
            _fmt(current.get("wind_speed_10m")),
            cfg.units.wind_symbol,
            astro.compass_point(current.get("wind_direction_10m")),
        ),
        Metric("UV max", _fmt(today("uv_index_max"))),
        Metric("Pioggia", _fmt(today("precipitation_probability_max")), "%"),
    ]

    if cfg.features.air_quality:
        aqi = (air_quality or {}).get("current", {}).get("european_aqi")
        metrics.append(Metric("Aria", _fmt(aqi), "", _aqi_label(aqi)))
    return metrics


def _indoor_slot() -> EipsSlot:
    """The blank the Kindle writes the indoor temperature into, in pixels."""
    return EipsSlot(
        x=INDOOR_SLOT_COL * EIPS_CELL_WIDTH,
        y=INDOOR_SLOT_ROW * EIPS_CELL_HEIGHT,
        width=INDOOR_SLOT_CHARS * EIPS_CELL_WIDTH,
        height=EIPS_CELL_HEIGHT,
    )


def build_dashboard(
    forecast: dict[str, Any],
    air_quality: dict[str, Any] | None,
    cfg: Config,
    now: datetime | None = None,
) -> Dashboard:
    """Turn the raw API payloads into the print-ready model.

    `now` is the local time of the location; pass it explicitly to get a
    reproducible render out of a fixture.
    """
    current = forecast.get("current", {})
    daily = forecast.get("daily", {})

    offset = timedelta(seconds=forecast.get("utc_offset_seconds", 0))
    local_now = now or (datetime.now(timezone.utc) + offset).replace(tzinfo=None)

    code = current.get("weather_code")
    is_day = bool(current.get("is_day", 1))

    # Open-Meteo refreshes the observation every 15 minutes: when the one we
    # get is much older, the image is truthful but not current and it has to be
    # said on screen, otherwise stale data would pass for fresh.
    stale = False
    if current.get("time"):
        stale = (local_now - _parse_local(current["time"])) > STALE_AFTER

    hours, temp_path, temp_area = _build_hourly(forecast, local_now, cfg.display.hourly_hours)

    sunrise = sunset = ""
    if cfg.features.sun_times and _series(daily, "sunrise"):
        sunrise = _parse_local(daily["sunrise"][0]).strftime("%H:%M")
        sunset = _parse_local(daily["sunset"][0]).strftime("%H:%M")

    moon_markup: str | Markup = ""
    moon_name = moon_illum = ""
    if cfg.features.moon_phase:
        # The phase depends on the instant, not on the timezone: compute it in UTC.
        phase = astro.moon_phase(datetime.now(timezone.utc))
        moon_markup = Markup(astro.moon_svg(phase))
        moon_name = phase.name
        moon_illum = f"{round(phase.illumination * 100)}%"

    return Dashboard(
        location=cfg.location.name,
        date_long=f"{GIORNI[local_now.weekday()]} {local_now.day} {MESI[local_now.month - 1]}",
        updated_at=local_now.strftime("%H:%M"),
        generated_iso=local_now.isoformat(timespec="minutes"),
        temperature=_fmt(current.get("temperature_2m")),
        temperature_unit="°",
        apparent=_fmt(current.get("apparent_temperature"), "°"),
        condition=wmo.describe(code),
        icon=wmo.icon_for(code, is_day),
        today_max=_fmt(_at(_series(daily, "temperature_2m_max"), 0), "°"),
        today_min=_fmt(_at(_series(daily, "temperature_2m_min"), 0), "°"),
        metrics=_build_metrics(forecast, air_quality, cfg),
        chart_width=CHART_WIDTH,
        chart_height=CHART_HEIGHT,
        chart_temp_height=CHART_TEMP_HEIGHT,
        chart_bars_height=CHART_BARS_HEIGHT,
        temp_path=temp_path,
        temp_area_path=temp_area,
        hours=hours,
        # Announce the hours we actually drew, not the ones we asked for: a
        # short payload would otherwise make the title lie.
        hourly_title=f"Prossime {len(hours)} ore",
        days=_build_days(forecast, cfg),
        day_bar_width=DAY_BAR_WIDTH,
        wind_unit=cfg.units.wind_symbol,
        sunrise=sunrise,
        sunset=sunset,
        moon_svg=moon_markup,
        moon_name=moon_name,
        moon_illumination=moon_illum,
        stale=stale,
        indoor=_indoor_slot() if cfg.features.indoor_temperature else None,
    )
