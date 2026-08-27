#!/bin/sh
# Twenty seconds of the real thing: press the page buttons and watch the panel
# change location. Goes to
# /mnt/us/extensions/k4weather/bin/test-keys.sh on the Kindle.
#
# "The buttons do nothing" is the hardest fault this project has to report,
# because everything it could be is invisible from the device: the wrong input
# device, key codes this Kindle does not send, one location in the cache
# instead of five, or the whole feature switched off by a stray character in
# env.sh. All of it is decided inside local/interact.sh, which normally runs
# for ten seconds behind a stopped framework where nobody can see it.
#
# So this entry runs exactly that script, in exactly those conditions, and then
# says what it saw. No second implementation of the decoding — a test that
# passes against a copy of the code proves nothing about the code.
#
# It stops the reader framework for the length of the test and starts it again
# afterwards, come what may. With the framework up the presses would also turn
# pages in whatever book is open, and its repaints would fight the panel for
# the screen.

CR=$(printf '\r')
if grep -q "$CR" "$0" 2>/dev/null; then
  REPAIRED=/tmp/k4weather-test-keys.sh
  tr -d "$CR" < "$0" > "$REPAIRED" 2>/dev/null
  if [ -s "$REPAIRED" ] && ! grep -q "$CR" "$REPAIRED" 2>/dev/null; then
    exec /bin/sh "$REPAIRED" "$@"
  fi
fi

EXT_DIR=$(cd "$(dirname "$0")/.." 2>/dev/null && pwd) || EXT_DIR=/mnt/us/extensions/k4weather
[ -d "$EXT_DIR/bin" ] || EXT_DIR=/mnt/us/extensions/k4weather
DASH_DIR=${DASH_DIR:-/mnt/us/dashboard}
EIPS=${EIPS:-/usr/sbin/eips}
LOG=${KUAL_LOG:-$EXT_DIR/kual.log}
WINDOW=${K4W_KEYTEST_WINDOW:-20}

log() { echo "$(date) k4weather/kual keys: $*" >>"$LOG" 2>/dev/null; }
say() { log "$1"; "$EIPS" 1 1 "$1" 2>/dev/null; }

fail() {
  say "$1"
  sleep 4
  "$EIPS" 1 1 "$1" 2>/dev/null
  "$EIPS" 1 2 "log: extensions/k4weather/kual.log" 2>/dev/null
  exit 1
}

if [ ! -f "$DASH_DIR/local/interact.sh" ]; then
  fail "k4-weather: niente in $DASH_DIR, lancia install.sh dal computer"
fi

# The loop opens a listening window of its own before every suspend. A second
# one running beside it would share the keypad and both would answer the same
# press, so the panel would jump two locations and the test would measure
# something nobody will ever reproduce.
if ps 2>/dev/null | grep -q '[d]ash\.sh'; then
  fail "k4-weather: il pannello e' in esecuzione, prima 'Meteo: ferma'"
fi

# Nothing to switch between is not a button fault, and saying so here saves
# somebody twenty seconds of pressing a button that is working perfectly.
if [ ! -f "$DASH_DIR/cache/locations.txt" ]; then
  fail "k4-weather: nessuna immagine in cache, prima 'Meteo: prova'"
fi
cached=$(ls "$DASH_DIR/cache"/*.png 2>/dev/null | wc -l | tr -d ' ')
if [ "${cached:-0}" -lt 2 ]; then
  fail "k4-weather: solo ${cached:-0} localita' in cache, prima 'Meteo: prova'"
fi

# The dashboard's own settings, so this measures the configuration that is
# really in use rather than the defaults built into the scripts.
# shellcheck disable=SC1091
. "$DASH_DIR/local/env.sh"

log "starting: ${cached} cached location(s), INTERACT=${INTERACT:-unset}," \
    "KEY_DEVICE=${KEY_DEVICE:-unset}, next='${KEY_NEXT:-unset}'," \
    "prev='${KEY_PREV:-unset}'"

# The framework comes back whatever happens next, including a signal: leaving
# a Kindle with no reader and no panel is the one outcome this must not have.
framework_back() {
  /etc/init.d/framework start >>"$LOG" 2>&1
}
trap 'framework_back' EXIT
trap 'framework_back; trap - INT;  kill -INT  $$' INT
trap 'framework_back; trap - TERM; kill -TERM $$' TERM

/etc/init.d/framework stop >>"$LOG" 2>&1
# The framework repaints on its way down, and eips writes underneath it are
# lost; this is the wait for it to finish doing that.
sleep 3

"$EIPS" -c 2>/dev/null
"$EIPS" 1 1 "k4-weather: premi i tasti pagina (${WINDOW}s)" 2>/dev/null
"$EIPS" 1 2 "la localita' deve cambiare a ogni pressione" 2>/dev/null
sleep 2

# --flash so the panel repaints the current location first: that flash is the
# device saying "I am listening", and its absence is itself an answer.
OUT=/tmp/k4weather-keytest.out
sh "$DASH_DIR/local/interact.sh" "$WINDOW" --flash > "$OUT" 2>&1
cat "$OUT" >>"$LOG" 2>/dev/null

# interact.sh counts what it saw, in a line of its own, and that count is the
# whole verdict: presses seen but no moves is a different fault from no presses
# at all, and both are different from a window that never opened.
summary=$(grep 'window closed' "$OUT" 2>/dev/null | tail -n 1)
presses=$(echo "$summary" | sed 's/.*: \([0-9]*\) key press.*/\1/')
moves=$(echo "$summary" | sed 's/.*, \([0-9]*\) move.*/\1/')
case "$presses" in ''|*[!0-9]*) presses=0 ;; esac
case "$moves"   in ''|*[!0-9]*) moves=0 ;; esac

ignored=$(grep -c 'ignored' "$OUT" 2>/dev/null)
case "$ignored" in ''|*[!0-9]*) ignored=0 ;; esac

log "verdict: presses=$presses moves=$moves ignored=$ignored"

# Said before the framework repaints over it, and said in terms of what to do
# next rather than of what happened.
"$EIPS" -c 2>/dev/null
if [ "$moves" -gt 0 ]; then
  "$EIPS" 1 1 "k4-weather: OK, $moves cambi su $presses pressioni" 2>/dev/null
elif [ "$ignored" -gt 0 ]; then
  "$EIPS" 1 1 "k4-weather: tasti letti ma codici sconosciuti" 2>/dev/null
  "$EIPS" 1 2 "i codici visti sono nel log, mettili in env.sh" 2>/dev/null
elif [ "$presses" -gt 0 ]; then
  "$EIPS" 1 1 "k4-weather: tasti letti, nessun cambio" 2>/dev/null
  "$EIPS" 1 2 "manca l'immagine di una localita'? vedi il log" 2>/dev/null
else
  "$EIPS" 1 1 "k4-weather: nessuna pressione rilevata" 2>/dev/null
  "$EIPS" 1 2 "vedi extensions/k4weather/kual.log" 2>/dev/null
fi
sleep 5

rm -f "$OUT"
exit 0
