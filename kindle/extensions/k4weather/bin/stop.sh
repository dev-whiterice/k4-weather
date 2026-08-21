#!/usr/bin/env sh
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

DASH_DIR=/mnt/us/dashboard
LOG_DIR="$DASH_DIR/logs"
LOG="$LOG_DIR/kual.log"
EIPS=/usr/sbin/eips

mkdir -p "$LOG_DIR"
log() { echo "$(date) k4weather/kual stop: $*" >>"$LOG"; }

if [ -x "$DASH_DIR/stop.sh" ]; then
  "$DASH_DIR/stop.sh" >>"$LOG" 2>&1
else
  pkill -f dash.sh >>"$LOG" 2>&1
fi

# The loop can be inside its 10-second window before suspend: give it time to
# notice the signal before the framework starts repainting over it.
sleep 2

# Idempotent: on a framework that is already up this is a no-op, and starting
# it is the half people forget when they stop the loop by hand.
/etc/init.d/framework start >>"$LOG" 2>&1

log "stopped, framework restarted"
"$EIPS" 1 1 "k4-weather: fermato, lettore riavviato"
exit 0
