#!/usr/bin/env sh
# Suspends to RAM until the next refresh, and answers a wake-up by hand.
# Goes to /mnt/us/dashboard/local/suspend.sh on the Kindle.
#
#     suspend.sh <seconds>
#
# This replaces kindle-dash's own `rtc_sleep`, which it cannot extend: the
# function is defined inside dash.sh and there is no hook around it. The
# arithmetic is the same — arm the hardware clock, write "mem" to
# /sys/power/state — with one thing added, the reason the whole feature exists:
#
#   the loop now knows whether it woke up because the clock said so, or because
#   somebody pressed power.
#
# It can tell them apart by how long it actually slept. A wake-up by hand hands
# control to interact.sh, which reads the page buttons and changes location;
# then the remaining time is slept off, so pressing power at :20 does not
# postpone the :45 refresh.

DIR=$(dirname "$0")
RTC=${RTC:-/sys/devices/platform/mxc_rtc.0/wakeup_enable}
POWER_STATE=${POWER_STATE:-/sys/power/state}

INTERACT_SECONDS=${INTERACT_SECONDS:-25}
# How much shorter than the alarm counts as "somebody woke it up". Generous on
# purpose: the RTC is a second-resolution device and the resume itself takes a
# moment, so a scheduled wake-up can land a few seconds early.
EARLY_WAKE_MARGIN=${EARLY_WAKE_MARGIN:-10}
# Below this, going back to sleep is not worth a suspend cycle: the loop is
# better off returning and letting the refresh happen a minute early.
MIN_SLEEP=${MIN_SLEEP:-60}

remaining=${1:-0}

log() { echo "$(date) suspend: $*"; }

# DEBUG=true keeps the device reachable over SSH, exactly as upstream does:
# no suspend, no RTC, and Ctrl-C still works.
if [ "${DEBUG:-false}" = true ]; then
  log "DEBUG: sleeping ${remaining}s instead of suspending"
  sleep "$remaining"
  exit 0
fi

# Arm the hardware clock. Upstream writes only when the file reads 0, on the
# assumption that a non-zero value means an alarm is already pending; here the
# device may have just come back from a wake-up that was not the clock's doing,
# and a stale value left behind would make every later arming a no-op — the
# panel would then sleep until somebody pressed power again. So: report it,
# clear it, and write ours.
arm_rtc() {
  armed=$(cat "$RTC" 2>/dev/null)
  if [ -n "$armed" ] && [ "$armed" != 0 ]; then
    log "RTC still reads ${armed}s, clearing it before arming ${1}s"
    echo -n 0 > "$RTC" 2>/dev/null
  fi
  echo -n "$1" > "$RTC"
}

log "suspending for ${remaining}s (INTERACT=${INTERACT:-true}," \
    "window ${INTERACT_SECONDS}s, early-wake margin ${EARLY_WAKE_MARGIN}s)"

while [ "$remaining" -ge "$MIN_SLEEP" ]; do
  arm_rtc "$remaining"

  t0=$(date +%s)
  echo mem > "$POWER_STATE"
  t1=$(date +%s)

  slept=$((t1 - t0))
  [ "$slept" -lt 0 ] && slept=0        # the clock moved under us; ignore it
  planned=$remaining
  remaining=$((remaining - slept))

  if [ "$slept" -ge $((planned - EARLY_WAKE_MARGIN)) ]; then
    log "woke on the clock after ${slept}s"
    break
  fi

  # Woken by hand — the power slider, since the keypad cannot wake this device.
  # The window that follows is the whole point of pressing it.
  log "woken by hand after ${slept}s (alarm was ${planned}s), ${remaining}s left"

  # Timed rather than assumed: every press extends the window, so a session
  # spent walking through five locations lasts far longer than
  # INTERACT_SECONDS. Subtracting the nominal length instead of the real one
  # would leave the next alarm armed for time that has already gone, and the
  # scheduled refresh would land that much late.
  w0=$(date +%s)
  "$DIR/interact.sh" "$INTERACT_SECONDS" --flash
  w1=$(date +%s)
  window=$((w1 - w0))
  [ "$window" -lt 0 ] && window=$INTERACT_SECONDS
  remaining=$((remaining - window))
  log "window lasted ${window}s, ${remaining}s left before the next refresh"
done

log "returning to the loop"

exit 0
