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
# So the loop is moved into a session of its own before it is left alone, and
# given a moment to let KUAL finish leaving before it pulls the framework down
# underneath it.
#
# This is also the only channel that reaches a user with no shell, and it is a
# narrow one: KUAL exits before this runs, the framework repaints the home
# screen a moment later, and an eips message written in between is wiped by it.
# Hence `fail`, which says things twice, and the log — see config.xml.

# ---------------------------------------------------- carriage returns, first
#
# Before anything reads a variable, because a variable is exactly what this
# breaks. The Kindle's busybox `ash` does not treat a carriage return as
# whitespace: it is an ordinary character and it ends up inside the value. A
# copy of this file with CRLF line endings — which is what a checkout on
# Windows produces unless it is told otherwise — assigns "/mnt/us/dashboard<CR>"
# below, finds no such directory, and reports that the dashboard is not
# installed. Which is true of no directory that exists.
#
# `$0` is the one thing here that cannot carry a CR, so the test is done
# against the file rather than against anything read out of it. A copy with the
# returns taken out is written to /tmp and this script hands over to it; the
# copy then finds itself clean, does not do this again, and repairs the rest of
# the installation below.
CR=$(printf '\r')
if grep -q "$CR" "$0" 2>/dev/null; then
  REPAIRED=/tmp/k4weather-start.sh
  tr -d "$CR" < "$0" > "$REPAIRED" 2>/dev/null
  # Only if it actually worked: an exec into a file that is still broken would
  # come straight back here and loop for ever.
  if [ -s "$REPAIRED" ] && ! grep -q "$CR" "$REPAIRED" 2>/dev/null; then
    exec /bin/sh "$REPAIRED" "$@"
  fi
fi

# KUAL sets the working directory to the extension folder, but nothing here
# relies on that: $0 is the only thing that always points at this file. The
# repaired copy above lives in /tmp, so it cannot be used to find the extension
# — hence the fallback, which is where the extension always is.
EXT_DIR=$(cd "$(dirname "$0")/.." 2>/dev/null && pwd) || EXT_DIR=/mnt/us/extensions/k4weather
[ -d "$EXT_DIR/bin" ] || EXT_DIR=/mnt/us/extensions/k4weather
DASH_DIR=${DASH_DIR:-/mnt/us/dashboard}
EIPS=${EIPS:-/usr/sbin/eips}

# How long to wait before the dashboard pulls the framework down. KUAL exits
# the moment it launches this, and the framework then repaints the home screen;
# stopping it in the middle of that leaves the device in a state where neither
# the reader nor the panel is drawing. A few seconds is enough for the exit to
# finish, and they are spent detached, so the menu still returns immediately.
SETTLE=${K4W_SETTLE:-5}
# How long to give the loop to prove it is alive before reporting on it. It has
# to cover `framework stop` and the first pass through the main loop, which
# reaches its first sleep well inside this.
CONFIRM=${K4W_CONFIRM:-20}

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

# The same repair, for the installation this is about to launch. A CR in
# local/env.sh is quieter than one in this file and worse: `INTERACT=true<CR>`
# is not equal to `true`, so the page buttons stop working and nothing at all
# is reported. Idempotent, and a no-op on an installation that is already
# clean, which is the normal case.
repaired=0
for script in "$DASH_DIR"/*.sh "$DASH_DIR"/local/*.sh "$EXT_DIR"/bin/*.sh; do
  [ -f "$script" ] || continue
  grep -q "$CR" "$script" 2>/dev/null || continue
  if tr -d "$CR" < "$script" > "$script.lf" 2>/dev/null && mv "$script.lf" "$script"; then
    repaired=$((repaired + 1))
  else
    rm -f "$script.lf"
  fi
done
if [ "$repaired" -gt 0 ]; then
  log "repaired CRLF line endings in $repaired script(s) — reinstall from a"
  log "checkout with the repository's .gitattributes to fix this at the source"
fi

# Two loops would race each other for the screen and for the RTC wakeup, and
# the second one would win the race often enough to be confusing. busybox `ps`
# takes no flags here and already lists everything; the bracket keeps the
# pattern from matching the grep that carries it.
running() { ps 2>/dev/null | grep -q '[d]ash\.sh'; }

if running; then
  say "k4-weather: gia' in esecuzione"
  exit 0
fi

# ------------------------------------------------------------- the handover
#
# Everything from here happens in a session of its own, so that the framework
# taking itself down cannot take the launch with it, and so that the settle
# wait and the check that follows it do not hold the menu open.
#
# The detached half is marked by an argument rather than by an exported
# variable: an argument survives setsid, nohup and a subshell by construction.
if [ "${1:-}" != "--detached" ]; then
  log "starting $DASH_DIR/start.sh (settle ${SETTLE}s, confirm ${CONFIRM}s)"

  # Both halves of this were wrong before, and the log said so on every run:
  #
  #     no setsid, falling back to nohup and a double fork
  #     bin/start.sh: line 77: nohup: not found
  #
  # so the panel was never started from the menu at all, three attempts out of
  # three. What this device actually has is neither of the two things that were
  # assumed.
  #
  # `setsid` is PROBED BY RUNNING IT, not by asking `command -v`: this Kindle
  # has no `command` builtin, so that test answers "missing" for things that
  # are present, and the fallback it selects has to work anyway. Same discovery
  # as kindle/tools/keytest.sh, which was written after the same failure.
  #
  # The fallback uses no external program at all. `nohup` is not on this
  # device; ignoring SIGHUP in a subshell is what nohup does, and the shell can
  # do it by itself. The double fork then leaves the loop parented to init.
  # Weaker than a session of its own — it stays in the framework's process
  # group — but it is what there is, and it does start.
  if setsid true 2>/dev/null; then
    log "detaching with setsid"
    setsid /bin/sh "$0" --detached </dev/null >>"$LOG" 2>&1 &
  else
    log "no setsid: detaching with a HUP-proof subshell and a double fork"
    ( trap '' HUP; /bin/sh "$0" --detached </dev/null >>"$LOG" 2>&1 & ) &
  fi

  # The dashboard replaces this within a few seconds. It stays on screen only
  # if something went wrong before the first draw, which is exactly when it is
  # worth reading.
  "$EIPS" 1 1 "k4-weather: avvio in corso, attendere..." 2>/dev/null
  exit 0
fi

# ---- detached from here on: the log and eips are the only output ----

# Let KUAL finish leaving. dash.sh stops the framework as its very first act,
# and doing that while the menu is still unwinding is what leaves the device
# showing neither the reader nor the panel.
sleep "$SETTLE"

# How big the dashboard's own log is before we start, so that growth can be
# used as evidence afterwards. See the two-signal check below.
DASH_LOG="$DASH_DIR/logs/dash.log"

# The -f test is not decoration. `wc -c < missing` fails in the shell, when it
# opens the redirection, before `wc` is ever run — so the `2>/dev/null` on the
# command does not catch it and the error lands in the log on every first-ever
# start, where it reads like a fault and is not one.
log_size() {
  [ -f "$DASH_LOG" ] || { echo 0; return; }
  wc -c < "$DASH_LOG" 2>/dev/null | tr -d ' '
}
before=$(log_size)
[ -n "$before" ] || before=0

sh "$DASH_DIR/start.sh" >>"$LOG" 2>&1
log "start.sh returned $?"

# The half that was missing, and the reason this entry could look like it did
# nothing: start.sh backgrounds dash.sh and returns immediately, so its exit
# status says nothing at all about whether the loop survived.
sleep "$CONFIRM"

# Two independent signals, and only a failure on BOTH counts as a failure.
#
# The process table is the direct answer, but it is read through `ps | grep`,
# and how much of a command line busybox `ps` prints is a property of how it
# was built. If it prints less than expected here, a single-signal check would
# declare a perfectly healthy panel dead — and then restart the framework on
# top of it, which is a worse outcome than the fault this is meant to catch.
#
# The second signal cannot be wrong in that direction: dash.sh writes
# "Starting dashboard with ... refresh" to logs/dash.log before it does
# anything else, and start.sh is what redirects it there. A log that has grown
# since a moment ago is a loop that ran.
after=$(log_size)
[ -n "$after" ] || after=0

if running; then
  log "confirmed: dash.sh is in the process table"
  exit 0
fi

if [ "$after" -gt "$before" ]; then
  log "dash.sh is not in the process table, but dash.log grew from ${before}"
  log "to ${after} bytes, so the loop did run. Leaving it alone."
  exit 0
fi

# Neither signal. Whatever went wrong went into the dashboard's own log, so
# bring the last of it into ours — that file is on the USB drive and readable
# from any computer, while /var/tmp is not.
log "dash.sh is NOT running ${CONFIRM}s after the launch, and dash.log did not grow"
{
  echo "--- last 20 lines of $DASH_LOG ---"
  tail -n 20 "$DASH_LOG" 2>/dev/null || echo "(no dash.log at all)"
  echo "--- end ---"
} >>"$LOG" 2>&1

# The framework was very probably stopped before the loop died, which would
# leave the device with nothing drawing at all. Put the reader back: a Kindle
# that is a Kindle again is a far better failure than a black screen.
/etc/init.d/framework start >>"$LOG" 2>&1
sleep 6
"$EIPS" 1 1 "k4-weather: avvio fallito, lettore ripristinato" 2>/dev/null
"$EIPS" 1 2 "vedi KUAL > k4-weather > Meteo: diagnostica" 2>/dev/null
exit 1
