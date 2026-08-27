"""Builds the font the Kindle draws the indoor temperature with.

The room's temperature is the one number this project cannot render in the
image: the sensor is on the device and the image is built in the cloud. The
Kindle writes it on top, and for it to look like the figures beside it — the
max, the min and the apparent temperature, which are Inter SemiBold 26px — it
has to draw with the same font.

That cannot be the woff2 the page uses, for two reasons:

  * `fbink` renders through stb_truetype, which reads glyph outlines and
    nothing else. It applies no OpenType features. The page asks for
    `font-feature-settings: "tnum" 1, "cv05" 1`, so its digits are the tabular,
    disambiguated variants — different glyphs from the ones a plain cmap lookup
    returns, and different widths: Inter's proportional `1` is 0.42 em against
    `4` at 0.67 em, while the tabular set is uniform. Rendered naively the
    digits would be the wrong shapes AND would jitter from one refresh to the
    next.
  * fbink reads TTF and OTF, not woff2.

So the features are frozen here instead: the substitutions those two features
would perform are applied to the character map directly, so that a plain lookup
of "7" already lands on the glyph the page would have used. What comes out is
then subset to the eleven characters the device can actually draw — ten digits,
a minus sign and a space — which takes a 300 KB font down to a couple of
kilobytes on a FAT partition that has to be read by a 2011 e-reader.

    make indoor-font        # regenerates kindle/fonts/indoor.ttf

The result is committed, because install.sh has to be able to copy it without a
Python environment. Rerun this when the page's font or its feature settings
change — `tests/test_kindle.py` checks the two sides still agree.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "k4weather" / "templates" / "fonts" / "Inter-SemiBold.woff2"
TARGET = ROOT / "kindle" / "fonts" / "indoor.ttf"

# Exactly what local/indoor-temp.sh can produce: whole degrees between
# INDOOR_TEMP_MIN and INDOOR_TEMP_MAX, right-aligned with leading blanks.
CHARACTERS = "0123456789- "

# The features the page turns on. Kept as a tuple rather than inlined so that
# the one place to change them is next to the comment explaining why.
FEATURES = ("tnum", "cv05")


def single_substitutions(font: TTFont, features: tuple[str, ...]) -> dict[str, str]:
    """The glyph-for-glyph swaps `features` would make, flattened into a map."""
    gsub = font["GSUB"].table
    wanted = set(features)

    lookup_indices: set[int] = set()
    for record in gsub.FeatureList.FeatureRecord:
        if record.FeatureTag in wanted:
            lookup_indices.update(record.Feature.LookupListIndex)

    mapping: dict[str, str] = {}
    for index in sorted(lookup_indices):
        lookup = gsub.LookupList.Lookup[index]
        # Type 1 is a straight one-for-one swap, which is all these two
        # features do. Anything else would need shaping, and shaping is exactly
        # what the device cannot do.
        if lookup.LookupType != 1:
            continue
        for table in lookup.SubTable:
            mapping.update(table.mapping)
    return mapping


def resolve(glyph: str, mapping: dict[str, str]) -> str:
    """Follow the swaps to a fixed point: `four` -> `four.ss01` -> `four.tf.ss01`.

    Two features can chain, and which order they are stored in is the font's
    business, not ours. Bounded so that a cycle in a future font cannot hang
    the build.
    """
    seen = {glyph}
    for _ in range(len(mapping) + 1):
        nxt = mapping.get(glyph)
        if nxt is None or nxt in seen:
            return glyph
        glyph = nxt
        seen.add(glyph)
    return glyph


def build() -> Path:
    font = TTFont(SOURCE)
    mapping = single_substitutions(font, FEATURES)
    best = font.getBestCmap()

    # What each character must end up drawing.
    resolved = {}
    for character in CHARACTERS:
        source_glyph = best.get(ord(character))
        if source_glyph is None:
            raise SystemExit(f"{SOURCE.name} has no glyph for {character!r}")
        resolved[ord(character)] = resolve(source_glyph, mapping)

    # Rewritten in every cmap subtable, not just the best one: fbink picks a
    # subtable by its own rules, and a font whose tables disagree would render
    # differently there than it does in the checks below.
    for table in font["cmap"].tables:
        for codepoint, glyph in resolved.items():
            if codepoint in table.cmap:
                table.cmap[codepoint] = glyph

    TARGET.parent.mkdir(parents=True, exist_ok=True)

    options = subset.Options()
    # GSUB goes with it. The substitutions are in the cmap now, and leaving the
    # features behind would let a shaper apply them a second time.
    options.layout_features = []
    options.drop_tables += ["GSUB", "GPOS", "GDEF"]
    options.name_IDs = ["*"]
    options.notdef_outline = True
    options.recalc_bounds = True

    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=[ord(c) for c in CHARACTERS])
    subsetter.subset(font)

    # The space is widened to a digit, which is the whole alignment strategy.
    #
    # The device right-aligns the reading by padding it with blanks — " 21",
    # " -5", "-10" — and that only lands in the same place every time if a
    # blank is exactly as wide as what it stands in for. Inter's space is
    # 0.269 em against a tabular digit's 0.647.
    #
    # It buys a second thing, and the picture is the argument for it: the image
    # carries a dash in this slot, for the case where the sensor cannot be read,
    # and fbink paints a background only behind what it draws. A padded string
    # that fills the box therefore erases that dash; a string that stops short
    # of it leaves it showing through the digits.
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    digit = hmtx[cmap[ord("0")]][0]
    space_glyph = cmap[ord(" ")]
    hmtx[space_glyph] = (digit, hmtx[space_glyph][1])

    font.flavor = None  # TTF, not woff2: stb_truetype reads no compressed font
    font.save(TARGET)
    return TARGET


def verify(path: Path) -> None:
    """The two properties the device depends on, checked rather than assumed."""
    font = TTFont(path)
    upem = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]

    advances = {c: hmtx[cmap[ord(c)]][0] for c in "0123456789"}
    widths = set(advances.values())
    if len(widths) != 1:
        raise SystemExit(
            "the digits are not tabular after freezing: "
            + ", ".join(f"{c}={w}" for c, w in advances.items())
        )

    digit = widths.pop()
    for character in "- ":
        width = hmtx[cmap[ord(character)]][0]
        if width != digit:
            raise SystemExit(
                f"{character!r} advances {width} against the digits' {digit}: "
                "the reading would not right-align"
            )

    print(f"  {path.relative_to(ROOT)}  {path.stat().st_size} bytes")
    print(f"  unitsPerEm {upem}, every character advances {digit} "
          f"= {digit / upem:.4f} em")


if __name__ == "__main__":
    verify(build())
    sys.exit(0)
