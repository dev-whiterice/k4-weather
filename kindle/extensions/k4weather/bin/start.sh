#!/bin/sh
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
# This is also the only channel that reaches a user with no shell, and it is a
# narrow one: KUAL exits before this runs, the framework repaints the home
# screen a moment later, and an eips message written in between is wiped by it.
# Hence `fail`, which says things twice, and the log — see config.xml.

# KUAL sets the working directory to the extension folder, but nothing here
# relies on that: $0 is the only thing that always points at this file.
EXT_DIR=$(cd "$(dirname "$0")/.." 2>/dev/null && pwd) || EXT_DIR=/mnt/us/extensions/k4weather
DASH_DIR=${DASH_DIR:-/mnt/us/dashboard}
EIPS=${EIPS:-/usr/sbin/eips}

# Beside the extension, not inside $DASH_DIR: this script has to be able to
# report "there is no $DASH_DIR" too, and it cannot do that into a directory
# whose absence is the news. Over USB it is extensions/k4weather/kual.log.
LOG=${KUAL_LOG:-$EXT_DIR/kual.log}

log() { echo "$(date) k4weather/kual start: $*" >>"$LOG" 2>/dev/null; }

# Row 1 rather than row 0: the top row sits under the status bar the framework
# is still drawing at this point.
say() { log "$1"; "$EIPS" 1 1 "$1" 2>/dev/null; }

# A failure has to survive the home screen the framework repaints when KUAL
# exits. Saying it once is not enough — that first message is usually painted
# over within a second — so this waits for the repaint to happen and says it
# again, with the log path underneath it. A success needs none of this: the
# dashboard itself replaces the screen.
fail() {
  say "$1"
  sleep 4
  "$EIPS" 1 1 "$1" 2>/dev/null
  "$EIPS" 1 2 "log: extensions/k4weather/kual.log" 2>/dev/null
  exit 1
}

# -f, not -x. /mnt/us is FAT: the execute bit there is synthesised by the mount
# options and says nothing about whether the file can be run, so `-x` reports
# "the dashboard is not installed" for an installation that is perfectly fine.
# Everything below is started through `sh` for the same reason.
if [ ! -f "$DASH_DIR/start.sh" ]; then
  fail "k4-weather: niente in $DASH_DIR, lancia install.sh dal computer"
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
  setsid sh "$DASH_DIR/start.sh" </dev/null >>"$LOG" 2>&1 &
else
  log "no setsid, falling back to nohup and a double fork"
  ( nohup sh "$DASH_DIR/start.sh" </dev/null >>"$LOG" 2>&1 & ) &
fi

# The dashboard replaces this within a few seconds. It stays on screen only if
# something went wrong before the first draw, which is exactly when it is worth
# reading.
"$EIPS" 1 1 "k4-weather: avvio in corso, attendere..." 2>/dev/null
exit 0
