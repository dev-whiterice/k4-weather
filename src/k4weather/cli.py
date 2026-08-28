"""Command line interface.

    python -m k4weather generate            # live data -> out/dashboard-<id>.png
    python -m k4weather preview             # data from a fixture, no network
    python -m k4weather inspect out

Every command returns a shell exit code: 0 when the images are fit for `eips`,
1 when they are not. The workflow relies on that to fail loudly.

`generate` renders one image per configured location and writes the manifest
that ties them together. A location whose data cannot be fetched does not take
the others down with it — see `_render_all`.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from . import fetch, manifest, postprocess, render
from .config import Config, Location, load_config
from .model import build_dashboard

log = logging.getLogger("k4weather")

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _render_one(
    forecast,
    air_quality,
    cfg: Config,
    location: Location,
    out_dir: Path,
    take,
    now=None,
) -> int:
    """Model -> HTML -> raw screenshot -> e-ink PNG, then validate the result.

    Returns the number of problems found in the finished image, so the caller
    can tell a transport failure (retry next run) from an image this device
    cannot draw (a bug, and the run has to say so).
    """
    out_png = out_dir / location.image
    dashboard = build_dashboard(forecast, air_quality, cfg, now=now, location=location)
    html = render.build_html(dashboard, cfg)

    out_html = out_png.with_suffix(".html")
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")
    log.info("preview HTML: %s", out_html)

    # The screenshot lands in a scratch file first: only the quantised copy is
    # meant to be published, and the raw one must not linger next to it.
    raw_png = out_png.with_name(out_png.stem + ".raw.png")
    try:
        take(html, raw_png)
        report = postprocess.to_eink_png(raw_png, out_png, cfg)
    finally:
        raw_png.unlink(missing_ok=True)

    problems = postprocess.validate(report, cfg)
    log.info(report.describe())
    for problem in problems:
        log.error("%s: invalid image: %s", location.id, problem)
    return len(problems)


def _render_all(cfg: Config, out_dir: Path, save_fixtures: Path | None = None) -> int:
    """Render every configured location. Returns the process exit code.

    Two kinds of failure, deliberately treated differently:

    - **the data did not arrive.** Open-Meteo timed out, or the network blinked.
      The other locations are still rendered and published; the one that failed
      keeps whatever the device already has in its cache, and the next run
      thirty minutes later almost always fixes it. Only a run where *nothing*
      rendered is a failed run.
    - **the image came out wrong.** Not transient and not the network's fault:
      that is a bug in this program, it would publish something `eips` draws as
      garbage, and the run fails whatever else succeeded.
    """
    rendered = 0
    unreachable: list[str] = []
    broken = 0

    with render.screenshotter(cfg) as take:
        for location in cfg.locations:
            try:
                forecast = fetch.fetch_forecast(cfg, location=location)
                air_quality = fetch.fetch_air_quality(cfg, location=location)
            except Exception as exc:  # noqa: BLE001 — any transport error is the same here
                log.error("%s (%s): no data, skipped — %s", location.id, location.name, exc)
                unreachable.append(location.id)
                continue

            if save_fixtures is not None:
                # Named the way the fixtures already in tests/ are, so a payload
                # captured here can be dropped straight in beside them.
                save_fixtures.mkdir(parents=True, exist_ok=True)
                (save_fixtures / f"forecast_{location.id}.json").write_text(
                    json.dumps(forecast, indent=2), encoding="utf-8"
                )
                if air_quality is not None:
                    (save_fixtures / f"air_quality_{location.id}.json").write_text(
                        json.dumps(air_quality, indent=2), encoding="utf-8"
                    )

            broken += _render_one(forecast, air_quality, cfg, location, out_dir, take)
            rendered += 1

    if unreachable:
        log.warning(
            "%d of %d locations had no data this run: %s",
            len(unreachable), len(cfg.locations), ", ".join(unreachable),
        )
    if not rendered:
        log.error("no location could be rendered: nothing to publish")
        return 1
    return 1 if broken else 0


def cmd_generate(args) -> int:
    """Fetch live data and render every location."""
    cfg = load_config(args.config)
    out_dir = Path(args.out_dir)
    save_fixtures = Path(args.save_fixtures) if args.save_fixtures else None
    status = _render_all(cfg, out_dir, save_fixtures)

    # Written even when a location was skipped: the manifest describes the
    # configuration, not the outcome of one run, and the device treats an image
    # it cannot download as "keep the copy I have" rather than as a gap.
    json_path, text_path = manifest.write(cfg.locations, out_dir)
    log.info("manifest: %s, %s", json_path, text_path)
    return status


def cmd_preview(args) -> int:
    """Render the primary location from a stored payload, so design work needs
    no network."""
    cfg = load_config(args.config)
    fixture = Path(args.fixture)
    forecast = json.loads(fixture.read_text(encoding="utf-8"))
    # Fixture `forecast_X.json` pairs with `air_quality_X.json`, when present.
    air_path = fixture.with_name(fixture.name.replace("forecast_", "air_quality_", 1))
    air_quality = (
        json.loads(air_path.read_text(encoding="utf-8")) if air_path.exists() else None
    )
    # Anchor "now" to the fixture, which makes the preview reproducible.
    observed = forecast.get("current", {}).get("time")
    now = datetime.fromisoformat(observed) if observed else None

    out_dir = Path(args.out_dir)
    with render.screenshotter(cfg) as take:
        problems = _render_one(
            forecast, air_quality, cfg, cfg.location, out_dir, take, now=now
        )
    return 1 if problems else 0


def _images(path: Path) -> list[Path]:
    """The images `inspect` was pointed at: one file, or every one in a directory."""
    if path.is_dir():
        return sorted(path.glob("dashboard-*.png"))
    return [path]


def cmd_inspect(args) -> int:
    """Check already generated PNGs against the constraints of `eips`."""
    cfg = load_config(args.config)
    images = _images(Path(args.image))
    if not images:
        print(f"no dashboard image found in {args.image}")
        return 1

    failed = 0
    for image in images:
        report = postprocess.inspect(image)
        print(report.describe())
        problems = postprocess.validate(report, cfg)
        for problem in problems:
            print(f"  ✗ {problem}")
        if problems:
            failed += 1
        else:
            print("  ✓ compatible with eips on the Kindle 4")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    # Windows chooses the ANSI code page for a redirected stream, and neither
    # the check marks `inspect` prints nor the dashes in the log messages are
    # in it: `python -m k4weather inspect out > report.txt` then died on an
    # encode error rather than printing a report, and the same run through a
    # terminal was fine. UTF-8 on both streams, and replacement rather than an
    # exception wherever even that cannot be honoured.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="k4weather")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="fetch the data and render every location")
    generate.add_argument("--out-dir", default="out")
    generate.add_argument("--save-fixtures", metavar="DIR",
                          help="also write each raw API payload here, named as in tests/fixtures")
    generate.set_defaults(func=cmd_generate)

    preview = subparsers.add_parser("preview", help="render the primary location from a fixture")
    preview.add_argument("--fixture", default=str(FIXTURES / "forecast_caoria.json"))
    preview.add_argument("--out-dir", default="out")
    preview.set_defaults(func=cmd_preview)

    inspect = subparsers.add_parser("inspect", help="check already generated images")
    inspect.add_argument("image", nargs="?", default="out",
                         help="an image, or a directory holding dashboard-*.png")
    inspect.set_defaults(func=cmd_inspect)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
