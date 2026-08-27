#!/usr/bin/env sh
# Draws an image with eips, then stamps on top of it the one number that could
# not travel inside it. Goes to /mnt/us/dashboard/local/draw.sh on the Kindle.
#
# kindle-dash calls /usr/sbin/eips directly and offers no hook that runs after
# the screen is up, so install.sh rewrites those call sites to point here. The
# arguments are passed through untouched: this is a drop-in for eips itself,
# and with INDOOR_TEMP=false it is exactly that and nothing more.
#
# The image is always drawn by eips. The number on top of it is drawn by
# whichever of three things this device turns out to have, tried in order of
# how much it looks like the rest of the page:
#
#   1. fbink with the page's own font. `fonts/indoor.ttf` is Inter SemiBold,
#      subset to the eleven characters a temperature can use and with the
#      page's OpenType features already frozen into it — fbink renders through
#      stb_truetype and applies no features of its own. The reading then looks
#      like the max, the min and the apparent temperature beside it, because it
#      is the same typeface at the same size.
#   2. fbink with its own bitmap face, scaled to the same box. Legible, and
#      visibly a different program's work.
#   3. eips, which has exactly one size, 12x20 px per character. Small.
#
# Each step falls through to the next only if it fails, so an installation
# missing the font still draws, and one missing fbink altogether still draws.
# All three write into the same box — INDOOR_TEMP_X/Y and the size derived from
# INDOOR_TEMP_SCALE/CHARS — which is the hole `model.py` leaves in the image.

DIR="$(dirname "$0")"
EIPS=${EIPS:-/usr/sbin/eips}
FBINK=${INDOOR_TEMP_FBINK:-$DIR/../fbink}
TTF=${INDOOR_TEMP_TTF:-$DIR/../fonts/indoor.ttf}

"$EIPS" "$@"
status=$?

# The sleeping screen has no slot to write into.
case " $* " in
  *sleeping.png*) exit "$status" ;;
esac

[ "${INDOOR_TEMP:-true}" = true ] || exit "$status"
# A failed draw leaves the previous image on screen, value included: writing a
# fresh number over a stale dashboard would be the one misleading combination.
[ "$status" -eq 0 ] || exit "$status"

# No reading, no drawing: the dash the image carries stays, and says so.
value=$("$DIR/indoor-temp.sh") || exit "$status"

# The blank left in the image, in pixels, and the multiplier fbink applies to
# its 8x16 bitmap font. Must match INDOOR_SLOT_X/Y, INDOOR_SCALE and
# INDOOR_SLOT_CHARS in src/k4weather/model.py.
x=${INDOOR_TEMP_X:-468}
y=${INDOOR_TEMP_Y:-134}
scale=${INDOOR_TEMP_SCALE:-2}
chars=${INDOOR_TEMP_CHARS:-3}

box_w=$((8 * scale * chars))
box_h=$((16 * scale))

# The panel, so the right and bottom margins can be worked out from the left
# and top ones: fbink takes margins, not coordinates.
screen_w=${INDOOR_TEMP_SCREEN_W:-600}
screen_h=${INDOOR_TEMP_SCREEN_H:-800}

# ------------------------------------------------------------ 1. the real font
#
# `px` is fbink's rendering size in pixels, and it is NOT the CSS one: fbink
# scales the font so that ascent-to-descent measures px, while a browser scales
# the em square. Inter's ascent-to-descent is 1.21 em, so the page's 25px comes
# out as px=30 here. `tools/indoor_font.py` prints the conversion, and
# `tests/test_kindle.py` checks this number against the stylesheet.
px=${INDOOR_TEMP_PX:-30}

if [ -x "$FBINK" ] && [ -f "$TTF" ]; then
  # Padded to the width of the box, exactly as the bitmap branch below does,
  # and for the same two reasons — which hold here only because the font was
  # built for it. Every character in indoor.ttf advances the same width, the
  # blank included, so three of them fill the slot and a two-digit reading ends
  # where a three-digit one does. And fbink paints a background behind what it
  # draws: a string that fills the box therefore covers the dash the image
  # carries, which is what shows when the sensor cannot be read. A string
  # narrower than the box would leave that dash struck through the digits.
  padded=$(printf "%${chars}s" "$value")
  if [ ${#padded} -eq "$chars" ]; then
    right=$(( screen_w - x - box_w ))
    [ "$right" -lt 0 ] && right=0
    bottom=$(( screen_h - y - box_h ))
    [ "$bottom" -lt 0 ] && bottom=0

    # Margins, not coordinates: that is fbink's interface for -t. They bound
    # the drawing area to the slot, so nothing can spill over the rule beside
    # it however wide the reading turns out to be. `padding=BOTH` fills that
    # area with the background before drawing, which is the belt to the padded
    # string's braces.
    #
    # `--` because a temperature below zero starts with a dash and would
    # otherwise be read as an option of fbink's own.
    if "$FBINK" -q -t \
        "regular=$TTF,px=$px,top=$y,bottom=$bottom,left=$x,right=$right,padding=BOTH" \
        -- "$padded" 2>/dev/null; then
      exit "$status"
    fi
  fi
fi

# --------------------------------------------------------- 2. the bitmap face
#
# Right-aligned in its slot by padding rather than by moving: the bitmap font
# is fixed-width, so two and three digit readings then end in the same place,
# and the blanks repaint the cells the previous value used. A reading too wide
# for the slot is dropped instead of being allowed to run over the rule next to
# it.
if [ -x "$FBINK" ]; then
  padded=$(printf "%${chars}s" "$value")
  if [ ${#padded} -eq "$chars" ]; then
    # -x/-y are columns and rows; -X/-Y move the result by whole pixels, which
    # is the only way to land on a hole measured in them.
    if "$FBINK" -q -F IBM -S "$scale" -x 0 -y 0 -X "$x" -Y "$y" -- "$padded" 2>/dev/null; then
      exit "$status"
    fi
  fi
fi

# ---------------------------------------------------------------- 3. and eips
#
# Same blank, its own 12x20 px grid. The cell coordinates are derived from the
# pixel ones rather than configured beside them, so the slot has a single place
# to be moved from — the value ends up right-aligned in the box and centred
# across its height, smaller than the hole but never wider.
# `model.indoor_eips_cells()` is the same arithmetic, and tests/test_kindle.py
# checks the two agree.
ecols=$((box_w / 12))
ecol=$(((x + box_w - ecols * 12) / 12))
erow=$(((y + (box_h - 20) / 2 + 10) / 20))

# Padded to the full width of the box: that leading blank is also what stops
# eips from reading a temperature below zero as an option of its own.
padded=$(printf "%${ecols}s" "$value")
[ ${#padded} -eq "$ecols" ] || exit "$status"

"$EIPS" "$ecol" "$erow" "$padded"
exit "$status"
