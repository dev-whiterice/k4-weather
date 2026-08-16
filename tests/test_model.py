import copy
from datetime import datetime, timedelta

from k4weather.model import CHART_WIDTH, DAY_BAR_WIDTH, STALE_AFTER, build_dashboard


def _at_fixture_time(forecast):
    return datetime.fromisoformat(forecast["current"]["time"])


def test_dashboard_completa(forecast, air_quality, cfg):
    d = build_dashboard(forecast, air_quality, cfg, now=_at_fixture_time(forecast))

    assert d.location == "Caoria"
    assert d.date_long == "domenica 16 agosto"
    assert d.temperature == "19"  # 18.8 nella fixture, arrotondato
    assert d.condition == "Temporale"
    assert d.icon == "thunderstorm"
    assert len(d.days) == cfg.display.forecast_days
    assert len(d.hours) == cfg.display.hourly_hours
    assert d.sunrise and d.sunset
    assert d.moon_name


def test_griglia_giorni_parte_da_domani(forecast, cfg):
    d = build_dashboard(forecast, None, cfg, now=_at_fixture_time(forecast))
    # Il 16 agosto 2026 e' domenica: la prima riga della griglia e' lunedi.
    assert d.days[0].name == "LUN"


def test_barre_giorni_restano_nella_traccia(forecast, cfg):
    d = build_dashboard(forecast, None, cfg, now=_at_fixture_time(forecast))
    for day in d.days:
        assert day.bar_x >= 0
        assert day.bar_width > 0
        assert day.bar_x + day.bar_width <= DAY_BAR_WIDTH + 0.01


def test_grafico_orario_dentro_al_riquadro(forecast, cfg):
    d = build_dashboard(forecast, None, cfg, now=_at_fixture_time(forecast))
    for hour in d.hours:
        assert 0 <= hour.x <= CHART_WIDTH
        assert 0 <= hour.temp_y <= d.chart_temp_height
        assert 0 <= hour.bar_height <= d.chart_bars_height
    assert d.temp_path.startswith("M ")
    assert d.temp_area_path.endswith("Z")


def test_etichette_estremi_non_escono_dal_grafico(forecast, cfg):
    d = build_dashboard(forecast, None, cfg, now=_at_fixture_time(forecast))
    extremes = [h for h in d.hours if h.is_extreme]
    assert len(extremes) == 2
    for hour in extremes:
        assert 15 <= hour.label_x <= CHART_WIDTH - 15
        assert 0 < hour.label_y < d.chart_temp_height


def test_ora_corrente_e_il_primo_punto(forecast, cfg):
    now = _at_fixture_time(forecast)
    d = build_dashboard(forecast, None, cfg, now=now)
    assert d.hours[0].label == f"{now.hour:02d}"


def test_valori_mancanti_diventano_trattini(forecast, cfg):
    broken = copy.deepcopy(forecast)
    broken["current"]["temperature_2m"] = None
    broken["current"]["relative_humidity_2m"] = None
    broken["daily"]["uv_index_max"] = [None] * len(broken["daily"]["time"])

    d = build_dashboard(broken, None, cfg, now=_at_fixture_time(forecast))
    assert d.temperature == "–"
    assert d.metrics[0].value == "–"
    assert d.metrics[2].value == "–"


def test_aria_assente_non_rompe_la_striscia(forecast, cfg):
    d = build_dashboard(forecast, None, cfg, now=_at_fixture_time(forecast))
    aria = [m for m in d.metrics if m.label == "Aria"]
    assert len(aria) == 1 and aria[0].value == "–"


def test_osservazione_recente_non_e_segnalata(forecast, cfg):
    d = build_dashboard(forecast, None, cfg, now=_at_fixture_time(forecast))
    assert d.stale is False


def test_osservazione_vecchia_viene_segnalata(forecast, cfg):
    later = _at_fixture_time(forecast) + STALE_AFTER + timedelta(minutes=1)
    d = build_dashboard(forecast, None, cfg, now=later)
    assert d.stale is True


def test_giornata_isoterma_ha_barra_visibile(forecast, cfg):
    flat = copy.deepcopy(forecast)
    flat["daily"]["temperature_2m_min"][1] = 20.0
    flat["daily"]["temperature_2m_max"][1] = 20.0
    d = build_dashboard(flat, None, cfg, now=_at_fixture_time(forecast))
    assert d.days[0].bar_width >= 10
