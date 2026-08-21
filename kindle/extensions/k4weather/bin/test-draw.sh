#!/usr/bin/env sh
# One download, one draw, then back to the menu. Goes to
# /mnt/us/extensions/k4weather/bin/test-draw.sh on the Kindle.
#
# This is the SSH check-list from kindle/README.md — fetch, then draw with the
# indoor temperature on top — reduced to a menu entry, for the case where the
# computer is not at hand. It touches neither the framework nor the RTC: the
# reader keeps running underneath and the image stays until the next keypress
# repaints the home screen.
#
# Each step reports on the screen, because that is the only output a device
# with no terminal has. The messages are in Italian like the panel itself.

DASH_DIR=/mnt/us/dashboard
LOG_DIR="$DASH_DIR/logs"
LOG="$LOG_DIR/kual.log"
EIPS=/usr/sbin/eips
TEST_PNG=/tmp/k4weather-test.png

mkdir -p "$LOG_DIR"
log() { echo "$(date) k4weather/kual test: $*" >>"$LOG"; }
say() { log "$1"; "$EIPS" 1 1 "$1"; }

if [ ! -x "$DASH_DIR/local/fetch-dashboard.sh" ]; then
  say "k4-weather: niente in $DASH_DIR, lancia install.sh dal computer"
  exit 1
fi

# Sourced, not run: draw.sh reads INDOOR_TEMP_* from the environment, and this
# is the one place that has to set it up itself — normally start.sh does it.
# shellcheck disable=SC1091
. "$DASH_DIR/local/env.sh"

say "k4-weather: attendo il wi-fi..."
if ! "$DASH_DIR/wait-for-wifi.sh" "${WIFI_TEST_IP:-1.1.1.1}" >>"$LOG" 2>&1; then
  say "k4-weather: nessuna rete, controlla il wi-fi"
  exit 1
fi

say "k4-weather: scarico l'immagine..."
if ! "$DASH_DIR/local/fetch-dashboard.sh" "$TEST_PNG" >>"$LOG" 2>&1; then
  say "k4-weather: download fallito, vedi logs/kual.log"
  exit 1
fi

# Full refresh, not partial: this runs over whatever the framework had on
# screen, and a partial update would leave the old page showing through.
"$DASH_DIR/local/draw.sh" -f -g "$TEST_PNG" >>"$LOG" 2>&1
status=$?
rm -f "$TEST_PNG"

[ "$status" -eq 0 ] || say "k4-weather: disegno fallito ($status)"
log "test finished with status $status"
exit "$status"
