#!/bin/sh
# Stops the dashboard loop and brings the ebook reader back. Goes to
# /mnt/us/extensions/k4weather/bin/stop.sh on the Kindle.
#
# Note when this is reachable at all: while the dashboard runs, the framework
# is down and KUAL is not on screen, so the normal way back is a reboot (power
# button held ~20s) — which already leaves the reader running, because nothing
# starts the dashboard at boot. What this entry is for is the untidy case: a
# loop left running behind a framework that is still up, after a failed start
# or after `bin/test-draw.sh` was interrupted. It is safe to pick when nothing
# is running.

EXT_DIR=$(cd "$(dirname "$0")/.." 2>/dev/null && pwd) || EXT_DIR=/mnt/us/extensions/k4weather
DASH_DIR=${DASH_DIR:-/mnt/us/dashboard}
EIPS=${EIPS:-/usr/sbin/eips}
LOG=${KUAL_LOG:-$EXT_DIR/kual.log}

log() { echo "$(date) k4weather/kual stop: $*" >>"$LOG" 2>/dev/null; }

# -f rather than -x, and `sh` rather than a direct call: on FAT the execute bit
# is a property of the mount, not of the file. See bin/start.sh.
if [ -f "$DASH_DIR/stop.sh" ]; then
  sh "$DASH_DIR/stop.sh" >>"$LOG" 2>&1
else
  log "no $DASH_DIR/stop.sh, killing dash.sh directly"
  pkill -f dash.sh >>"$LOG" 2>&1
fi

# The loop can be inside its 10-second window before suspend: give it time to
# notice the signal before the framework starts repainting over it.
sleep 2

# Idempotent: on a framework that is already up this is a no-op, and starting
# it is the half people forget when they stop the loop by hand.
/etc/init.d/framework start >>"$LOG" 2>&1

log "stopped, framework restarted"
"$EIPS" 1 1 "k4-weather: fermato, lettore riavviato" 2>/dev/null
exit 0
