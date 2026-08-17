"""Mapping of the WMO weather codes used by Open-Meteo.

Every code yields an Italian description (the dashboard is read in Italian) and
an icon name. "Variable" icons have a day and a night version: `icon_for` only
appends the -day/-night suffix for the names listed in DAY_NIGHT_ICONS.
"""

# WMO code -> (long description, short description, icon).
# The short description is kept alongside the long one for the day the grid
# gets tighter; only the long one is rendered today.
WMO_CODES: dict[int, tuple[str, str, str]] = {
    0: ("Sereno", "Sereno", "clear"),
    1: ("Prevalentemente sereno", "Poco nuv.", "mostly-clear"),
    2: ("Parzialmente nuvoloso", "Parz. nuv.", "partly-cloudy"),
    3: ("Coperto", "Coperto", "overcast"),
    45: ("Nebbia", "Nebbia", "fog"),
    48: ("Nebbia con brina", "Nebbia", "fog"),
    51: ("Pioviggine debole", "Pioviggine", "drizzle"),
    53: ("Pioviggine", "Pioviggine", "drizzle"),
    55: ("Pioviggine intensa", "Pioviggine", "drizzle"),
    56: ("Pioviggine gelata", "Gelicidio", "sleet"),
    57: ("Pioviggine gelata intensa", "Gelicidio", "sleet"),
    61: ("Pioggia debole", "Pioggia", "rain"),
    63: ("Pioggia", "Pioggia", "rain"),
    65: ("Pioggia forte", "Pioggia", "heavy-rain"),
    66: ("Pioggia gelata", "Gelicidio", "sleet"),
    67: ("Pioggia gelata forte", "Gelicidio", "sleet"),
    71: ("Neve debole", "Neve", "snow"),
    73: ("Neve", "Neve", "snow"),
    75: ("Neve abbondante", "Neve", "snow"),
    77: ("Granuli di neve", "Neve", "snow"),
    80: ("Rovesci deboli", "Rovesci", "rain"),
    81: ("Rovesci", "Rovesci", "rain"),
    82: ("Rovesci violenti", "Rovesci", "heavy-rain"),
    85: ("Rovesci di neve", "Neve", "snow"),
    86: ("Rovesci di neve intensi", "Neve", "snow"),
    95: ("Temporale", "Temporale", "thunderstorm"),
    96: ("Temporale con grandine", "Temporale", "thunderstorm-hail"),
    99: ("Temporale con grandine forte", "Temporale", "thunderstorm-hail"),
}

# Icons that exist in a -day and a -night variant.
DAY_NIGHT_ICONS = {"clear", "mostly-clear", "partly-cloudy"}

# Used for codes the API may add in the future, and for a missing code.
_UNKNOWN = ("Non disponibile", "N.D.", "unknown")


def describe(code: int | None) -> str:
    """Long Italian description for a WMO code."""
    return WMO_CODES.get(code, _UNKNOWN)[0] if code is not None else _UNKNOWN[0]


def icon_for(code: int | None, is_day: bool = True) -> str:
    """Icon file name (without extension) for a WMO code."""
    base = WMO_CODES.get(code, _UNKNOWN)[2] if code is not None else _UNKNOWN[2]
    if base in DAY_NIGHT_ICONS:
        return f"{base}-{'day' if is_day else 'night'}"
    return base
