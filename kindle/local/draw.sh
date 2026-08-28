#!/usr/bin/env sh
# Draws an image with eips, then stamps on top of it the two numbers that could
# not travel inside it. Goes to /mnt/us/dashboard/local/draw.sh on the Kindle.
#
# kindle-dash calls /usr/sbin/eips directly and offers no hook that runs after
# the screen is up, so install.sh rewrites those call sites to point here. The
# arguments are passed through untouched: this is a drop-in for eips itself,
# and with INDOOR_TEMP=false and BATTERY=false it is exactly that and nothing
# more.
#
# The two numbers are the temperature of the room and the level of the battery
# the panel runs on. Both are read here and the image is built in the cloud, so
# `model.py` leaves each of them a blank of an exact size in an exact place and
# this fills them in. The image itself is always drawn by eips.
#
# What fills a blank is whichever of three things this device turns out to
# have, tried in order of how much it looks like the rest of the page:
#
#   1. fbink with the page's own font. `fonts/indoor.ttf` is Inter SemiBold,
#      subset to the eleven characters these two readings can use and with the
#      page's OpenType features already frozen into it — fbink renders through
#      stb_truetype and applies no features of its own. The values then look
#      like the figures printed beside them, because they are the same typeface
#      at the same size.
#   2. fbink with its own bitmap face, scaled to the same box. Legible, and
#      visibly a different program's work.
#   3. eips, which has exactly one size, 12x20 px per character. Small.
#
# Each step falls through to the next only if it fails, so an installation
# missing the font still draws, and one missing fbink altogether still draws
# the temperature.
#
# The third step is offered to the temperature alone. eips' cells are taller
# than the type of the footer the battery level sits in, so there it would be
# the largest thing in the bar — a footnote shouting. The temperature is 25px
# of Inter and can afford to come out small; the battery level cannot afford to
# come out big, and without fbink the dash the image carries simply stays.

DIR="$(dirname "$0")"
EIPS=${EIPS:-/usr/sbin/eips}
# One binary and one font serve both blanks, which is why the two keep the
# names they were given when the temperature was the only thing drawn here.
FBINK=${INDOOR_TEMP_FBINK:-$DIR/../fbink}
TTF=${INDOOR_TEMP_TTF:-$DIR/../fonts/indoor.ttf}

# The panel, so the right and bottom margins can be worked out from the left
# and top ones: fbink takes margins, not coordinates.
SCREEN_W=${INDOOR_TEMP_SCREEN_W:-600}
SCREEN_H=${INDOOR_TEMP_SCREEN_H:-800}

# ------------------------------------------------------------------ stamping
#
# Both blanks are described the same way: their top left corner in pixels of
# the image, how many characters wide they are, and the multiplier fbink
# applies to its 8x16 bitmap font. Every name below is prefixed, because a
# shell function has no scope of its own and these are handed the coordinates
# the caller is holding.

# stamp_fbink VALUE X Y CHARS SCALE PX — steps 1 and 2. Returns 0 if it drew.
stamp_fbink() {
  s_value=$1
  s_x=$2
  s_y=$3
  s_chars=$4
  s_scale=$5
  s_px=$6

  [ -x "$FBINK" ] || return 1

  # Padded to the width of the box, which is what right-aligns the value, and
  # it holds for both steps below. Every character of indoor.ttf advances the
  # same width, the blank included — the font was built for this — and so does
  # every character of a bitmap face. Two digits therefore end where three do.
  # And fbink paints a background behind what it draws: a string that fills the
  # box covers the dash the image carries for a reading that could not be
  # taken, where a shorter one would leave that dash struck through the digits.
  # A value too wide for the box is dropped rather than allowed to run over
  # whatever is beside it.
  s_padded=$(printf "%${s_chars}s" "$s_value")
  [ ${#s_padded} -eq "$s_chars" ] || return 1

  s_w=$((8 * s_scale * s_chars))
  s_h=$((16 * s_scale))

  # --------------------------------------------------------- 1. the real font
  #
  # `px` is fbink's rendering size in pixels, and it is NOT the CSS one: fbink
  # scales the font so that ascent-to-descent measures px, while a browser
  # scales the em square. Inter's ascent-to-descent is 1.21 em, so the page's
  # 25px comes out as px=30 here, and the footer's 12.4px as px=15.
  # `tools/indoor_font.py` prints the conversion.
  if [ -f "$TTF" ]; then
    s_right=$((SCREEN_W - s_x - s_w))
    [ "$s_right" -lt 0 ] && s_right=0
    s_bottom=$((SCREEN_H - s_y - s_h))
    [ "$s_bottom" -lt 0 ] && s_bottom=0

    # Margins, not coordinates: that is fbink's interface for -t. They bound
    # the drawing area to the blank, so nothing can spill over whatever is
    # beside it however wide the reading turns out to be. `padding=BOTH` fills
    # that area with the background before drawing, which is the belt to the
    # padded string's braces.
    #
    # `--` because a temperature below zero starts with a dash and would
    # otherwise be read as an option of fbink's own.
    if "$FBINK" -q -t \
        "regular=$TTF,px=$s_px,top=$s_y,bottom=$s_bottom,left=$s_x,right=$s_right,padding=BOTH" \
        -- "$s_padded" 2>/dev/null; then
      return 0
    fi
  fi

  # ------------------------------------------------------- 2. the bitmap face
  #
  # -x/-y are columns and rows; -X/-Y move the result by whole pixels, which is
  # the only way to land on a blank measured in them.
  "$FBINK" -q -F IBM -S "$s_scale" -x 0 -y 0 -X "$s_x" -Y "$s_y" -- "$s_padded" 2>/dev/null
}

# stamp_eips VALUE X Y CHARS SCALE — step 3, and the temperature's alone.
#
# Same blank, its own 12x20 px grid. The cell coordinates are derived from the
# pixel ones rather than configured beside them, so the blank has a single
# place to be moved from — the value ends up right-aligned in the box and
# centred across its height, smaller than the hole but never wider.
# `model.indoor_eips_cells()` is the same arithmetic, and tests/test_kindle.py
# checks the two agree.
stamp_eips() {
  e_value=$1
  e_x=$2
  e_y=$3
  e_chars=$4
  e_scale=$5

  e_w=$((8 * e_scale * e_chars))
  e_h=$((16 * e_scale))

  e_cols=$((e_w / 12))
  e_col=$(((e_x + e_w - e_cols * 12) / 12))
  e_row=$(((e_y + (e_h - 20) / 2 + 10) / 20))

  # Padded to the full width of the box: that leading blank is also what stops
  # eips from reading a temperature below zero as an option of its own.
  e_padded=$(printf "%${e_cols}s" "$e_value")
  [ ${#e_padded} -eq "$e_cols" ] || return 1

  "$EIPS" "$e_col" "$e_row" "$e_padded"
}

# --------------------------------------------------------------- the drawing

"$EIPS" "$@"
status=$?

# The sleeping screen has no blanks to write into.
case " $* " in
  *sleeping.png*) exit "$status" ;;
esac

# A failed draw leaves the previous image on screen, values included: writing
# fresh numbers over a stale dashboard would be the one misleading combination.
[ "$status" -eq 0 ] || exit "$status"

# The room's temperature. No reading, no drawing: the dash the image carries
# stays, and says so.
if [ "${INDOOR_TEMP:-true}" = true ] && value=$("$DIR/indoor-temp.sh"); then
  # Must match INDOOR_SLOT_X/Y, INDOOR_SLOT_CHARS and INDOOR_SCALE in
  # src/k4weather/model.py.
  x=${INDOOR_TEMP_X:-492}
  y=${INDOOR_TEMP_Y:-134}
  chars=${INDOOR_TEMP_CHARS:-3}
  scale=${INDOOR_TEMP_SCALE:-2}
  stamp_fbink "$value" "$x" "$y" "$chars" "$scale" "${INDOOR_TEMP_PX:-30}" ||
    stamp_eips "$value" "$x" "$y" "$chars" "$scale"
fi

# The battery. Same rule for a reading that cannot be taken, and nothing behind
# fbink: see the header.
if [ "${BATTERY:-true}" = true ] && value=$("$DIR/battery.sh"); then
  # Must match BATTERY_SLOT_X/Y, BATTERY_SLOT_CHARS and BATTERY_SCALE in
  # src/k4weather/model.py.
  stamp_fbink "$value" "${BATTERY_X:-542}" "${BATTERY_Y:-769}" \
    "${BATTERY_CHARS:-3}" "${BATTERY_SCALE:-1}" "${BATTERY_PX:-15}"
fi

exit "$status"
