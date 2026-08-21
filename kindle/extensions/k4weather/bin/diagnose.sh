#!/bin/sh
# Writes down everything worth knowing when the panel does not start, and puts
# it where a computer can read it. Goes to
# /mnt/us/extensions/k4weather/bin/diagnose.sh on the Kindle.
#
# The whole point of this entry: the failures of a KUAL extension are invisible
# on the device. The menu prints the action it launched and exits, the
# framework repaints the home screen over anything the script managed to write,
# and the real error — the shell's own "not found" or "Permission denied" — is
# appended to /var/tmp/KUAL.log, which nothing ever shows you. So instead of
# reporting on the screen, this collects the answers and leaves them in a file
# at the root of the USB drive: plug the Kindle into a computer and open
# k4weather-diagnostica.txt.
#
# It changes nothing and starts nothing, so it is always safe to pick.

EXT_DIR=$(cd "$(dirname "$0")/.." 2>/dev/null && pwd) || EXT_DIR=/mnt/us/extensions/k4weather
DASH_DIR=${DASH_DIR:-/mnt/us/dashboard}
EIPS=${EIPS:-/usr/sbin/eips}
OUT=${OUT:-/mnt/us/k4weather-diagnostica.txt}

say() { "$EIPS" 1 1 "$1" 2>/dev/null; }

# One file, rewritten each time: a diagnostic that appends grows a history
# nobody asked for and buries the run that matters under the ones before it.
: > "$OUT" 2>/dev/null || {
  say "k4-weather: non riesco a scrivere $OUT"
  exit 1
}
exec >>"$OUT" 2>&1

section() { echo; echo "--- $* ---"; }

# Every check below answers a question that has actually been asked of this
# extension, in the order the launch itself asks them.

echo "k4-weather diagnostica"
echo "$(date)"
echo "estensione: $EXT_DIR"
echo "dashboard:  $DASH_DIR"

section "il dispositivo"
cat /etc/version.txt 2>/dev/null || echo "/etc/version.txt: assente"
echo "shell: $(readlink -f /bin/sh 2>/dev/null || echo /bin/sh)"
# Whether /usr/bin/env exists decides whether a `#!/usr/bin/env sh` shebang
# resolves at all, which is the quietest way for a script not to start.
[ -e /usr/bin/env ] && echo "/usr/bin/env: presente" || echo "/usr/bin/env: ASSENTE"
command -v setsid >/dev/null 2>&1 && echo "setsid: presente" || echo "setsid: assente (si usa nohup)"

section "il filesystem /mnt/us"
# The execute bit on FAT comes from the mount options, not from the files. If
# it is missing, a script called directly fails with "Permission denied" and
# only /var/tmp/KUAL.log ever hears about it — which is why every action in
# menu.json names its interpreter instead of relying on the bit.
grep ' /mnt/us ' /proc/mounts 2>/dev/null || echo "/mnt/us non risulta montato"

section "i file dell'estensione"
ls -l "$EXT_DIR" "$EXT_DIR/bin" 2>&1

section "i file del pannello"
if [ -d "$DASH_DIR" ]; then
  ls -l "$DASH_DIR" "$DASH_DIR/local" 2>&1
else
  echo "$DASH_DIR non esiste: install.sh non e' mai arrivato in fondo"
fi

section "cosa manca"
# Named one by one rather than as a count: "start.sh manca" is an instruction,
# "3 file mancanti" is a puzzle.
for f in start.sh stop.sh dash.sh wait-for-wifi.sh xh next-wakeup \
         local/env.sh local/draw.sh local/fetch-dashboard.sh \
         local/indoor-temp.sh local/interact.sh local/locations.sh \
         local/suspend.sh; do
  [ -f "$DASH_DIR/$f" ] || echo "manca: $DASH_DIR/$f"
done
[ -f "$DASH_DIR/fbink" ] \
  && echo "fbink: presente (temperatura interna grande)" \
  || echo "fbink: assente (temperatura interna disegnata da eips, piccola)"

section "si riesce davvero a eseguire uno script?"
# The question the rest of this file only circles around. A script written and
# run here reproduces exactly what KUAL does with a menu action, and tells the
# two failure modes apart by name.
probe=/tmp/k4weather-probe.sh
printf '#!/bin/sh\necho "  eseguito"\n' > "$probe"
chmod +x "$probe" 2>/dev/null
echo "chiamata diretta ($probe):"
"$probe" 2>&1 || echo "  FALLITA — e' questo che blocca l'avvio da KUAL"
echo "chiamata tramite sh:"
sh "$probe" 2>&1 || echo "  FALLITA — qualcosa di piu' grave del bit di esecuzione"
rm -f "$probe"

section "il pannello e' in esecuzione?"
if ps 2>/dev/null | grep -q '[d]ash\.sh'; then
  echo "si':"
  ps 2>/dev/null | grep '[d]ash\.sh'
else
  echo "no"
fi

section "le immagini scaricate"
if [ -d "$DASH_DIR/cache" ]; then
  ls -l "$DASH_DIR/cache" 2>&1
  echo "posizione mostrata: $(cat "$DASH_DIR/state/location" 2>/dev/null || echo '(nessuna)')"
else
  echo "nessuna cache: il pannello non ha mai scaricato nulla"
fi

# The logs last, because they are the longest and the least often needed. The
# KUAL one first: it is the only place the shell's own errors are written, and
# the reason this file exists.
section "/var/tmp/KUAL.log (errori delle voci di menu, ultime 40 righe)"
tail -n 40 /var/tmp/KUAL.log 2>/dev/null || echo "(vuoto o assente: nessuna voce di menu ha mai fallito)"

section "$EXT_DIR/kual.log (ultime 40 righe)"
tail -n 40 "$EXT_DIR/kual.log" 2>/dev/null || echo "(assente)"

section "$DASH_DIR/logs/dash.log (ultime 60 righe)"
tail -n 60 "$DASH_DIR/logs/dash.log" 2>/dev/null || echo "(assente)"

echo
echo "--- fine ---"

say "k4-weather: scritto k4weather-diagnostica.txt sul Kindle"
exit 0
