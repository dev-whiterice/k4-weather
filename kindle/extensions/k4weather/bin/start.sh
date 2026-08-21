#!/usr/bin/env sh
# Starts the dashboard from the KUAL menu, so the panel can be brought up with
# no computer attached. Goes to
# /mnt/us/extensions/k4weather/bin/start.sh on the Kindle.
#
# Why this is not just a menu entry pointing straight at start.sh: the first
# thing dash.sh does is `/etc/init.d/framework stop`, and on a Kindle 4 KUAL is
# a kindlet running inside that framework. Launched as a child of the menu, the
# loop is in the framework's own session and gets torn down together with the
# thing it just killed — sometimes on the first pass, sometimes hours later.
# So the loop is moved into a session of its own before it is left alone.
#
# This is also the only channel that reaches a user with no shell: every
# failure below is written on the screen with eips, not only to the log.

DASH_DIR=/mnt/us/dashboard
LOG_DIR="$DASH_DIR/logs"
LOG="$LOG_DIR/kual.log"
EIPS=/usr/sbin/eips

mkdir -p "$LOG_DIR"
log() { echo "$(date) k4weather/kual start: $*" >>"$LOG"; }

# Row 1 rather than row 0: the top row sits under the status bar the framework
# is still drawing at this point.
say() { log "$1"; "$EIPS" 1 1 "$1"; }

if [ ! -x "$DASH_DIR/start.sh" ]; then
  say "k4-weather: niente in $DASH_DIR, lancia install.sh dal computer"
  exit 1
fi

# Two loops would race each other for the screen and for the RTC wakeup, and
# the second one would win the race often enough to be confusing. busybox `ps`
# takes no flags here and already lists everything; the bracket keeps the
# pattern from matching the grep that carries it.
if ps 2>/dev/null | grep -q '[d]ash\.sh'; then
  say "k4-weather: gia' in esecuzione"
  exit 0
fi

log "starting $DASH_DIR/start.sh"

# start.sh backgrounds dash.sh and returns immediately, so the session created
# here is the one the loop inherits. setsid is the real fix; where busybox was
# built without it, a double fork gets the loop reparented to init and nohup
# keeps the framework's exit from hanging it up — weaker, but better than
# leaving it in the framework's process group.
if command -v setsid >/dev/null 2>&1; then
  setsid "$DASH_DIR/start.sh" </dev/null >>"$LOG" 2>&1 &
else
  log "no setsid, falling back to nohup and a double fork"
  ( nohup "$DASH_DIR/start.sh" </dev/null >>"$LOG" 2>&1 & ) &
fi

# The dashboard replaces this within a few seconds. It stays on screen only if
# something went wrong before the first draw, which is exactly when it is worth
# reading.
"$EIPS" 1 1 "k4-weather: avvio in corso, attendere..."
exit 0
