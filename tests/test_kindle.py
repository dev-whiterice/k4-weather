"""The client that runs on the Kindle.

Two things are worth testing off the device. The first is the coupling: the
indoor temperature is drawn by the Kindle at coordinates the layout has to
leave blank, and the two sides declare them separately — `model.py` in pixels,
`env.sh` in character cells. The second is the arithmetic that turns a battery
gas gauge reading into a number for the wall, which is fiddly precisely because
POSIX sh has no floating point.

Nothing in those scripts is Kindle-specific except the sensor command and
`eips` itself, and both are overridable from the environment: that is what
makes them runnable here.
"""

import re
import subprocess
from pathlib import Path

import pytest

from k4weather import model

KINDLE = Path(__file__).resolve().parents[1] / "kindle" / "local"
INDOOR_TEMP = str(KINDLE / "indoor-temp.sh")
DRAW = str(KINDLE / "draw.sh")


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
        ("INDOOR_TEMP_COL", model.INDOOR_SLOT_COL),
        ("INDOOR_TEMP_ROW", model.INDOOR_SLOT_ROW),
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


@pytest.fixture
def eips(tmp_path):
    """A stand-in for /usr/sbin/eips that records the calls instead."""
    log = tmp_path / "calls"
    fake = tmp_path / "eips"
    fake.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\n', encoding="utf-8")
    fake.chmod(0o755)

    def calls() -> list[str]:
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    calls.path = str(fake)  # type: ignore[attr-defined]
    return calls


def _draw(eips, image="/tmp/dash.png", **env) -> None:
    _run(DRAW, "-f", "-g", image, EIPS=eips.path, **env)


@pytest.mark.parametrize(
    "reading,unit,drawn",
    [
        ("73 Fahrenheit", "F", "  23"),
        ("8", "C", "   8"),
        # Right-aligned and padded rather than moved: without that leading
        # blank, eips would read a temperature below zero as one of its own
        # options.
        ("-5", "C", "  -5"),
    ],
)
def test_the_value_is_right_aligned_in_its_slot(eips, reading, unit, drawn):
    _draw(eips, INDOOR_TEMP_CMD=f"echo {reading}", INDOOR_TEMP_UNIT=unit)

    assert eips() == [
        "-f -g /tmp/dash.png",
        f"{model.INDOOR_SLOT_COL} {model.INDOOR_SLOT_ROW} {drawn}",
    ]


def test_the_image_is_drawn_even_when_the_sensor_is_not_there(eips):
    _draw(eips, INDOOR_TEMP_CMD="false")
    assert eips() == ["-f -g /tmp/dash.png"]


def test_the_overlay_can_be_turned_off_on_the_device(eips):
    _draw(eips, INDOOR_TEMP_CMD="echo 73 Fahrenheit", INDOOR_TEMP="false")
    assert eips() == ["-f -g /tmp/dash.png"]


def test_the_sleeping_screen_gets_no_temperature(eips):
    # It is not the dashboard: it has no slot to write into.
    _draw(eips, image="/mnt/us/dashboard/sleeping.png", INDOOR_TEMP_CMD="echo 73 Fahrenheit")
    assert eips() == ["-f -g /mnt/us/dashboard/sleeping.png"]
