"""Interfaccia a riga di comando.

    python -m k4weather generate            # dati live -> out/dashboard.png
    python -m k4weather preview             # dati da fixture, nessuna rete
    python -m k4weather inspect out/dashboard.png
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
    dashboard = build_dashboard(forecast, air_quality, cfg, now=now)
    html = render.build_html(dashboard, cfg)

    out_html = out_png.with_suffix(".html")
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")
    log.info("HTML di anteprima: %s", out_html)

    raw_png = out_png.with_name(out_png.stem + ".raw.png")
    render.html_to_png(html, raw_png, cfg)
    report = postprocess.to_eink_png(raw_png, out_png, cfg)
    raw_png.unlink(missing_ok=True)

    problems = postprocess.validate(report, cfg)
    log.info(report.describe())
    for problem in problems:
        log.error("immagine non valida: %s", problem)
    return 1 if problems else 0


def cmd_generate(args) -> int:
    cfg = load_config(args.config)
    forecast = fetch.fetch_forecast(cfg)
    air_quality = fetch.fetch_air_quality(cfg)
    if args.save_fixture:
        Path(args.save_fixture).write_text(json.dumps(forecast, indent=2), encoding="utf-8")
    return _write_outputs(forecast, air_quality, cfg, Path(args.out))


def cmd_preview(args) -> int:
    cfg = load_config(args.config)
    fixture = Path(args.fixture)
    forecast = json.loads(fixture.read_text(encoding="utf-8"))
    # Alla fixture `forecast_X.json` corrisponde `air_quality_X.json`, se c'e'.
    air_path = fixture.with_name(fixture.name.replace("forecast_", "air_quality_", 1))
    air_quality = (
        json.loads(air_path.read_text(encoding="utf-8")) if air_path.exists() else None
    )
    # Ancoriamo "adesso" alla fixture, cosi' l'anteprima e' riproducibile.
    now = datetime.fromisoformat(forecast["current"]["time"])
    return _write_outputs(forecast, air_quality, cfg, Path(args.out), now=now)


def cmd_inspect(args) -> int:
    cfg = load_config(args.config)
    report = postprocess.inspect(Path(args.image))
    print(report.describe())
    problems = postprocess.validate(report, cfg)
    for problem in problems:
        print(f"  ✗ {problem}")
    if not problems:
        print("  ✓ compatibile con eips sul Kindle 4")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="k4weather")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="scarica i dati e genera il PNG")
    generate.add_argument("--out", default="out/dashboard.png")
    generate.add_argument("--save-fixture", help="salva la risposta grezza su file")
    generate.set_defaults(func=cmd_generate)

    preview = subparsers.add_parser("preview", help="genera il PNG da una fixture locale")
    preview.add_argument("--fixture", default=str(FIXTURES / "forecast_caoria.json"))
    preview.add_argument("--out", default="out/dashboard.png")
    preview.set_defaults(func=cmd_preview)

    inspect = subparsers.add_parser("inspect", help="verifica un PNG gia' generato")
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
