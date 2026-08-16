"""Adattamento del PNG al pannello e-ink del Kindle 4.

`eips` vuole un PNG in scala di grigi senza canale alpha: passargli un RGB fa
uscire l'immagine deformata. Qui normalizziamo dimensioni, spazio colore e
numero di livelli, e verifichiamo il risultato prima della pubblicazione.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .config import Config


@dataclass(frozen=True)
class ImageReport:
    path: Path
    width: int
    height: int
    mode: str
    levels: int
    size_bytes: int

    def describe(self) -> str:
        return (
            f"{self.path.name}: {self.width}x{self.height} "
            f"mode={self.mode} livelli={self.levels} "
            f"peso={self.size_bytes / 1024:.1f} kB"
        )


def _quantization_table(levels: int) -> list[int]:
    """LUT che schiaccia 0-255 sui `levels` grigi equispaziati del pannello."""
    step = 255 / (levels - 1)
    return [int(round(round(value / step) * step)) for value in range(256)]


def to_eink_png(source: Path, output: Path, cfg: Config) -> ImageReport:
    width, height = cfg.display.width, cfg.display.height
    output.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source) as raw:
        image = raw.convert("L")
        if image.size != (width, height):
            image = image.resize((width, height), Image.LANCZOS)
        image = image.point(_quantization_table(cfg.display.gray_levels))
        image.save(output, format="PNG", optimize=True)

    return inspect(output)


def inspect(path: Path) -> ImageReport:
    with Image.open(path) as image:
        levels = len({value for value, count in image.convert("L").getcolors(65536) if count})
        return ImageReport(
            path=path,
            width=image.width,
            height=image.height,
            mode=image.mode,
            levels=levels,
            size_bytes=path.stat().st_size,
        )


def validate(report: ImageReport, cfg: Config) -> list[str]:
    """Controlli che devono passare prima di pubblicare l'immagine."""
    problems = []
    if (report.width, report.height) != (cfg.display.width, cfg.display.height):
        problems.append(
            f"dimensioni {report.width}x{report.height}, attese "
            f"{cfg.display.width}x{cfg.display.height}"
        )
    if report.mode != "L":
        problems.append(f"mode {report.mode}, atteso L (grigio 8 bit senza alpha)")
    if report.levels > cfg.display.gray_levels:
        problems.append(f"{report.levels} livelli di grigio, massimo {cfg.display.gray_levels}")
    return problems
