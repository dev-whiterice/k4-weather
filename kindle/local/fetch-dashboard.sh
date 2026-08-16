#!/usr/bin/env sh
# Scarica la dashboard e la scrive in "$1", come richiede kindle-dash.
# Va copiato in /mnt/us/dashboard/local/fetch-dashboard.sh sul Kindle.
#
# curl e wget di serie sul Kindle 4 non parlano TLS moderno: usiamo `xh`,
# il client statico che kindle-dash include nella propria release.

# Il branch `output` del repository, dove il workflow pubblica l'immagine.
# Il Kindle non ha modo di autenticarsi: la sorgente deve essere leggibile
# senza token, ed e' il motivo per cui il repository e' pubblico.
DASH_URL="https://raw.githubusercontent.com/dev-whiterice/k4-weather/output/dashboard.png"

XH="$(dirname "$0")/../xh"
TARGET="$1"
TMP="${TARGET}.part"
ATTEMPTS=3

i=1
while [ "$i" -le "$ATTEMPTS" ]; do
  # Il parametro di cache-busting evita che GitHub Pages serva la copia
  # precedente rimasta in cache intermedia.
  if "$XH" -d -q --follow -o "$TMP" get "${DASH_URL}?t=$(date +%s)" && [ -s "$TMP" ]; then
    mv "$TMP" "$TARGET"
    exit 0
  fi
  rm -f "$TMP"
  sleep 5
  i=$((i + 1))
done

# Uscendo con errore senza toccare "$TARGET" lo schermo conserva l'ultima
# immagine buona invece di svuotarsi: preferibile a un pannello bianco.
echo "k4-weather: download fallito dopo ${ATTEMPTS} tentativi" >&2
exit 1
