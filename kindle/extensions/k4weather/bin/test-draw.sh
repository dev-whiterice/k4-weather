#!/bin/sh
# One download, one draw, then back to the menu. Goes to
# /mnt/us/extensions/k4weather/bin/test-draw.sh on the Kindle.
#
# This is the SSH check-list from kindle/README.md — fetch, then draw with the
# indoor temperature and the battery level stamped on top — reduced to a menu
# entry, for the case where the computer is not at hand. It touches neither the framework nor the RTC: the
# reader keeps running underneath and the image stays until the next keypress
# repaints the home screen.
#
# Each step reports on the screen, because that is the only output a device
# with no terminal has. The messages are in Italian like the panel itself.

EXT_DIR=$(cd "$(dirname "$0")/.." 2>/dev/null && pwd) || EXT_DIR=/mnt/us/extensions/k4weather
DASH_DIR=${DASH_DIR:-/mnt/us/dashboard}
EIPS=${EIPS:-/usr/sbin/eips}
LOG=${KUAL_LOG:-$EXT_DIR/kual.log}
TEST_PNG=${TEST_PNG:-/tmp/k4weather-test.png}

log() { echo "$(date) k4weather/kual test: $*" >>"$LOG" 2>/dev/null; }
say() { log "$1"; "$EIPS" 1 1 "$1" 2>/dev/null; }

# Said twice, for the same reason as in bin/start.sh: KUAL exits before this
# runs and the framework repaints the home screen over the first message. The
# steps below take seconds, so only the earliest failures need it — but those
# are the ones that leave the screen looking like nothing happened at all.
fail() {
  say "$1"
  sleep 4
  "$EIPS" 1 1 "$1" 2>/dev/null
  "$EIPS" 1 2 "log: extensions/k4weather/kual.log" 2>/dev/null
  exit 1
}

# -f, not -x: on FAT the execute bit says nothing. See bin/start.sh.
if [ ! -f "$DASH_DIR/local/fetch-dashboard.sh" ]; then
  fail "k4-weather: niente in $DASH_DIR, lancia install.sh dal computer"
fi

# Sourced, not run: draw.sh reads INDOOR_TEMP_* from the environment, and this
# is the one place that has to set it up itself — normally start.sh does it.
# shellcheck disable=SC1091
. "$DASH_DIR/local/env.sh"

say "k4-weather: attendo il wi-fi..."
if ! sh "$DASH_DIR/wait-for-wifi.sh" "${WIFI_TEST_IP:-1.1.1.1}" >>"$LOG" 2>&1; then
  fail "k4-weather: nessuna rete, controlla il wi-fi"
fi

say "k4-weather: scarico l'immagine..."
if ! sh "$DASH_DIR/local/fetch-dashboard.sh" "$TEST_PNG" >>"$LOG" 2>&1; then
  fail "k4-weather: download fallito, vedi il log"
fi

# Full refresh, not partial: this runs over whatever the framework had on
# screen, and a partial update would leave the old page showing through.
sh "$DASH_DIR/local/draw.sh" -f -g "$TEST_PNG" >>"$LOG" 2>&1
status=$?
rm -f "$TEST_PNG"

[ "$status" -eq 0 ] || fail "k4-weather: disegno fallito ($status)"
log "test finished with status $status"
exit "$status"
