"""Command line interface.

    python -m k4weather generate            # live data -> out/dashboard.png
    python -m k4weather preview             # data from a fixture, no network
    python -m k4weather inspect out/dashboard.png

Every command returns a shell exit code: 0 when the image is fit for `eips`,
1 when it is not. The workflow relies on that to fail loudly.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from . import fetch, postprocess, render
from .config import load_config
from .model import build_dashboard

log = logging.getLogger("k4weather")

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _write_outputs(forecast, air_quality, cfg, out_png: Path, now=None) -> int:
    """Model -> HTML -> raw screenshot -> e-ink PNG, then validate the result."""
    dashboard = build_dashboard(forecast, air_quality, cfg, now=now)
    html = render.build_html(dashboard, cfg)

    out_html = out_png.with_suffix(".html")
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")
    log.info("preview HTML: %s", out_html)

    # The screenshot lands in a scratch file first: only the quantised copy is
    # meant to be published, and the raw one must not linger next to it.
    raw_png = out_png.with_name(out_png.stem + ".raw.png")
    try:
        render.html_to_png(html, raw_png, cfg)
        report = postprocess.to_eink_png(raw_png, out_png, cfg)
    finally:
        raw_png.unlink(missing_ok=True)

    problems = postprocess.validate(report, cfg)
    log.info(report.describe())
    for problem in problems:
        log.error("invalid image: %s", problem)
    return 1 if problems else 0


def cmd_generate(args) -> int:
    """Fetch live data and render the dashboard."""
    cfg = load_config(args.config)
    forecast = fetch.fetch_forecast(cfg)
    air_quality = fetch.fetch_air_quality(cfg)
    if args.save_fixture:
        Path(args.save_fixture).write_text(json.dumps(forecast, indent=2), encoding="utf-8")
    return _write_outputs(forecast, air_quality, cfg, Path(args.out))


def cmd_preview(args) -> int:
    """Render from a stored payload, so design work needs no network."""
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
    return _write_outputs(forecast, air_quality, cfg, Path(args.out), now=now)


def cmd_inspect(args) -> int:
    """Check an already generated PNG against the constraints of `eips`."""
    cfg = load_config(args.config)
    report = postprocess.inspect(Path(args.image))
    print(report.describe())
    problems = postprocess.validate(report, cfg)
    for problem in problems:
        print(f"  ✗ {problem}")
    if not problems:
        print("  ✓ compatible with eips on the Kindle 4")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="k4weather")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="fetch the data and render the PNG")
    generate.add_argument("--out", default="out/dashboard.png")
    generate.add_argument("--save-fixture", help="also write the raw response to this file")
    generate.set_defaults(func=cmd_generate)

    preview = subparsers.add_parser("preview", help="render the PNG from a local fixture")
    preview.add_argument("--fixture", default=str(FIXTURES / "forecast_caoria.json"))
    preview.add_argument("--out", default="out/dashboard.png")
    preview.set_defaults(func=cmd_preview)

    inspect = subparsers.add_parser("inspect", help="check an already generated PNG")
    inspect.add_argument("image")
    inspect.set_defaults(func=cmd_inspect)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
