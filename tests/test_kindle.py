"""The client that runs on the Kindle.

Two things are worth testing off the device. The first is the coupling: the
indoor temperature is drawn by the Kindle at coordinates the layout has to
leave blank, and the two sides declare them separately — `model.py` for the
image, `env.sh` for the device. The second is the arithmetic that turns a battery
gas gauge reading into a number for the wall, which is fiddly precisely because
POSIX sh has no floating point.

Nothing in those scripts is Kindle-specific except the sensor command and the
two programs that draw — `eips` and `fbink` — and all of them are overridable
from the environment: that is what makes them runnable here.
"""

import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from k4weather import model

KINDLE = Path(__file__).resolve().parents[1] / "kindle" / "local"
INDOOR_TEMP = str(KINDLE / "indoor-temp.sh")
DRAW = str(KINDLE / "draw.sh")

EXTENSION = KINDLE.parent / "extensions" / "k4weather"


def _env_default(name: str) -> str:
    """The default of one `export NAME=${NAME:-value}` line of `env.sh`."""
    text = (KINDLE / "env.sh").read_text(encoding="utf-8")
    match = re.search(rf"^export {name}=\$\{{{name}:-(.*)\}}$", text, re.MULTILINE)
    assert match, f"{name} is not defined in env.sh"
    return match.group(1).strip('"')


def _run(script: str, *args: str, **env: str) -> subprocess.CompletedProcess:
    """Run one of the device scripts with a fake sensor behind it."""
    return subprocess.run(
        ["sh", script, *args],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", **env},
    )


def _temperature(*args: str, **env: str) -> subprocess.CompletedProcess:
    return _run(INDOOR_TEMP, *args, **env)


# ------------------------------------------------------------------ coupling


@pytest.mark.parametrize(
    "variable,constant",
    [
        ("INDOOR_TEMP_X", model.INDOOR_SLOT_X),
        ("INDOOR_TEMP_Y", model.INDOOR_SLOT_Y),
        ("INDOOR_TEMP_SCALE", model.INDOOR_SCALE),
        ("INDOOR_TEMP_CHARS", model.INDOOR_SLOT_CHARS),
    ],
)
def test_the_kindle_writes_where_the_layout_leaves_a_hole(variable, constant):
    # The Kindle draws at these coordinates whatever the dashboard looks like:
    # if the two drift apart, the value lands on top of something else and
    # nothing in either program can notice.
    assert int(_env_default(variable)) == constant


# ------------------------------------------------------- reading the sensor


@pytest.mark.parametrize(
    "reading,unit,expected",
    [
        ("73 Fahrenheit", "F", "23"),  # what gasgauge-info -k actually prints
        ("INFO:battery temperature: 73 Fahrenheit", "F", "23"),
        ("32 Fahrenheit", "F", "0"),
        ("14 Fahrenheit", "F", "-10"),
        ("235", "dC", "24"),  # a sysfs file in tenths
        ("21500", "mC", "22"),  # and one in thousandths
        ("-4", "C", "-4"),
        ("08", "C", "8"),  # a leading zero is not octal here
    ],
)
def test_the_reading_is_converted_to_whole_degrees(reading, unit, expected):
    done = _temperature(INDOOR_TEMP_CMD=f"echo {reading}", INDOOR_TEMP_UNIT=unit)
    assert done.returncode == 0
    assert done.stdout.strip() == expected


@pytest.mark.parametrize("offset,expected", [("0", "23"), ("-2.5", "20"), ("1.5", "24")])
def test_the_offset_is_applied_before_rounding(offset, expected):
    done = _temperature(INDOOR_TEMP_CMD="echo 73 Fahrenheit", INDOOR_TEMP_OFFSET=offset)
    assert done.returncode == 0
    assert done.stdout.strip() == expected


def test_the_uncalibrated_reading_is_printed_for_the_calibration():
    # This is the number the offset is measured against, so it keeps the
    # decimal the sensor is worth.
    done = _temperature("--raw", INDOOR_TEMP_CMD="echo 73 Fahrenheit")
    assert done.stdout.strip() == "22.8"


@pytest.mark.parametrize(
    "env",
    [
        {"INDOOR_TEMP_CMD": "echo 200 Fahrenheit"},  # sensor gone mad
        {"INDOOR_TEMP_CMD": "echo n/a"},  # no number in the answer
        {"INDOOR_TEMP_CMD": "true"},  # no answer at all
        {"INDOOR_TEMP_CMD": "command-that-is-not-there"},  # not this device
    ],
)
def test_an_unusable_reading_prints_nothing(env):
    # The caller then leaves the dash the image already carries: on a wall, no
    # number beats a wrong one.
    done = _temperature(**env)
    assert done.returncode == 1
    assert done.stdout == ""


# ------------------------------------------------------- drawing the reading


def _recorder(tmp_path, name: str):
    """A stand-in for one of the two drawing programs, that records the calls."""
    log = tmp_path / f"{name}-calls"
    fake = tmp_path / name
    fake.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\n', encoding="utf-8")
    fake.chmod(0o755)

    def calls() -> list[str]:
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    calls.path = str(fake)  # type: ignore[attr-defined]
    return calls


@pytest.fixture
def eips(tmp_path):
    """A stand-in for /usr/sbin/eips."""
    return _recorder(tmp_path, "eips")


@pytest.fixture
def fbink(tmp_path):
    """A stand-in for the fbink binary, which is not in this repository."""
    return _recorder(tmp_path, "fbink")


def _draw(eips, image="/tmp/dash.png", fbink=None, **env) -> None:
    # Never left to the default: on a device — or on a machine where the binary
    # has been dropped into kindle/ ready to be installed — draw.sh would find
    # the real fbink and these tests would be measuring it.
    _run(
        DRAW,
        "-f",
        "-g",
        image,
        EIPS=eips.path,
        INDOOR_TEMP_FBINK=fbink.path if fbink else "/nonexistent/fbink",
        **env,
    )


@pytest.mark.parametrize(
    "reading,unit,drawn",
    [
        ("73 Fahrenheit", "F", " 23"),
        ("8", "C", "  8"),
        # Right-aligned by padding rather than by moving, so every reading ends
        # against the degree sign the image carries, and the blanks repaint the
        # cells the previous one used.
        ("-5", "C", " -5"),
        ("14 Fahrenheit", "F", "-10"),
    ],
)
def test_fbink_draws_the_value_right_aligned_in_its_slot(eips, fbink, reading, unit, drawn):
    _draw(eips, fbink=fbink, INDOOR_TEMP_CMD=f"echo {reading}", INDOOR_TEMP_UNIT=unit)

    assert eips() == ["-f -g /tmp/dash.png"]
    assert fbink() == [
        f"-q -F IBM -S {model.INDOOR_SCALE} -x 0 -y 0 "
        f"-X {model.INDOOR_SLOT_X} -Y {model.INDOOR_SLOT_Y} -- {drawn}"
    ]


@pytest.mark.parametrize(
    "reading,unit,drawn",
    [
        ("73 Fahrenheit", "F", "    23"),
        ("8", "C", "     8"),
        # Without that leading blank eips would read a temperature below zero as
        # one of its own options, which is why the value is padded to the full
        # width of the hole and not merely aligned in it.
        ("-5", "C", "    -5"),
        ("14 Fahrenheit", "F", "   -10"),
    ],
)
def test_eips_draws_the_value_in_the_same_hole_when_fbink_is_missing(
    eips, reading, unit, drawn
):
    _draw(eips, INDOOR_TEMP_CMD=f"echo {reading}", INDOOR_TEMP_UNIT=unit)

    col, row, chars = model.indoor_eips_cells()
    assert len(drawn) == chars
    assert eips() == ["-f -g /tmp/dash.png", f"{col} {row} {drawn}"]


def test_the_image_is_drawn_even_when_the_sensor_is_not_there(eips, fbink):
    _draw(eips, fbink=fbink, INDOOR_TEMP_CMD="false")
    assert eips() == ["-f -g /tmp/dash.png"]
    assert fbink() == []


def test_the_overlay_can_be_turned_off_on_the_device(eips, fbink):
    _draw(eips, fbink=fbink, INDOOR_TEMP_CMD="echo 73 Fahrenheit", INDOOR_TEMP="false")
    assert eips() == ["-f -g /tmp/dash.png"]
    assert fbink() == []


def test_the_sleeping_screen_gets_no_temperature(eips, fbink):
    # It is not the dashboard: it has no slot to write into.
    _draw(
        eips,
        image="/mnt/us/dashboard/sleeping.png",
        fbink=fbink,
        INDOOR_TEMP_CMD="echo 73 Fahrenheit",
    )
    assert eips() == ["-f -g /mnt/us/dashboard/sleeping.png"]
    assert fbink() == []


# ------------------------------------------------------------- the KUAL menu
#
# KUAL reports none of this: a malformed menu.json, an id that does not match
# the directory, an action pointing at nothing — each of them makes the whole
# extension disappear from the menu in silence, on a device with no terminal to
# ask why. Cheap to check here, tedious to diagnose there.


def test_the_menu_is_valid_json():
    json.loads((EXTENSION / "menu.json").read_text(encoding="utf-8"))


def test_the_extension_id_matches_its_directory():
    root = ET.parse(EXTENSION / "config.xml").getroot()
    assert root.findtext("information/id") == EXTENSION.name


def test_every_menu_entry_points_at_a_script_that_is_there():
    menu = json.loads((EXTENSION / "menu.json").read_text(encoding="utf-8"))
    actions = [item["action"] for item in menu["items"]]
    assert actions, "the menu has no entries"

    for action in actions:
        script = EXTENSION / action
        assert script.is_file(), f"{action} is not in the extension"
        # /mnt/us is FAT and may not keep the bit, which is why install.sh
        # chmods on arrival — but a file that is not executable here would not
        # be worth chmoding there.
        assert script.stat().st_mode & 0o111, f"{action} is not executable"


@pytest.mark.parametrize("script", sorted((EXTENSION / "bin").glob("*.sh")), ids=lambda p: p.name)
def test_the_menu_scripts_parse_as_posix_sh(script):
    # busybox ash on the device, /bin/sh here: neither has bashisms.
    done = subprocess.run(["sh", "-n", str(script)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
