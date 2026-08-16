"""Calcoli astronomici leggeri: fase lunare e rosa dei venti.

Open-Meteo non espone la fase lunare, quindi la ricaviamo dal ciclo sinodico.
L'approssimazione ha un errore di poche ore, piu che sufficiente per mostrare
il nome della fase e un disco illuminato correttamente.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

SYNODIC_MONTH = 29.530588853
# Novilunio di riferimento: 6 gennaio 2000, 18:14 UTC
_REFERENCE_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)

_PHASE_NAMES = [
    "Luna nuova",
    "Luna crescente",
    "Primo quarto",
    "Gibbosa crescente",
    "Luna piena",
    "Gibbosa calante",
    "Ultimo quarto",
    "Luna calante",
]

_COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO",
]


@dataclass(frozen=True)
class MoonPhase:
    fraction: float      # posizione nel ciclo, 0 = novilunio, 0.5 = plenilunio
    illumination: float  # frazione di disco illuminato, 0..1
    name: str
    waxing: bool         # True se crescente


def moon_phase(moment: datetime) -> MoonPhase:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    days = (moment - _REFERENCE_NEW_MOON).total_seconds() / 86400.0
    fraction = (days % SYNODIC_MONTH) / SYNODIC_MONTH
    illumination = (1 - math.cos(2 * math.pi * fraction)) / 2
    # Otto settori centrati sulle fasi principali
    index = int((fraction * 8) + 0.5) % 8
    return MoonPhase(
        fraction=fraction,
        illumination=illumination,
        name=_PHASE_NAMES[index],
        waxing=fraction < 0.5,
    )


def moon_svg(phase: MoonPhase, size: int = 22) -> str:
    """Disco lunare come SVG: parte illuminata piena, resto a contorno.

    Il terminatore e' un'ellisse la cui semiampiezza orizzontale varia con
    cos(2*pi*fraction); il segno decide se la fase e' crescente o calante.
    """
    r = size / 2
    cx = cy = r
    inner = r - 1  # lascia spazio al contorno
    k = math.cos(2 * math.pi * phase.fraction)
    rx = abs(k) * inner

    # Semidisco sempre illuminato: destro se crescente, sinistro se calante.
    lit_sweep = 1 if phase.waxing else 0
    # Il terminatore curva verso l'esterno quando la fase supera il quarto.
    term_sweep = 1 if (k < 0) == phase.waxing else 0

    lit = (
        f"M {cx} {cy - inner} "
        f"A {inner} {inner} 0 0 {lit_sweep} {cx} {cy + inner} "
        f"A {rx:.3f} {inner} 0 0 {term_sweep} {cx} {cy - inner} Z"
    )
    return (
        f'<svg class="moon" viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
        f'<circle cx="{cx}" cy="{cy}" r="{inner}" fill="none" '
        f'stroke="currentColor" stroke-width="1.5" opacity="0.45"/>'
        f'<path d="{lit}" fill="currentColor"/>'
        f"</svg>"
    )


def compass_point(degrees: float | None) -> str:
    """Direzione del vento in sedicesimi, notazione italiana (O = ovest)."""
    if degrees is None:
        return ""
    return _COMPASS[int((degrees % 360) / 22.5 + 0.5) % 16]
