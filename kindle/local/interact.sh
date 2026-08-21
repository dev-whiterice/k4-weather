#!/usr/bin/env sh
# Listens to the page buttons for a while, and moves between locations.
# Goes to /mnt/us/dashboard/local/interact.sh on the Kindle.
#
#     interact.sh <seconds> [--flash]
#
# It replaces the plain `sleep` kindle-dash does before suspending, and is also
# what runs when the device is woken up by hand. With INTERACT=false it *is*
# that plain sleep, so turning the feature off gives the upstream behaviour
# back, ten-second abort window included.
#
# Why the buttons are only read here, and never while the panel sleeps: the
# keypad on a Kindle 4 is not a wakeup source — `power/wakeup` for
# `tequila-keypad` reads empty, meaning the driver never registered it as one,
# and no amount of writing to it changes that. The power slider wakes the
# device below the evdev layer; the buttons are perfectly readable a moment
# later, with the framework down. Hence: power to wake, page buttons to choose.
# `kindle/tools/keytest.sh` is what measured all of that.

DIR=$(dirname "$0")
DASH_DIR=${DASH_DIR:-$(cd "$DIR/.." && pwd)}
# shellcheck disable=SC1091
. "$DIR/locations.sh"

SECONDS_TO_LISTEN=${1:-10}
FLASH=false
[ "${2:-}" = "--flash" ] && FLASH=true

# Off: behave exactly like the `sleep` this replaced. Not a no-op — that window
# is the only chance to interrupt the loop by hand before it suspends.
if [ "${INTERACT:-true}" != true ]; then
  sleep "$SECONDS_TO_LISTEN"
  exit 0
fi

KEY_DEVICE=${KEY_DEVICE:-/dev/input/event0}
KEY_NEXT=${KEY_NEXT:-"191 104"}
KEY_PREV=${KEY_PREV:-"109 193"}
INTERACT_EXTEND=${INTERACT_EXTEND:-15}
CAPTURE=${CAPTURE:-/tmp/k4weather-keys.bin}

EVENT_SIZE=16       # struct input_event on this 32-bit kernel
OFF_TYPE=8          # only the low byte of each field is read: key types,
OFF_CODE=10         # key codes and press/release values all fit in one, and
OFF_VALUE=12        # reading the high halves would double the `dd` calls

# --------------------------------------------------------- reading the keypad
#
# This device has no od, no hexdump and no xxd, so a byte becomes a number by
# looking up its position in a string holding every byte from 1 to 255. Three
# `dd` calls per event: slow in principle, invisible in practice, since a
# button press is four events and nothing else ever arrives.

BYTES=""
init_bytes() {
  [ -n "$BYTES" ] && return
  _fmt=""
  _i=1
  while [ "$_i" -le 255 ]; do
    # \ooo, three octal digits: the form POSIX specifies for the printf format
    # operand. The \0ooo spelling is NOT equivalent — bash counts the leading
    # zero as one of the three digits and silently truncates.
    _fmt="$_fmt\\$((_i / 64))$((_i / 8 % 8))$((_i % 8))"
    _i=$((_i + 1))
  done
  BYTES=$(printf "$_fmt")
}

byte_at() {  # file, offset -> decimal value of that byte
  # The X is a sentinel: command substitution strips trailing newlines, and
  # without it byte 0x0A would come back indistinguishable from a NUL.
  b=$(dd if="$1" bs=1 skip="$2" count=1 2>/dev/null; printf X)
  b=${b%X}
  if [ -z "$b" ]; then
    echo 0        # a NUL cannot survive a shell variable, and reads as empty
    return
  fi
  rest=${BYTES%%"$b"*}
  echo $((${#rest} + 1))
}

records_in() {  # how many whole events the capture holds so far
  size=$(wc -c < "$1" 2>/dev/null | tr -d ' ')
  [ -n "$size" ] || size=0
  echo $((size / EVENT_SIZE))
}

# The code of event number `$2` of file `$1`, but only if it is a key being
# pressed down. Releases and auto-repeats print nothing: one press must move
# one location, and holding a button down must not run through the whole list.
press_code() {
  base=$(( $2 * EVENT_SIZE ))
  [ "$(byte_at "$1" $((base + OFF_TYPE)))" = 1 ] || return 1
  [ "$(byte_at "$1" $((base + OFF_VALUE)))" = 1 ] || return 1
  byte_at "$1" $((base + OFF_CODE))
}

# Is code $1 one of the space-separated codes in $2? Called for its exit status
# and so not in a subshell, which is why its variables are prefixed: a loop
# variable called `code` here would overwrite the caller's `code` between the
# test for "next" and the test for "previous", and the second one would then be
# comparing the wrong number.
in_list() {
  _want=$1
  for _key in $2; do
    [ "$_key" = "$_want" ] && return 0
  done
  return 1
}

# ------------------------------------------------------------------ the loop

init_bytes
rm -f "$CAPTURE"
: > "$CAPTURE"

# One reader, open for the whole window. Polling `dd` per press would leave
# gaps between the polls, and a press that lands in a gap is a button that did
# not work — the one failure a wall panel must not have.
dd if="$KEY_DEVICE" of="$CAPTURE" bs="$EVENT_SIZE" 2>/dev/null &
reader=$!
# The reader is killed on every exit path: leaving it holding the input device
# across a suspend would keep a `dd` alive for as long as the panel runs.
trap 'kill "$reader" 2>/dev/null' EXIT INT TERM

current=$(loc_current) || current=""

# A full refresh on arrival says "awake and listening" without drawing any
# chrome that would then have to be cleaned off the image. Only after a wake by
# hand: a scheduled refresh has just painted the screen anyway.
if [ "$FLASH" = true ] && [ -n "$current" ] && [ "${INTERACT_FLASH:-true}" = true ]; then
  loc_draw "$current"
fi

seen=0
deadline=$(( $(date +%s) + SECONDS_TO_LISTEN ))

# kindle-dash's stop.sh is `pkill -f dash.sh`, which reaches the loop and not
# this child of it. Without the check below, stopping the panel during the
# listening window would leave one of these counting down on its own, holding
# the input device — and redrawing the screen behind the framework that was
# just brought back.
parent=$PPID

while [ "$(date +%s)" -lt "$deadline" ]; do
  sleep 1
  kill -0 "$parent" 2>/dev/null || break

  total=$(records_in "$CAPTURE")
  while [ "$seen" -lt "$total" ]; do
    code=$(press_code "$CAPTURE" "$seen")
    seen=$((seen + 1))
    [ -n "$code" ] || continue

    if in_list "$code" "$KEY_NEXT"; then
      step=1
    elif in_list "$code" "$KEY_PREV"; then
      step=-1
    else
      continue    # every other button on the device is not ours to answer
    fi

    [ -n "$current" ] || current=$(loc_current) || continue
    target=$(loc_step "$current" "$step") || continue
    [ "$target" = "$current" ] && continue

    if loc_go "$target"; then
      current=$target
      # Each press buys more time: walking five locations must not need five
      # presses inside the same shrinking window.
      deadline=$(( $(date +%s) + INTERACT_EXTEND ))
    fi
  done
done

exit 0
