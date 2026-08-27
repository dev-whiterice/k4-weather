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
import os
import re
import shutil
import signal
import struct
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

from k4weather import model

KINDLE = Path(__file__).resolve().parents[1] / "kindle" / "local"
INDOOR_TEMP = str(KINDLE / "indoor-temp.sh")
DRAW = str(KINDLE / "draw.sh")

EXTENSION = KINDLE.parent / "extensions" / "k4weather"

# Windows has no execute bit, so `st_mode & 0o111` there says nothing at all:
# NTFS reports 0o666 for every file Git checks out, executable or not. What is
# actually shared between contributors — and what a `git clone` on macOS turns
# into a real execute bit — is the mode Git records in the index, so that is
# what gets asked. The filesystem is the fallback, for a source tree that is
# not a checkout.
WINDOWS = os.name == "nt"


def _is_executable(path: Path) -> bool:
    if not WINDOWS:
        return bool(path.stat().st_mode & 0o111)
    if shutil.which("git") is None:
        return True  # nothing to check against; not worth a false failure
    done = subprocess.run(
        ["git", "ls-files", "-s", "--", str(path)],
        capture_output=True,
        text=True,
        cwd=path.parent,
    )
    if done.returncode != 0 or not done.stdout.strip():
        return True
    return done.stdout.split()[0] == "100755"


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


INDOOR_TTF = KINDLE.parent / "fonts" / "indoor.ttf"


def _draw(eips, image="/tmp/dash.png", fbink=None, ttf=False, **env) -> None:
    # Neither is ever left to its default. draw.sh picks the first of three
    # renderers that is actually present, so a test that does not say which are
    # present is not testing the one it thinks it is: on a machine where fbink
    # has been dropped into kindle/ ready to install, or simply where
    # kindle/fonts/indoor.ttf is checked out — which it always is — the default
    # would silently select a different branch.
    _run(
        DRAW,
        "-f",
        "-g",
        image,
        EIPS=eips.path,
        INDOOR_TEMP_FBINK=fbink.path if fbink else "/nonexistent/fbink",
        INDOOR_TEMP_TTF=str(INDOOR_TTF) if ttf else "/nonexistent/indoor.ttf",
        **env,
    )


@pytest.mark.parametrize(
    "reading,unit,drawn",
    [
        # Padded to the width of the box, which is what right-aligns it: every
        # character of indoor.ttf advances the same width, the blank included,
        # so two digits and three end in the same place. It is also what covers
        # the dash the image carries for a sensor that cannot be read.
        ("73 Fahrenheit", "F", " 23"),
        ("8", "C", "  8"),
        ("-5", "C", " -5"),
        ("14 Fahrenheit", "F", "-10"),
    ],
)
def test_fbink_draws_the_value_in_the_page_font_when_the_font_is_there(
    eips, fbink, reading, unit, drawn
):
    """The first choice, and the only one that looks like the rest of the page.

    fbink takes margins, not coordinates, so every number here is derived from
    the slot: `top` and `left` are its own corner, `bottom` and `right` are
    what is left of the 600x800 panel beyond it. Bounding the drawing area to
    the slot is what stops a wide reading from spilling over the rule beside it.
    """
    _draw(eips, fbink=fbink, ttf=True, INDOOR_TEMP_CMD=f"echo {reading}", INDOOR_TEMP_UNIT=unit)

    slot = model.indoor_slot()
    assert eips() == ["-f -g /tmp/dash.png"]
    assert fbink() == [
        f"-q -t regular={INDOOR_TTF},px=30,top={slot.y},"
        f"bottom={800 - slot.y - slot.height},left={slot.x},"
        f"right={600 - slot.x - slot.width},padding=BOTH -- {drawn}"
    ]


def test_a_missing_font_falls_back_to_the_bitmap_face(eips, fbink):
    # An installation from before the font existed, or one where the copy did
    # not arrive: still legible, just visibly another program's work.
    _draw(eips, fbink=fbink, ttf=False, INDOOR_TEMP_CMD="echo 21", INDOOR_TEMP_UNIT="C")

    assert fbink() == [
        f"-q -F IBM -S {model.INDOOR_SCALE} -x 0 -y 0 "
        f"-X {model.INDOOR_SLOT_X} -Y {model.INDOOR_SLOT_Y} -- {' 21'}"
    ]


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
    _draw(eips, fbink=fbink, ttf=False, INDOOR_TEMP_CMD=f"echo {reading}", INDOOR_TEMP_UNIT=unit)

    assert eips() == ["-f -g /tmp/dash.png"]
    assert fbink() == [
        f"-q -F IBM -S {model.INDOOR_SCALE} -x 0 -y 0 "
        f"-X {model.INDOOR_SLOT_X} -Y {model.INDOOR_SLOT_Y} -- {drawn}"
    ]


@pytest.mark.parametrize(
    "reading,unit,drawn",
    [
        ("73 Fahrenheit", "F", "  23"),
        ("8", "C", "   8"),
        # Without that leading blank eips would read a temperature below zero as
        # one of its own options, which is why the value is padded to the full
        # width of the hole and not merely aligned in it.
        ("-5", "C", "  -5"),
        ("14 Fahrenheit", "F", " -10"),
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


def _menu_actions() -> list[tuple[str, str]]:
    """Every menu action, split into the interpreter and the script it runs."""
    menu = json.loads((EXTENSION / "menu.json").read_text(encoding="utf-8"))
    actions = [item["action"] for item in menu["items"]]
    assert actions, "the menu has no entries"
    return [tuple(action.split()) for action in actions]


def _install_ext_dir() -> str:
    """The directory install.sh copies the extension into, on the device."""
    text = (KINDLE.parent / "install.sh").read_text(encoding="utf-8")
    match = re.search(r'^EXT_DIR="([^"]+)"$', text, re.MULTILINE)
    assert match, "install.sh no longer declares EXT_DIR"
    return match.group(1)


def test_every_menu_entry_names_its_interpreter():
    """The action is a shell command, and it has to name the shell.

    /mnt/us is FAT: the execute bit there is synthesised from the mount options
    rather than stored per file, so calling a script directly is a bet on how
    the partition happens to be mounted. Losing that bet fails the way every
    KUAL failure does — the menu prints the action, exits, and the error goes
    only to /var/tmp/KUAL.log. Naming the interpreter takes the bet off the
    table.
    """
    for interpreter, script in _menu_actions():
        assert interpreter == "/bin/sh", f"{script} is not launched through /bin/sh"


def test_every_menu_entry_points_at_a_script_that_is_there():
    """And points at it by the absolute path it will have on the device.

    A relative action rides on KUAL setting the working directory to the
    extension folder, which is a promise made by a Java kindlet on a 2011
    device and not one worth depending on: kindle-dash's own KUAL extension
    uses an absolute path too. That makes menu.json and install.sh agree on
    where the extension lives, so this checks they still do.
    """
    ext_dir = _install_ext_dir()

    for _, script in _menu_actions():
        assert script.startswith(f"{ext_dir}/"), (
            f"{script} is not under {ext_dir}, where install.sh puts the extension"
        )
        here = EXTENSION / script[len(ext_dir) + 1:]
        assert here.is_file(), f"{script} is not in the extension"
        # No longer what makes the entry work — the interpreter is named above
        # — but the scripts are run by hand over SSH too, and install.sh chmods
        # them on arrival. A file not executable here is not worth chmoding.
        assert _is_executable(here), (
            f"{script} is not executable (git mode is not 100755)"
        )


@pytest.mark.parametrize(
    "script",
    sorted((EXTENSION / "bin").glob("*.sh")) + sorted(KINDLE.glob("*.sh")),
    ids=lambda p: p.name,
)
def test_no_device_script_has_carriage_returns(script):
    """The one thing a Windows checkout gets wrong, and the worst one.

    busybox `ash` does not treat a carriage return as whitespace: it is an
    ordinary character and it ends up inside the value of whatever assignment
    it terminates. `DASH_DIR=${DASH_DIR:-/mnt/us/dashboard}` then names a
    directory that does not exist, and `INTERACT=${INTERACT:-true}` holds
    something that is not equal to `true`, so the page buttons quietly stop
    being read. Neither failure says anything on a device with no terminal.

    The .gitattributes at the root of the repository is what prevents this,
    and this is what notices if it ever stops working — including for a
    contributor whose editor decides to be helpful.
    """
    assert b"\r" not in script.read_bytes(), (
        f"{script.name} has CRLF line endings. Run 'make lineendings' (or "
        "'git add --renormalize .') — this file cannot run on the Kindle."
    )


@pytest.mark.parametrize(
    "script",
    sorted((EXTENSION / "bin").glob("*.sh")) + sorted(KINDLE.glob("*.sh")),
    ids=lambda p: p.name,
)
def test_every_device_script_parses_as_posix_sh(script):
    # busybox ash on the device, /bin/sh here: neither has bashisms. A syntax
    # error in any of these is only discovered on a Kindle with no terminal,
    # usually after it has already stopped drawing.
    done = subprocess.run(["sh", "-n", str(script)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


# ------------------------------------------------------- switching locations
#
# The panel shows one location at a time and the page buttons walk through the
# list. None of it can be tried without a Kindle in front of you, which is
# exactly why the parts that are pure shell are exercised here: the cycle and
# its wrap-around, the state file and the three ways it goes stale, and the
# decoding of raw evdev bytes into "the right-hand page button was pressed".

LOCATIONS = str(KINDLE / "locations.sh")
INTERACT = str(KINDLE / "interact.sh")
SUSPEND = str(KINDLE / "suspend.sh")

MANIFEST = [
    ("caoria", "Caoria"),
    ("fumane", "Fumane"),
    ("verona", "Verona"),
]


def _event(type_: int, code: int, value: int) -> bytes:
    """One `struct input_event` as the 32-bit kernel on the device lays it out."""
    return struct.pack("<iiHHi", 0, 0, type_, code, value)


def _button(code: int) -> bytes:
    """What one press of a page button really puts on the wire.

    Measured with `kindle/tools/keytest.sh`: a scancode, the key going down, a
    second scancode, the key coming back up. Only the second event may move the
    panel — the rest is what the decoder has to step over.
    """
    return _event(4, 4, 7) + _event(1, code, 1) + _event(4, 4, 7) + _event(1, code, 0)


@pytest.fixture
def device(tmp_path):
    """A stand-in for /mnt/us/dashboard: manifest, cached images, a fake draw.sh."""
    root = tmp_path / "dashboard"
    (root / "cache").mkdir(parents=True)
    (root / "state").mkdir()

    (root / "cache" / "locations.txt").write_text(
        "".join(f"{id_}\tdashboard-{id_}.png\t{name}\n" for id_, name in MANIFEST),
        encoding="utf-8",
    )
    for id_, _ in MANIFEST:
        (root / "cache" / f"{id_}.png").write_bytes(b"\x89PNG not really")

    draw = _recorder(tmp_path, "draw.sh")
    state = root / "state" / "location"

    return SimpleNamespace(
        path=root,
        state=state,
        # What draw.sh was asked to paint, and what the device would show after
        # a reboot: the two things every test below is really about.
        drawn=draw,
        stored=lambda: state.read_text(encoding="utf-8").strip() if state.exists() else None,
        env={"DASH_DIR": str(root), "LOC_DRAW": draw.path},
    )


def _loc(device, script: str, **env) -> subprocess.CompletedProcess:
    """Source locations.sh and run one line against the fake installation."""
    return subprocess.run(
        ["sh", "-c", f'. "{LOCATIONS}"\n{script}\n'],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", **device.env, **env},
    )


def test_only_locations_with_an_image_are_in_the_cycle(device):
    # A location whose download has never succeeded is skipped: a button press
    # that led to a blank screen would look like a crash.
    (device.path / "cache" / "fumane.png").unlink()

    assert _loc(device, "loc_ids").stdout.split() == ["caoria", "verona"]


def test_the_cycle_wraps_in_both_directions(device):
    assert _loc(device, 'loc_step verona 1').stdout.strip() == "caoria"
    assert _loc(device, 'loc_step caoria -1').stdout.strip() == "verona"
    assert _loc(device, 'loc_step caoria 1').stdout.strip() == "fumane"
    assert _loc(device, 'loc_step fumane -1').stdout.strip() == "caoria"


def test_the_current_location_is_the_stored_one(device):
    device.state.write_text("verona\n", encoding="utf-8")
    assert _loc(device, "loc_current").stdout.strip() == "verona"


@pytest.mark.parametrize("stored", ["", "trento", "  \n"])
def test_a_stale_state_file_falls_back_to_the_first_location(device, stored):
    # The three ways it goes stale: never written, written empty, or naming a
    # location that has since been removed from config.yaml. All three have to
    # recover on their own — there is nobody at the panel to ask.
    device.state.write_text(stored, encoding="utf-8")
    assert _loc(device, "loc_current").stdout.strip() == "caoria"


def test_showing_a_location_asks_for_a_full_refresh(device):
    # A location change replaces every pixel: a partial update would leave the
    # previous place ghosting through the new one.
    _loc(device, "loc_go fumane")

    assert device.drawn() == [f"-f -g {device.path}/dash.png"]
    assert (device.path / "dash.png").read_bytes() == b"\x89PNG not really"
    assert device.stored() == "fumane"


def test_the_state_is_recorded_only_once_the_panel_agrees(device, tmp_path):
    # Written before the draw, a state file would survive a power cut that the
    # image did not, and the panel would come back naming a place it is not
    # showing.
    failing = tmp_path / "failing-draw.sh"
    failing.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    failing.chmod(0o755)

    done = _loc(device, "loc_go fumane", LOC_DRAW=str(failing))

    assert done.returncode != 0
    assert device.stored() is None


# --------------------------------------------------- reading the page buttons


def _interact(device, presses: bytes, tmp_path, seconds="2", **env):
    """Run the listening window against a canned stream of key events.

    `dd` does not care that the input device is an ordinary file here: it reads
    the events, reaches the end and stops, which is the same thing that happens
    on the device when nothing more is pressed.
    """
    keys = tmp_path / "events.bin"
    keys.write_bytes(presses)

    return subprocess.run(
        ["sh", INTERACT, seconds],
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "KEY_DEVICE": str(keys),
            "CAPTURE": str(tmp_path / "capture.bin"),
            "INTERACT_FLASH": "false",
            # Every press pushes the deadline out by INTERACT_EXTEND, which is
            # 15 seconds on the device and would be 15 seconds of waiting here.
            # The extension has a test of its own below.
            "INTERACT_EXTEND": "1",
            **device.env,
            **env,
        },
    )


def test_a_page_button_moves_one_location(device, tmp_path):
    device.state.write_text("caoria\n", encoding="utf-8")

    _interact(device, _button(191), tmp_path)

    assert device.stored() == "fumane"
    assert device.drawn() == [f"-f -g {device.path}/dash.png"]


def test_both_sides_of_the_device_do_the_same_thing(device, tmp_path):
    # 191 is the right-hand page-forward button and 104 the left-hand one: the
    # panel answers whichever thumb is on it.
    device.state.write_text("caoria\n", encoding="utf-8")
    _interact(device, _button(104), tmp_path)
    assert device.stored() == "fumane"


def test_the_other_direction_walks_back(device, tmp_path):
    device.state.write_text("caoria\n", encoding="utf-8")

    _interact(device, _button(109), tmp_path)

    assert device.stored() == "verona"  # wrapped round the end of the list


def test_holding_a_button_down_still_moves_one_location(device, tmp_path):
    # The 5-way repeats while held and the page buttons could too. Only the key
    # going *down* counts: otherwise leaning on a button would run through the
    # whole list and stop somewhere arbitrary.
    device.state.write_text("caoria\n", encoding="utf-8")
    held = _event(1, 191, 1) + _event(1, 191, 2) + _event(1, 191, 2) + _event(1, 191, 0)

    _interact(device, held, tmp_path)

    assert device.stored() == "fumane"


def test_two_presses_move_two_locations(device, tmp_path):
    device.state.write_text("caoria\n", encoding="utf-8")

    _interact(device, _button(191) + _button(191), tmp_path)

    assert device.stored() == "verona"


def test_a_press_buys_more_time_to_press_again(device, tmp_path):
    # Walking five locations must not need five presses inside one window that
    # is running out: each press restarts the clock. Measured as a lower bound
    # on how long the window stayed open, which is the only observable the
    # script has from out here.
    device.state.write_text("caoria\n", encoding="utf-8")

    started = time.monotonic()
    _interact(device, _button(191), tmp_path, seconds="1", INTERACT_EXTEND="3")
    elapsed = time.monotonic() - started

    assert elapsed >= 3
    assert device.stored() == "fumane"


def test_the_buttons_that_are_not_ours_are_left_alone(device, tmp_path):
    # MENU, BACK and HOME all arrive on the same device. Answering them would
    # make the panel unpredictable to anyone who picks the Kindle up.
    device.state.write_text("caoria\n", encoding="utf-8")

    _interact(device, _button(139) + _button(158) + _button(102), tmp_path)

    assert device.stored() == "caoria"
    assert device.drawn() == []


def test_turning_the_feature_off_gives_back_a_plain_sleep(device, tmp_path):
    # INTERACT=false has to restore the upstream behaviour exactly: the window
    # is the only chance to interrupt the loop by hand before it suspends, so
    # it must still be waited out, not skipped.
    device.state.write_text("caoria\n", encoding="utf-8")

    started = time.monotonic()
    done = _interact(device, _button(191), tmp_path, seconds="1", INTERACT="false")
    elapsed = time.monotonic() - started

    assert done.returncode == 0
    assert elapsed >= 1
    assert device.stored() == "caoria"
    assert device.drawn() == []


# ------------------------------------------------------------ the two halves


@pytest.mark.parametrize(
    "variable,script,fallback",
    [
        ("KEY_DEVICE", INTERACT, "auto"),
        ("KEY_NEXT", INTERACT, "191 104"),
        ("KEY_PREV", INTERACT, "109 193"),
        ("INTERACT_EXTEND", INTERACT, "15"),
        ("INTERACT_SECONDS", SUSPEND, "25"),
        ("EARLY_WAKE_MARGIN", SUSPEND, "10"),
    ],
)
def test_the_scripts_fall_back_to_what_env_sh_configures(variable, script, fallback):
    # Each of these is written twice: once in env.sh, where it is meant to be
    # changed, and once as a fallback in the script, for the case where it is
    # run by hand without sourcing env.sh first. Two spellings of one value is
    # exactly the kind of thing that drifts.
    text = Path(script).read_text(encoding="utf-8")
    match = re.search(rf"^{variable}=\$\{{{variable}:-\"?([^\"}}]*)\"?\}}$", text, re.MULTILINE)
    assert match, f"{variable} has no fallback in {Path(script).name}"
    assert match.group(1) == fallback == _env_default(variable)


# ------------------------------------------------------------- the download
#
# One wake-up in thirty minutes, and this script decides whether the panel
# updates at all. What it must never do is worse than not updating: write a
# half-downloaded file over a good one, drop an image it cannot replace, or
# hand kindle-dash a target it has torn up.

FETCH = str(KINDLE / "fetch-dashboard.sh")


@pytest.fixture
def origin(tmp_path):
    """A stand-in for GitHub Pages, plus the `xh` that fetches from it."""
    served = tmp_path / "served"
    served.mkdir()
    (served / "locations.txt").write_text(
        "".join(f"{id_}\tdashboard-{id_}.png\t{name}\n" for id_, name in MANIFEST),
        encoding="utf-8",
    )
    for id_, _ in MANIFEST:
        (served / f"dashboard-{id_}.png").write_bytes(f"image of {id_}".encode())

    # `xh -d -q --follow -o OUT get URL`, reduced to a file copy. FAIL lists the
    # file names this run must refuse, which is how a location that CI could not
    # render — or a flaky network — is reproduced.
    fake = tmp_path / "xh"
    fake.write_text(
        f'''#!/bin/sh
# The first thing it does, because it is the first thing the real one does.
#
# xh follows httpie: standard input that is not a terminal is the body of the
# request, so it reads stdin to the end whether or not anything is there. A
# stub that skipped this was the reason the suite passed for a version of
# fetch-dashboard.sh that downloaded exactly one location out of five on the
# device — the loop walking the manifest had the manifest as its stdin, and xh
# ate it. Faithfulness here is not pedantry: it is the whole test.
cat > /dev/null
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out=$2; shift 2 ;;
    get) url=$2; shift 2 ;;
    *) shift ;;
  esac
done
name=${{url##*/}}
case " ${{FAIL:-}} " in *" $name "*) exit 1 ;; esac
[ -f "{served}/$name" ] || exit 1
cp "{served}/$name" "$out"
''',
        encoding="utf-8",
    )
    fake.chmod(0o755)

    return SimpleNamespace(served=served, xh=str(fake))


def _fetch(device, origin, target, fail="", **env) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sh", FETCH, str(target)],
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "XH": origin.xh,
            "FAIL": fail,
            # One attempt: the real script backs off for fifteen seconds
            # between tries, which is right on a wall and wrong here.
            "ATTEMPTS": "1",
            "BASE_URL": "https://example.invalid/k4-weather",
            **device.env,
            **env,
        },
    )


def test_every_location_is_downloaded_and_the_current_one_is_handed_over(
    device, origin, tmp_path
):
    # Every image, not just the one on screen: switching has to work with the
    # Wi-Fi off, so the cost is paid while the radio is already up.
    target = tmp_path / "dash.png"
    device.state.write_text("fumane\n", encoding="utf-8")

    done = _fetch(device, origin, target)

    assert done.returncode == 0
    for id_, _ in MANIFEST:
        assert (device.path / "cache" / f"{id_}.png").read_bytes() == f"image of {id_}".encode()
    assert target.read_bytes() == b"image of fumane"


def test_one_location_failing_leaves_the_others_alone(device, origin, tmp_path):
    # CI publishes nothing for a location whose data did not arrive, and the
    # copy already in the cache is a few hours old at worst.
    target = tmp_path / "dash.png"
    (device.path / "cache" / "verona.png").write_bytes(b"yesterday")

    done = _fetch(device, origin, target, fail="dashboard-verona.png")

    assert done.returncode == 0
    assert (device.path / "cache" / "verona.png").read_bytes() == b"yesterday"
    assert (device.path / "cache" / "fumane.png").read_bytes() == b"image of fumane"
    # And nothing half-written was left behind to be picked up as an image.
    assert not list((device.path / "cache").glob("*.new"))


def test_a_location_that_left_the_config_leaves_the_cache_too(device, origin, tmp_path):
    # The cycle is built from what is on disk, so an image nobody removed would
    # stay reachable with the page buttons for ever.
    stale = device.path / "cache" / "trento.png"
    stale.write_bytes(b"no longer configured")

    _fetch(device, origin, tmp_path / "dash.png")

    assert not stale.exists()


def test_a_download_that_fails_completely_does_not_touch_the_target(
    device, origin, tmp_path
):
    # kindle-dash reads the exit code and leaves the previous image on screen.
    # An empty or truncated target would be drawn, and a torn dashboard on a
    # wall is worse than an old one.
    target = tmp_path / "dash.png"
    target.write_bytes(b"the image already on screen")
    for cached in (device.path / "cache").glob("*.png"):
        cached.unlink()

    done = _fetch(
        device, origin, target,
        fail="locations.txt dashboard-caoria.png dashboard-fumane.png dashboard-verona.png",
    )

    assert done.returncode != 0
    assert target.read_bytes() == b"the image already on screen"


def test_a_manifest_that_will_not_download_falls_back_to_the_cached_one(
    device, origin, tmp_path
):
    # The list changes when somebody edits config.yaml, which is roughly never.
    # The images are what go stale, and they are downloadable on their own.
    target = tmp_path / "dash.png"

    done = _fetch(device, origin, target, fail="locations.txt")

    assert done.returncode == 0
    assert target.read_bytes() == b"image of caoria"


def test_the_state_follows_the_image_that_was_actually_handed_over(
    device, origin, tmp_path
):
    # The stored location no longer has an image: the fallback picked another
    # one, and the state file has to say so — otherwise the next press would
    # step away from a place the panel was never showing.
    device.state.write_text("verona\n", encoding="utf-8")
    (device.path / "cache" / "verona.png").unlink()

    _fetch(device, origin, tmp_path / "dash.png", fail="dashboard-verona.png")

    assert device.stored() == "caoria"


@pytest.mark.skipif(
    WINDOWS,
    reason="POSIX process groups: os.killpg does not exist on Windows, and the "
    "MSYS shell this would signal is not the shell that runs on the Kindle",
)
def test_ctrl_c_during_the_window_still_stops_the_panel(device, tmp_path):
    """The ten-second window is the documented way to interrupt the loop.

    It used to be a plain `sleep`, which Ctrl-C killed along with the shell
    waiting on it. Now it is a script with traps, and a trap that cleans up and
    *returns* swallows the signal: the window would run to its end and the loop
    around it would carry on, because a shell only aborts when a child of it
    dies of a signal. Re-raising is what keeps the old behaviour.
    """
    loop = tmp_path / "loop.sh"
    loop.write_text(f'#!/bin/sh\nsh {INTERACT} 30\necho "STILL RUNNING"\n', encoding="utf-8")

    running = subprocess.Popen(
        ["sh", str(loop)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        # Its own process group, so the signal below reaches the whole of it —
        # which is what a terminal does on Ctrl-C.
        start_new_session=True,
        env={
            "PATH": "/usr/bin:/bin",
            "KEY_DEVICE": "/dev/null",
            "CAPTURE": str(tmp_path / "capture.bin"),
            "INTERACT_FLASH": "false",
            **device.env,
        },
    )
    time.sleep(1.5)
    os.killpg(os.getpgid(running.pid), signal.SIGINT)

    try:
        running.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(running.pid), signal.SIGKILL)
        running.wait()
        pytest.fail("the window ignored Ctrl-C and ran to the end of its 30 seconds")

    assert "STILL RUNNING" not in running.stdout.read()
