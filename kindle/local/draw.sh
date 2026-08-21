#!/usr/bin/env sh
# Draws an image with eips, then stamps on top of it the one number that could
# not travel inside it. Goes to /mnt/us/dashboard/local/draw.sh on the Kindle.
#
# kindle-dash calls /usr/sbin/eips directly and offers no hook that runs after
# the screen is up, so install.sh rewrites those call sites to point here. The
# arguments are passed through untouched: this is a drop-in for eips itself,
# and with INDOOR_TEMP=false it is exactly that and nothing more.
#
# The image is always drawn by eips. The number on top of it is drawn by fbink
# where fbink is installed, because eips has one font size and it is too small
# to read a room temperature from across the room; where it is not, eips draws
# it as before, smaller, in the middle of the same blank.

DIR="$(dirname "$0")"
EIPS=${EIPS:-/usr/sbin/eips}
FBINK=${INDOOR_TEMP_FBINK:-$DIR/../fbink}

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
y=${INDOOR_TEMP_Y:-118}
scale=${INDOOR_TEMP_SCALE:-4}
chars=${INDOOR_TEMP_CHARS:-3}

if [ -x "$FBINK" ]; then
  # Right-aligned in its slot by padding rather than by moving: two and three
  # digit readings then end in the same place, hard against the degree sign the
  # image already carries, and the blanks repaint the cells the previous value
  # used. A reading too wide for the slot is dropped instead of being allowed to
  # run over the rule next to it.
  padded=$(printf "%${chars}s" "$value")
  [ ${#padded} -eq "$chars" ] || exit "$status"

  # -x/-y are columns and rows; -X/-Y move the result by whole pixels, which is
  # the only way to land on a hole measured in them. `--` because a temperature
  # below zero starts with a dash and would otherwise be read as an option. If
  # a future fbink renames these flags, this is the line to fix.
  "$FBINK" -q -F IBM -S "$scale" -x 0 -y 0 -X "$x" -Y "$y" -- "$padded"
  exit "$status"
fi

# Without fbink, eips: same blank, its own 12x20 px grid. The cell coordinates
# are derived from the pixel ones rather than configured beside them, so the
# slot has a single place to be moved from — the value ends up right-aligned in
# the box and centred across its height, smaller than the hole but never wider.
# `model.indoor_eips_cells()` is the same arithmetic, and tests/test_kindle.py
# checks the two agree.
box_w=$((8 * scale * chars))
box_h=$((16 * scale))
ecols=$((box_w / 12))
ecol=$(((x + box_w - ecols * 12) / 12))
erow=$(((y + (box_h - 20) / 2 + 10) / 20))

# Padded to the full width of the box: that leading blank is also what stops
# eips from reading a temperature below zero as an option of its own.
padded=$(printf "%${ecols}s" "$value")
[ ${#padded} -eq "$ecols" ] || exit "$status"

"$EIPS" "$ecol" "$erow" "$padded"
exit "$status"
