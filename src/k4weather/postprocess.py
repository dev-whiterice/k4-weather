"""Adapting the PNG to the e-ink panel of the Kindle 4.

`eips` wants a grayscale PNG with no alpha channel: handing it an RGB file
produces a skewed image on screen. Here we normalise size, colour space and
number of levels, and check the result before it is published.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .config import Config

# An 8-bit grayscale image can hold at most 256 distinct values, which is also
# the ceiling `Image.getcolors` needs in order not to give up and return None.
MAX_GRAY_VALUES = 256


@dataclass(frozen=True)
class ImageReport:
    """What we measured on a PNG, as printed by `k4weather inspect`."""

    path: Path
    width: int
    height: int
    mode: str
    levels: int
    size_bytes: int

    def describe(self) -> str:
        return (
            f"{self.path.name}: {self.width}x{self.height} "
            f"mode={self.mode} levels={self.levels} "
            f"size={self.size_bytes / 1024:.1f} kB"
        )


def _quantization_table(levels: int) -> list[int]:
    """LUT collapsing 0-255 onto the `levels` evenly spaced grays of the panel."""
    step = 255 / (levels - 1)
    return [int(round(round(value / step) * step)) for value in range(256)]


def to_eink_png(source: Path, output: Path, cfg: Config) -> ImageReport:
    """Convert a rendered screenshot into the exact PNG `eips` expects."""
    width, height = cfg.display.width, cfg.display.height
    output.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source) as raw:
        # "L" drops both colour and alpha, the two things eips cannot handle.
        image = raw.convert("L")
        if image.size != (width, height):
            # Downscaling a supersampled screenshot; LANCZOS keeps hairlines
            # from dissolving into the background.
            image = image.resize((width, height), Image.LANCZOS)
        image = image.point(_quantization_table(cfg.display.gray_levels))
        image.save(output, format="PNG", optimize=True)

    return inspect(output)


def _gray_levels(image: Image.Image) -> int:
    """Number of distinct gray values actually used by the image.

    `getcolors` yields `(count, value)` pairs — that order is easy to get
    backwards — and only lists values that occur at least once, so the length
    of the list is the answer.
    """
    colors = image.convert("L").getcolors(MAX_GRAY_VALUES)
    return len(colors) if colors else MAX_GRAY_VALUES


def inspect(path: Path) -> ImageReport:
    """Measure a PNG on disk without modifying it."""
    with Image.open(path) as image:
        return ImageReport(
            path=path,
            width=image.width,
            height=image.height,
            mode=image.mode,
            levels=_gray_levels(image),
            size_bytes=path.stat().st_size,
        )


def validate(report: ImageReport, cfg: Config) -> list[str]:
    """Checks that must pass before the image is published; empty list means OK."""
    problems = []
    if (report.width, report.height) != (cfg.display.width, cfg.display.height):
        problems.append(
            f"size is {report.width}x{report.height}, expected "
            f"{cfg.display.width}x{cfg.display.height}"
        )
    if report.mode != "L":
        problems.append(f"mode is {report.mode}, expected L (8-bit gray, no alpha)")
    if report.levels > cfg.display.gray_levels:
        problems.append(f"{report.levels} gray levels, at most {cfg.display.gray_levels}")
    return problems
