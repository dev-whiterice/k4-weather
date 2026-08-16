"""Normalizzazione delle risposte Open-Meteo nel modello che alimenta il template.

Tutta la logica (arrotondamenti, formattazione, geometria dei grafici) vive qui:
il template resta dichiarativo e si limita a posizionare valori gia' pronti.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from markupsafe import Markup

from . import astro, wmo
from .config import Config

# Geometria del grafico orario, in unita' SVG (coincidono con i px del PNG).
CHART_WIDTH = 556
CHART_TEMP_HEIGHT = 74
CHART_BARS_HEIGHT = 24
CHART_GAP = 6
CHART_HEIGHT = CHART_TEMP_HEIGHT + CHART_GAP + CHART_BARS_HEIGHT

# Larghezza della barra min/max nella griglia dei giorni.
DAY_BAR_WIDTH = 304

# Oltre questo scarto tra osservazione e generazione, la dashboard si dichiara
# non aggiornata.
STALE_AFTER = timedelta(minutes=90)

GIORNI = ["lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica"]
GIORNI_BREVI = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"]
MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]

# Scala EAQI europea: soglia superiore -> etichetta
_AQI_BANDS = [(20, "Buona"), (40, "Discreta"), (60, "Media"),
              (80, "Scarsa"), (100, "Scadente")]


def _aqi_label(value: float | None) -> str:
    if value is None:
        return ""
    for threshold, label in _AQI_BANDS:
        if value <= threshold:
            return label
    return "Pessima"


def _round(value: float | None) -> int | None:
    return None if value is None else int(round(value))


def _fmt(value: float | None, suffix: str = "") -> str:
    return "–" if value is None else f"{int(round(value))}{suffix}"


@dataclass
class Metric:
    label: str
    value: str
    unit: str = ""
    note: str = ""


@dataclass
class HourPoint:
    label: str
    x: float
    temp_y: float
    temp: int | None
    precip_probability: int
    bar_y: float
    bar_height: float
    show_label: bool
    is_extreme: bool = False
    # Posizione dell'etichetta di temperatura sui punti di minimo e massimo
    label_x: float = 0.0
    label_y: float = 0.0


@dataclass
class DayRow:
    name: str
    date_label: str
    icon: str
    temp_min: str
    temp_max: str
    bar_x: float
    bar_width: float
    precip_probability: int
    precip_label: str


@dataclass
class Dashboard:
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

    sunrise: str = ""
    sunset: str = ""
    moon_svg: str = ""
    moon_name: str = ""
    moon_illumination: str = ""
    stale: bool = False


def _parse_local(value: str) -> datetime:
    """Open-Meteo restituisce orari locali naive (`2026-08-16T22:15`)."""
    return datetime.fromisoformat(value)


def _smooth_path(points: Sequence[tuple[float, float]], tension: float = 0.22) -> str:
    """Curva Catmull-Rom convertita in bezier cubiche."""
    if not points:
        return ""
    if len(points) < 3:
        return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in points)

    parts = [f"M {points[0][0]:.2f} {points[0][1]:.2f}"]
    for i in range(len(points) - 1):
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
    hourly = forecast.get("hourly", {})
    times = [_parse_local(t) for t in hourly.get("time", [])]
    temps = hourly.get("temperature_2m", [])
    probs = hourly.get("precipitation_probability", [])

    start = next(
        (i for i, t in enumerate(times) if t >= now.replace(minute=0, second=0, microsecond=0)),
        0,
    )
    window = list(range(start, min(start + hours_count, len(times))))
    if not window:
        return [], "", ""

    values = [temps[i] for i in window if temps[i] is not None]
    lo, hi = (min(values), max(values)) if values else (0.0, 1.0)
    span = max(hi - lo, 1.0)
    # Margine verticale per non far toccare la curva ai bordi del riquadro.
    pad = 12.0
    usable = CHART_TEMP_HEIGHT - 2 * pad

    step = CHART_WIDTH / (len(window) - 1) if len(window) > 1 else CHART_WIDTH
    coords: list[tuple[float, float]] = []
    points: list[HourPoint] = []

    for slot, index in enumerate(window):
        temp = temps[index] if index < len(temps) else None
        prob = probs[index] if index < len(probs) and probs[index] is not None else 0
        x = slot * step
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
                # Un'etichetta ogni 3 ore, evitando l'ultima se troppo a ridosso.
                show_label=slot % 3 == 0 and slot < len(window) - 1,
            )
        )

    if values:
        warmest = max(points, key=lambda p: p.temp if p.temp is not None else -999)
        coldest = min(points, key=lambda p: p.temp if p.temp is not None else 999)
        for point in (warmest, coldest):
            point.is_extreme = True
            # Etichetta sopra al punto, ma sotto se rischia di uscire dal riquadro,
            # e rientrata ai bordi per non farsi tagliare in orizzontale.
            point.label_x = min(max(point.x, 15.0), CHART_WIDTH - 15.0)
            point.label_y = point.temp_y - 10 if point.temp_y > 22 else point.temp_y + 19

    path = _smooth_path(coords)
    area = f"{path} L {coords[-1][0]:.2f} {CHART_TEMP_HEIGHT} L {coords[0][0]:.2f} {CHART_TEMP_HEIGHT} Z"
    return points, path, area


def _build_days(forecast: dict[str, Any], cfg: Config) -> list[DayRow]:
    daily = forecast.get("daily", {})
    dates = daily.get("time", [])
    if len(dates) < 2:
        return []

    # Indice 0 e' oggi, gia' rappresentato dal blocco principale.
    upcoming = list(range(1, min(1 + cfg.display.forecast_days, len(dates))))
    mins = [daily["temperature_2m_min"][i] for i in upcoming]
    maxs = [daily["temperature_2m_max"][i] for i in upcoming]
    valid = [v for v in mins + maxs if v is not None]
    scale_lo, scale_hi = (min(valid), max(valid)) if valid else (0.0, 1.0)
    scale_span = max(scale_hi - scale_lo, 1.0)

    rows: list[DayRow] = []
    for i in upcoming:
        date = datetime.fromisoformat(dates[i]).date()
        tmin = daily["temperature_2m_min"][i]
        tmax = daily["temperature_2m_max"][i]
        prob = daily.get("precipitation_probability_max", [])[i] or 0
        code = daily["weather_code"][i]

        left = (tmin - scale_lo) / scale_span if tmin is not None else 0.0
        right = (tmax - scale_lo) / scale_span if tmax is not None else 1.0
        bar_x = left * DAY_BAR_WIDTH
        # Larghezza minima perche' le giornate isoterme restino visibili.
        bar_w = max((right - left) * DAY_BAR_WIDTH, 10.0)
        bar_w = min(bar_w, DAY_BAR_WIDTH - bar_x)

        rows.append(
            DayRow(
                name=GIORNI_BREVI[date.weekday()],
                date_label=f"{date.day}",
                icon=wmo.icon_for(code, is_day=True),
                temp_min=_fmt(tmin, "°"),
                temp_max=_fmt(tmax, "°"),
                bar_x=bar_x,
                bar_width=bar_w,
                precip_probability=int(prob),
                precip_label=f"{int(prob)}%" if prob else "–",
            )
        )
    return rows


def _build_metrics(
    forecast: dict[str, Any], air_quality: dict[str, Any] | None, cfg: Config
) -> list[Metric]:
    current = forecast.get("current", {})
    daily = forecast.get("daily", {})

    def today(key: str) -> Any:
        values = daily.get(key) or []
        return values[0] if values else None

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


def build_dashboard(
    forecast: dict[str, Any],
    air_quality: dict[str, Any] | None,
    cfg: Config,
    now: datetime | None = None,
) -> Dashboard:
    current = forecast.get("current", {})
    daily = forecast.get("daily", {})

    offset = timedelta(seconds=forecast.get("utc_offset_seconds", 0))
    local_now = now or (datetime.now(timezone.utc) + offset).replace(tzinfo=None)

    code = current.get("weather_code")
    is_day = bool(current.get("is_day", 1))

    # Open-Meteo aggiorna l'osservazione ogni 15 minuti: se quella che riceviamo
    # e' molto piu vecchia, l'immagine e' vera ma non attuale e va detto a
    # schermo, altrimenti un dato fermo passerebbe per fresco.
    stale = False
    if current.get("time"):
        stale = (local_now - _parse_local(current["time"])) > STALE_AFTER

    hours, temp_path, temp_area = _build_hourly(forecast, local_now, cfg.display.hourly_hours)

    sunrise = sunset = ""
    if cfg.features.sun_times and daily.get("sunrise"):
        sunrise = _parse_local(daily["sunrise"][0]).strftime("%H:%M")
        sunset = _parse_local(daily["sunset"][0]).strftime("%H:%M")

    moon_markup: str | Markup = ""
    moon_name = moon_illum = ""
    if cfg.features.moon_phase:
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
        today_max=_fmt((daily.get("temperature_2m_max") or [None])[0], "°"),
        today_min=_fmt((daily.get("temperature_2m_min") or [None])[0], "°"),
        metrics=_build_metrics(forecast, air_quality, cfg),
        chart_width=CHART_WIDTH,
        chart_height=CHART_HEIGHT,
        chart_temp_height=CHART_TEMP_HEIGHT,
        chart_bars_height=CHART_BARS_HEIGHT,
        temp_path=temp_path,
        temp_area_path=temp_area,
        hours=hours,
        hourly_title=f"Prossime {cfg.display.hourly_hours} ore",
        days=_build_days(forecast, cfg),
        day_bar_width=DAY_BAR_WIDTH,
        sunrise=sunrise,
        sunset=sunset,
        moon_svg=moon_markup,
        moon_name=moon_name,
        moon_illumination=moon_illum,
        stale=stale,
    )
