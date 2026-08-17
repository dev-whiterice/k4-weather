#!/usr/bin/env sh
# Draws an image with eips, then stamps on top of it the one number that could
# not travel inside it. Goes to /mnt/us/dashboard/local/draw.sh on the Kindle.
#
# kindle-dash calls /usr/sbin/eips directly and offers no hook that runs after
# the screen is up, so install.sh rewrites those call sites to point here. The
# arguments are passed through untouched: this is a drop-in for eips itself,
# and with INDOOR_TEMP=false it is exactly that and nothing more.

DIR="$(dirname "$0")"
EIPS=${EIPS:-/usr/sbin/eips}

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

col=${INDOOR_TEMP_COL:-42}
row=${INDOOR_TEMP_ROW:-7}
chars=${INDOOR_TEMP_CHARS:-4}

# Right-aligned in its slot, hard against the degree sign the image already
# carries, and padded to its full width rather than moved: the blank in front
# is what stops eips from reading a temperature below zero as an option of its
# own. A reading too wide for the slot is dropped instead of being allowed to
# run over the icon next to it.
padded=$(printf "%${chars}s" "$value")
[ ${#padded} -eq "$chars" ] || exit "$status"

"$EIPS" "$col" "$row" "$padded"
exit "$status"
