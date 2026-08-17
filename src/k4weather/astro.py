"""Lightweight astronomy: moon phase and compass rose.

Open-Meteo does not expose the moon phase, so we derive it from the synodic
cycle. The approximation is off by a few hours, which is plenty to show the
name of the phase and a correctly lit disc.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

# Mean length of a lunation, in days.
SYNODIC_MONTH = 29.530588853
# Reference new moon: 6 January 2000, 18:14 UTC
_REFERENCE_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)

# Italian phase names, in cycle order starting from the new moon.
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

# Sixteenths of the compass in Italian notation: O (ovest) where English uses W.
_COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO",
]


@dataclass(frozen=True)
class MoonPhase:
    fraction: float      # position in the cycle, 0 = new moon, 0.5 = full moon
    illumination: float  # lit fraction of the disc, 0..1
    name: str
    waxing: bool         # True while the lit side is growing


def moon_phase(moment: datetime) -> MoonPhase:
    """Moon phase at `moment`; naive datetimes are read as UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    days = (moment - _REFERENCE_NEW_MOON).total_seconds() / 86400.0
    fraction = (days % SYNODIC_MONTH) / SYNODIC_MONTH
    illumination = (1 - math.cos(2 * math.pi * fraction)) / 2
    # Eight sectors centred on the principal phases, hence the +0.5 rounding.
    index = int((fraction * 8) + 0.5) % 8
    return MoonPhase(
        fraction=fraction,
        illumination=illumination,
        name=_PHASE_NAMES[index],
        waxing=fraction < 0.5,
    )


def moon_svg(phase: MoonPhase, size: int = 22) -> str:
    """The moon as an SVG disc: lit part filled, the rest left as an outline.

    The terminator is an ellipse whose horizontal semi-axis follows
    cos(2*pi*fraction); the sign of that cosine decides which way it bulges.
    """
    r = size / 2
    cx = cy = r
    inner = r - 1  # leaves room for the outline stroke
    k = math.cos(2 * math.pi * phase.fraction)
    rx = abs(k) * inner

    # The always-lit half: right while waxing, left while waning.
    lit_sweep = 1 if phase.waxing else 0
    # The terminator bulges outwards once the phase is past the quarter.
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
    """Wind direction in sixteenths, Italian notation; empty string if unknown."""
    if degrees is None:
        return ""
    return _COMPASS[int((degrees % 360) / 22.5 + 0.5) % 16]
