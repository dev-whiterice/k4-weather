"""Conversion to the PNG `eips` accepts, and the checks guarding publication."""

from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from k4weather.postprocess import (
    ImageReport,
    _gray_levels,
    _quantization_table,
    inspect,
    to_eink_png,
    validate,
)


def _write_gradient(path, size, mode="RGB"):
    """A left-to-right gradient covering the whole 0-255 range."""
    image = Image.new(mode, size)
    width, height = size
    pixels = image.load()
    for x in range(width):
        value = int(x / max(width - 1, 1) * 255)
        for y in range(height):
            pixels[x, y] = (value, value, value) if mode == "RGB" else value
    image.save(path)
    return path


def test_quantization_table_produces_the_expected_levels():
    table = _quantization_table(16)
    assert len(set(table)) == 16
    assert min(table) == 0 and max(table) == 255


def test_gray_levels_counts_distinct_values_including_black():
    # Regression: getcolors() returns (count, value) pairs, and reading them
    # the other way round used to drop pure black from the tally.
    image = Image.new("L", (4, 1))
    image.putdata([0, 0, 128, 255])
    assert _gray_levels(image) == 3


@pytest.mark.parametrize("levels", [2, 4, 16])
def test_conversion_respects_the_level_budget(tmp_path, cfg, levels):
    source = _write_gradient(tmp_path / "src.png", (600, 800))
    config = replace(cfg, display=replace(cfg.display, gray_levels=levels))

    report = to_eink_png(source, tmp_path / "out.png", config)

    assert report.mode == "L"
    assert report.levels == levels
    assert validate(report, config) == []


def test_rgb_image_becomes_gray_and_correctly_sized(tmp_path, cfg):
    # eips skews RGB images: the conversion must always be forced.
    source = _write_gradient(tmp_path / "src.png", (1200, 1600))
    report = to_eink_png(source, tmp_path / "out.png", cfg)

    assert (report.width, report.height) == (cfg.display.width, cfg.display.height)
    assert report.mode == "L"


def test_validate_reports_every_problem(cfg):
    problems = validate(
        ImageReport(path=Path("x.png"), width=800, height=600,
                    mode="RGB", levels=200, size_bytes=1),
        cfg,
    )
    assert len(problems) == 3


def test_inspect_reads_a_real_png(tmp_path, cfg):
    source = _write_gradient(tmp_path / "src.png", (600, 800), mode="L")
    to_eink_png(source, tmp_path / "out.png", cfg)
    report = inspect(tmp_path / "out.png")
    assert report.width == 600 and report.height == 800
    assert "600x800" in report.describe()
