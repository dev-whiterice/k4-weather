"""The index published beside the images.

Nothing downstream builds an image URL by hand: the preview page and the Kindle
both read the list. What matters here is that the two files always describe the
same thing, and that the text one stays parseable by a shell that has no JSON
parser and no way to quote a name with a space in it.
"""

import json
from datetime import datetime, timezone

import pytest

from k4weather import manifest
from k4weather.config import Location

TRICKY = Location(
    id="sant-anna",
    # An apostrophe, an accent and two spaces: everything the device side must
    # carry through untouched, and the reason ids are not derived from names.
    name="Sant'Anna di Valdieri",
    latitude=44.25,
    longitude=7.30,
)
PLAIN = Location(id="caoria", name="Caoria", latitude=46.19647, longitude=11.67804)


@pytest.fixture
def locations():
    return (PLAIN, TRICKY)


def test_json_keeps_the_configured_order(locations):
    payload = json.loads(manifest.as_json(locations, datetime.now(timezone.utc)))
    assert [entry["id"] for entry in payload["locations"]] == ["caoria", "sant-anna"]


def test_json_names_the_image_instead_of_leaving_it_to_be_guessed(locations):
    payload = json.loads(manifest.as_json(locations, datetime.now(timezone.utc)))
    assert payload["locations"][0]["image"] == "dashboard-caoria.png"


def test_the_timestamp_is_utc_and_second_precision(locations):
    stamp = datetime(2026, 8, 21, 10, 30, 5, tzinfo=timezone.utc)
    payload = json.loads(manifest.as_json(locations, stamp))
    assert payload["generated_at"] == "2026-08-21T10:30:05Z"


def test_text_has_one_tab_separated_record_per_location(locations):
    lines = manifest.as_text(locations).splitlines()
    assert lines == [
        "caoria\tdashboard-caoria.png\tCaoria",
        "sant-anna\tdashboard-sant-anna.png\tSant'Anna di Valdieri",
    ]


def test_the_name_is_last_so_a_shell_can_read_the_record(locations):
    # `while read -r id image name` puts everything after the second field in
    # `name`, spaces included. Any other field order would need quoting the
    # device cannot do.
    for line in manifest.as_text(locations).splitlines():
        id_, image, name = line.split("\t", 2)
        assert "\t" not in name
        assert image == f"dashboard-{id_}.png"


def test_both_files_describe_the_same_list(tmp_path, locations):
    json_path, text_path = manifest.write(locations, tmp_path)

    from_json = [
        entry["id"] for entry in json.loads(json_path.read_text(encoding="utf-8"))["locations"]
    ]
    from_text = [
        line.split("\t")[0] for line in text_path.read_text(encoding="utf-8").splitlines()
    ]
    assert from_json == from_text


def test_write_creates_the_directory(tmp_path, locations):
    target = tmp_path / "publish" / "nested"
    json_path, text_path = manifest.write(locations, target)
    assert json_path.is_file() and text_path.is_file()
