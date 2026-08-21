"""The index CI publishes beside the images, so nothing downstream has to guess.

Neither the Kindle nor the preview page may build an image URL by sticking an
id onto a prefix: the day the naming scheme changes, whatever did that would
keep asking for files that are no longer there. They read the list instead, and
the list says where each image is.

It is written twice, with the same content:

  locations.json  canonical, for the preview page and for humans
  locations.txt   the same list, one tab-separated record per line

The second exists because the reader on the other side is busybox `ash` with no
`jq`: parsing JSON there is a pile of `sed` that breaks on the first name with
an accent in it, while `while read -r id image name` is one line and cannot
misread anything. Both files are written by the same function, from the same
tuple, so they cannot drift apart.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from .config import Location

JSON_NAME = "locations.json"
TEXT_NAME = "locations.txt"


def as_json(locations: Sequence[Location], generated_at: datetime) -> str:
    """The manifest as JSON, in the order the buttons walk through it."""
    payload = {
        "generated_at": generated_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "locations": [
            {"id": location.id, "name": location.name, "image": location.image}
            for location in locations
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def as_text(locations: Sequence[Location]) -> str:
    """The manifest as tab-separated records: `id`, `image`, then `name`.

    The name goes last because it is the only field that can contain a space:
    `read -r id image name` then puts the whole of it, spaces included, in the
    last variable without any quoting on the device.
    """
    return "".join(
        f"{location.id}\t{location.image}\t{location.name}\n" for location in locations
    )


def write(
    locations: Sequence[Location],
    out_dir: Path,
    generated_at: datetime | None = None,
) -> tuple[Path, Path]:
    """Write both files into `out_dir` and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = generated_at or datetime.now(timezone.utc)

    json_path = out_dir / JSON_NAME
    text_path = out_dir / TEXT_NAME
    json_path.write_text(as_json(locations, stamp), encoding="utf-8")
    text_path.write_text(as_text(locations), encoding="utf-8")
    return json_path, text_path
