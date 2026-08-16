#!/usr/bin/env bash
# Installa kindle-dash sul Kindle, configurato per k4-weather.
#
# GIRA SUL MAC, non sul Kindle. Da qualunque cartella:
#
#     ./kindle/install.sh                      # usa root@192.168.15.244
#     ./kindle/install.sh root@192.168.1.50    # Kindle raggiungibile via Wi-Fi
#
# Non avvia nulla: alla fine la dashboard e' installata ma ferma, cosi' puoi
# provarla in modalita' debug prima di lasciarla in mano al ciclo di sospensione.

set -euo pipefail

KINDLE="${1:-root@192.168.15.244}"
REMOTE_DIR="/mnt/us/dashboard"

# Percorsi relativi allo script, non alla cartella da cui lo lanci.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="${HERE}/../build/kindle-dash"

RELEASES="https://api.github.com/repos/pascalw/kindle-dash/releases/latest"

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
fail() { printf '\033[31mErrore: %s\033[0m\n' "$1" >&2; exit 1; }

for tool in curl tar ssh; do
  command -v "$tool" >/dev/null || fail "manca il comando '$tool'"
done

step "Scarico kindle-dash"
rm -rf "$BUILD"
mkdir -p "$BUILD"
asset="$(curl -sSfL "$RELEASES" | grep browser_download_url | cut -d'"' -f4)"
[ -n "$asset" ] || fail "non trovo l'asset della release su GitHub"
echo "    $asset"
# L'archivio si espande piatto, senza cartella contenitore.
curl -sSfL "$asset" | tar xz -C "$BUILD"
[ -x "$BUILD/dash.sh" ] || fail "l'archivio non contiene dash.sh"

step "Applico la configurazione di k4-weather"
cp "$HERE/local/env.sh" "$BUILD/local/env.sh"
cp "$HERE/local/fetch-dashboard.sh" "$BUILD/local/fetch-dashboard.sh"
url="$(grep -m1 '^DASH_URL=' "$BUILD/local/fetch-dashboard.sh" | cut -d'"' -f2)"
echo "    sorgente immagine: $url"

step "Verifico che l'immagine sia raggiungibile"
# Meglio scoprire adesso che l'URL e' sbagliato, invece che davanti a uno
# schermo e-ink che non si aggiorna e non dice perche'.
code="$(curl -sS -o /dev/null -w '%{http_code}' "$url" || true)"
if [ "$code" = "200" ]; then
  echo "    HTTP 200, l'immagine c'e'"
else
  echo "    ATTENZIONE: HTTP ${code:-nessuna risposta}"
  echo "    Il workflow 'dashboard' non ha ancora pubblicato sul branch output."
  echo "    L'installazione prosegue: il Kindle funzionera' appena l'immagine esiste."
fi

# USBNetwork non fa da server DHCP: macOS chiede un indirizzo, non riceve
# risposta e ripiega su un link-local 169.254.x.x. A quel punto il traffico per
# il Kindle esce dal Wi-Fi verso internet e va in timeout. L'indirizzo host
# della subnet va messo a mano.
diagnose_usbnet() {
  [ "$(uname)" = "Darwin" ] || return 0
  local iface subnet
  iface="$(networksetup -listallhardwareports 2>/dev/null \
    | awk '/^Hardware Port: RNDIS|^Hardware Port: .*Ethernet Gadget/{getline; print $2; exit}')"
  [ -n "$iface" ] || return 0

  subnet="${KINDLE##*@}"; subnet="${subnet%.*}"
  ifconfig "$iface" 2>/dev/null | grep -q "inet ${subnet}\." && return 0

  cat >&2 <<EOF

L'interfaccia USBNetwork ($iface) esiste ma non ha un indirizzo su ${subnet}.x:

$(ifconfig "$iface" | grep -E 'inet |status' | sed 's/^/    /')

Assegnalo e rilancia questo script:

    sudo ifconfig $iface ${subnet}.201 netmask 255.255.255.0

Va rifatto a ogni riconnessione del cavo. Non impostare un gateway su questa
interfaccia: verrebbe preferita al Wi-Fi e resteresti senza internet.
EOF
  exit 1
}

step "Copio su $KINDLE:$REMOTE_DIR"
ssh -o ConnectTimeout=10 "$KINDLE" "mkdir -p $REMOTE_DIR" 2>/dev/null || {
  diagnose_usbnet
  fail "non riesco a raggiungere $KINDLE (USBNetwork attivo? cavo collegato?)"
}
# Niente rsync: macOS 15+ monta openrsync (compatibile rsync 2.6.9) e il
# Kindle ha il tar di busybox. Un tar su SSH parla la lingua di entrambi.
#
# COPYFILE_DISABLE evita i sidecar AppleDouble `._*`, e --format=ustar evita
# gli header pax estesi: il tar di busybox non li capisce e stampa una raffica
# di "skipping header 'x'".
COPYFILE_DISABLE=1 tar c --format=ustar -C "$BUILD" . \
  | ssh "$KINDLE" "mkdir -p '$REMOTE_DIR' && cd '$REMOTE_DIR' && tar x"

# Ripulisce i residui di installazioni fatte prima di questa correzione.
# Il find di busybox non ha -delete, e con -exec cancella durante la visita
# saltandone una parte: meglio raccogliere prima la lista e poi cancellare.
ssh "$KINDLE" "find '$REMOTE_DIR' -name '._*' | xargs rm -f" 2>/dev/null || true
echo "    copiati $(find "$BUILD" -type f | wc -l | tr -d ' ') file"

step "Ripristino i permessi di esecuzione"
# Su /mnt/us (filesystem FAT) i permessi possono non essere memorizzati: se il
# chmod non attacca non e' un problema, la partizione e' montata eseguibile.
ssh "$KINDLE" "chmod +x $REMOTE_DIR/*.sh $REMOTE_DIR/local/*.sh \
  $REMOTE_DIR/xh $REMOTE_DIR/next-wakeup" 2>/dev/null \
  || echo "    chmod non applicabile (FAT): normale, si prosegue"

cat <<EOF

Installazione completata. Non ho avviato niente di proposito.

Prova prima i singoli pezzi, collegandoti al Kindle:

    ssh $KINDLE
    cd $REMOTE_DIR
    ./local/fetch-dashboard.sh /tmp/test.png && echo OK    # solo download
    eips -f -g /tmp/test.png                               # solo disegno
    DEBUG=true ./start.sh                                  # ciclo completo, Ctrl-C per uscire

Quando funziona, l'avvio vero (in background, poi il Kindle si sospende):

    ssh $KINDLE $REMOTE_DIR/start.sh

Per riprenderti il Kindle come lettore di ebook:

    ssh $KINDLE '$REMOTE_DIR/stop.sh; /etc/init.d/framework start'
EOF
