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
#
# Everything here says what it did, on stdout, which dash.sh sends to
# logs/dash.log. Not for the sake of a log: a panel whose buttons do nothing is
# indistinguishable from a panel that never listened, and from out here the two
# have completely different causes. The lines below are what tells them apart.

DIR=$(dirname "$0")
DASH_DIR=${DASH_DIR:-$(cd "$DIR/.." && pwd)}
# shellcheck disable=SC1091
. "$DIR/locations.sh"

SECONDS_TO_LISTEN=${1:-10}
FLASH=false
[ "${2:-}" = "--flash" ] && FLASH=true

log() { echo "$(date) interact: $*"; }

# Off: behave exactly like the `sleep` this replaced. Not a no-op — that window
# is the only chance to interrupt the loop by hand before it suspends.
if [ "${INTERACT:-true}" != true ]; then
  log "INTERACT is '${INTERACT:-true}', not 'true': plain ${SECONDS_TO_LISTEN}s sleep"
  sleep "$SECONDS_TO_LISTEN"
  exit 0
fi

# `auto` means every input device the kernel offers, which is what makes this
# survive a device that numbers its keypad differently: the buttons are found
# by listening rather than by being told where to listen. Naming one device
# explicitly still works and is marginally cheaper — see env.sh.
KEY_DEVICE=${KEY_DEVICE:-auto}
KEY_NEXT=${KEY_NEXT:-"191 104"}
KEY_PREV=${KEY_PREV:-"109 193"}
INTERACT_EXTEND=${INTERACT_EXTEND:-15}
CAPTURE=${CAPTURE:-/tmp/k4weather-keys.bin}

# Unread events per device per second above which the backlog is a stream and
# not a person. See the loop below.
MAX_BACKLOG=${MAX_BACKLOG:-200}

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

# ------------------------------------------------------------- the listeners
#
# One reader per device, open for the whole window. Polling `dd` per press
# would leave gaps between the polls, and a press that lands in a gap is a
# button that did not work — the one failure a wall panel must not have.
#
# Several devices rather than one because the alternative failed silently: a
# keypad that is not on the device named in env.sh produces no events, no
# error, and a panel whose buttons do nothing for a reason nobody can see from
# here. Reading them all costs a handful of `dd` processes for the length of
# the window and takes that whole class of fault off the table.

init_bytes

devices=""
if [ "$KEY_DEVICE" = auto ]; then
  for _dev in /dev/input/event*; do
    [ -r "$_dev" ] && devices="$devices $_dev"
  done
else
  for _dev in $KEY_DEVICE; do
    [ -r "$_dev" ] && devices="$devices $_dev"
  done
fi

if [ -z "$devices" ]; then
  # Nothing to listen to. Said out loud rather than waited out in silence:
  # this is the state in which the buttons cannot possibly work, and it is
  # invisible from the device itself.
  log "no readable input device (KEY_DEVICE='$KEY_DEVICE'), waiting ${SECONDS_TO_LISTEN}s"
  sleep "$SECONDS_TO_LISTEN"
  exit 0
fi

readers=""
slots=0
for _dev in $devices; do
  _cap="$CAPTURE.$slots"
  rm -f "$_cap"
  : > "$_cap"
  dd if="$_dev" of="$_cap" bs="$EVENT_SIZE" 2>/dev/null &
  readers="$readers $!"
  # POSIX sh has no arrays, and this needs one entry per device: the capture
  # file and how far it has been decoded. `eval` with a numbered name is the
  # form that works in busybox ash.
  eval "cap_$slots=\$_cap"
  eval "seen_$slots=0"
  slots=$((slots + 1))
done

# The readers are killed on every exit path: leaving one holding an input
# device across a suspend would keep a `dd` alive for as long as the panel runs.
cleanup() {
  for _pid in $readers; do
    kill "$_pid" 2>/dev/null
  done
}
trap cleanup EXIT

# A signal must still kill this script, and be seen to have killed it. A trap
# that cleans up and returns swallows the signal: the loop below carries on to
# the end of its window, and `dash.sh` — which only stops when a child of it
# dies of a signal — carries on too. So Ctrl-C during `DEBUG=true ./start.sh`
# would stop nothing at all, and that ten-second window is the documented way
# to interrupt the panel by hand.
#
# Clearing the trap and re-raising is what makes the second one fatal, and
# leaves the conventional 128+signal status behind for whoever is waiting.
trap 'cleanup; trap - INT;  kill -INT  $$' INT
trap 'cleanup; trap - TERM; kill -TERM $$' TERM

current=$(loc_current) || current=""

log "window ${SECONDS_TO_LISTEN}s, ${slots} device(s):${devices}, showing '${current:-none}' of $(loc_count) location(s)"

# A full refresh on arrival says "awake and listening" without drawing any
# chrome that would then have to be cleaned off the image. Only after a wake by
# hand: a scheduled refresh has just painted the screen anyway.
if [ "$FLASH" = true ] && [ -n "$current" ] && [ "${INTERACT_FLASH:-true}" = true ]; then
  loc_draw "$current"
fi

deadline=$(( $(date +%s) + SECONDS_TO_LISTEN ))
events=0
moves=0

# kindle-dash's stop.sh is `pkill -f dash.sh`, which reaches the loop and not
# this child of it. Without the check below, stopping the panel during the
# listening window would leave one of these counting down on its own, holding
# the input device — and redrawing the screen behind the framework that was
# just brought back.
#
# Watched only if watching works. `$PPID` is not always a process this shell
# can signal — it is not when the script is started by something that is not
# itself a process the shell can see, which is how it is run off the device —
# and a liveness test that answers "dead" on its first call would close every
# window one second after opening it. Asking once, up front, is the difference
# between a guard and a bug.
parent=$PPID
watch_parent=false
kill -0 "$parent" 2>/dev/null && watch_parent=true

# Everything the readers have produced since the last look, answered. A
# function rather than the body of the loop because it is needed twice: once
# per second while the window is open, and once more after it closes. A press
# that lands in the last second is a press, and dropping it made the panel feel
# unreliable in exactly the moment somebody is still deciding whether it works.
#
# Not called in a subshell anywhere: it updates `current`, `deadline`, `events`
# and `moves` in the caller, which is this script.
drain() {
  slot=0
  while [ "$slot" -lt "$slots" ]; do
    eval "cap=\$cap_$slot"
    eval "seen=\$seen_$slot"

    total=$(records_in "$cap")

    # A safety valve, and the price of listening to every device rather than to
    # one that was measured. Decoding a record costs three `dd` forks, so a
    # device that streams — anything that is not a keypad — would spend the
    # whole window being read and none of it answering buttons. A person
    # produces four events per press; a backlog this size in one second is not
    # a person, so it is dropped rather than worked through.
    if [ $((total - seen)) -gt "$MAX_BACKLOG" ]; then
      log "$cap produced $((total - seen)) events in a second: not a keypad, skipping"
      seen=$total
    fi

    while [ "$seen" -lt "$total" ]; do
      code=$(press_code "$cap" "$seen")
      seen=$((seen + 1))
      [ -n "$code" ] || continue
      events=$((events + 1))

      if in_list "$code" "$KEY_NEXT"; then
        step=1
      elif in_list "$code" "$KEY_PREV"; then
        step=-1
      else
        # Every other button on the device is not ours to answer. Logged all
        # the same: when the page buttons turn out to send codes this device
        # was never told about, this line is the whole diagnosis.
        log "key $code ignored (next='$KEY_NEXT' prev='$KEY_PREV')"
        continue
      fi

      [ -n "$current" ] || current=$(loc_current) || continue
      target=$(loc_step "$current" "$step") || continue
      [ "$target" = "$current" ] && continue

      if loc_go "$target"; then
        log "key $code: $current -> $target"
        current=$target
        moves=$((moves + 1))
        # Each press buys more time: walking five locations must not need five
        # presses inside the same shrinking window.
        deadline=$(( $(date +%s) + INTERACT_EXTEND ))
      else
        log "key $code: could not draw $target, staying on $current"
      fi
    done

    eval "seen_$slot=\$seen"
    slot=$((slot + 1))
  done
}

# The deadline is tested *after* the drain, not before it, and that ordering is
# the whole point of writing the loop this way.
#
# A press extends the window, so a press and the deadline are in a race: read
# the clock first and a button pushed in the last second is answered by a loop
# that has already decided to stop, and the extension it bought is applied to a
# window nobody is watching any more. Draining first means the window can only
# close on a device that had nothing left to say.
#
# It also removes a race that only exists off the Kindle, where it is what the
# test suite kept tripping over: the reader is a background process, and if it
# has not produced its first block by the time the first second is up, a loop
# that checks the clock first ends before it has ever looked.
while :; do
  sleep 1
  if [ "$watch_parent" = true ] && ! kill -0 "$parent" 2>/dev/null; then
    log "the panel loop is gone, closing the window"
    break
  fi
  drain
  [ "$(date +%s)" -lt "$deadline" ] || break
done

log "window closed: $events key press(es), $moves move(s)"
exit 0
