"""WMO code table: every code must resolve to text and to an icon on disk."""

from k4weather import wmo


def test_variable_codes_have_a_day_and_a_night_icon():
    assert wmo.icon_for(0, is_day=True) == "clear-day"
    assert wmo.icon_for(0, is_day=False) == "clear-night"
    assert wmo.icon_for(2, is_day=False) == "partly-cloudy-night"


def test_codes_without_a_variant_ignore_the_time_of_day():
    assert wmo.icon_for(95, is_day=True) == wmo.icon_for(95, is_day=False) == "thunderstorm"


def test_unknown_code_does_not_blow_up():
    assert wmo.icon_for(1234) == "unknown"
    assert wmo.icon_for(None) == "unknown"
    assert wmo.describe(None) == "Non disponibile"


def test_every_code_has_an_icon_file():
    from k4weather.render import ICONS

    for code in wmo.WMO_CODES:
        for is_day in (True, False):
            name = wmo.icon_for(code, is_day)
            assert (ICONS / f"{name}.svg").exists(), f"missing icon: {name}"


def test_descriptions_fit_on_one_line():
    # The condition in the main block must not wrap: at 20px semibold roughly
    # 30 characters fit in the available column.
    for code in wmo.WMO_CODES:
        assert len(wmo.describe(code)) <= 30, code
