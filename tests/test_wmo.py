from k4weather import wmo


def test_variabili_hanno_versione_diurna_e_notturna():
    assert wmo.icon_for(0, is_day=True) == "clear-day"
    assert wmo.icon_for(0, is_day=False) == "clear-night"
    assert wmo.icon_for(2, is_day=False) == "partly-cloudy-night"


def test_codici_senza_variante_ignorano_il_giorno():
    assert wmo.icon_for(95, is_day=True) == wmo.icon_for(95, is_day=False) == "thunderstorm"


def test_codice_sconosciuto_non_esplode():
    assert wmo.icon_for(1234) == "unknown"
    assert wmo.icon_for(None) == "unknown"
    assert wmo.describe(None) == "Non disponibile"


def test_ogni_codice_ha_un_file_icona():
    from k4weather.render import ICONS

    for code in wmo.WMO_CODES:
        for is_day in (True, False):
            name = wmo.icon_for(code, is_day)
            assert (ICONS / f"{name}.svg").exists(), f"icona mancante: {name}"


def test_descrizioni_stanno_su_una_riga():
    # La condizione del blocco principale non deve andare a capo: a 20px
    # semibold entrano circa 30 caratteri nella colonna disponibile.
    for code in wmo.WMO_CODES:
        assert len(wmo.describe(code)) <= 30, code
