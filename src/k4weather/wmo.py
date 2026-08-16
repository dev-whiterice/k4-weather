"""Mappatura dei codici meteo WMO usati da Open-Meteo.

Ogni codice produce una descrizione in italiano e un nome di icona. Le icone
"variabili" hanno una versione diurna e una notturna: `icon_for` aggiunge il
suffisso -day/-night solo per quelle presenti in DAY_NIGHT_ICONS.
"""

# codice WMO -> (descrizione lunga, descrizione breve, icona)
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

DAY_NIGHT_ICONS = {"clear", "mostly-clear", "partly-cloudy"}

_UNKNOWN = ("Non disponibile", "N.D.", "unknown")


def describe(code: int | None) -> str:
    return WMO_CODES.get(code, _UNKNOWN)[0] if code is not None else _UNKNOWN[0]


def icon_for(code: int | None, is_day: bool = True) -> str:
    """Nome del file icona (senza estensione) per un codice WMO."""
    base = WMO_CODES.get(code, _UNKNOWN)[2] if code is not None else _UNKNOWN[2]
    if base in DAY_NIGHT_ICONS:
        return f"{base}-{'day' if is_day else 'night'}"
    return base
