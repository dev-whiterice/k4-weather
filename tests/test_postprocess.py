from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from k4weather.postprocess import ImageReport, _quantization_table, inspect, to_eink_png, validate


def _write_gradient(path, size, mode="RGB"):
    image = Image.new(mode, size)
    width, height = size
    pixels = image.load()
    for x in range(width):
        value = int(x / max(width - 1, 1) * 255)
        for y in range(height):
            pixels[x, y] = (value, value, value) if mode == "RGB" else value
    image.save(path)
    return path


def test_tabella_quantizzazione_produce_i_livelli_attesi():
    table = _quantization_table(16)
    assert len(set(table)) == 16
    assert min(table) == 0 and max(table) == 255


@pytest.mark.parametrize("levels", [2, 4, 16])
def test_conversione_rispetta_il_numero_di_livelli(tmp_path, cfg, levels):
    source = _write_gradient(tmp_path / "src.png", (600, 800))
    config = replace(cfg, display=replace(cfg.display, gray_levels=levels))

    report = to_eink_png(source, tmp_path / "out.png", config)

    assert report.mode == "L"
    assert report.levels <= levels
    assert validate(report, config) == []


def test_immagine_rgb_diventa_grigia_e_della_misura_giusta(tmp_path, cfg):
    # eips deforma le immagini RGB: la conversione deve essere sempre forzata.
    source = _write_gradient(tmp_path / "src.png", (1200, 1600))
    report = to_eink_png(source, tmp_path / "out.png", cfg)

    assert (report.width, report.height) == (cfg.display.width, cfg.display.height)
    assert report.mode == "L"


def test_validate_segnala_i_problemi(cfg):
    problems = validate(
        ImageReport(path=Path("x.png"), width=800, height=600,
                    mode="RGB", levels=200, size_bytes=1),
        cfg,
    )
    assert len(problems) == 3


def test_inspect_legge_un_png_reale(tmp_path, cfg):
    source = _write_gradient(tmp_path / "src.png", (600, 800), mode="L")
    to_eink_png(source, tmp_path / "out.png", cfg)
    report = inspect(tmp_path / "out.png")
    assert report.width == 600 and report.height == 800
    assert "600x800" in report.describe()
