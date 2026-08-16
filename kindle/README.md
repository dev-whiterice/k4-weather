# Installazione sul Kindle 4

Il Kindle non calcola nulla: si sveglia, scarica un PNG e lo mostra. Tutta la
parte fragile (wifi, TLS, sospensione, sveglia da RTC) e' gia' risolta da
[pascalw/kindle-dash](https://github.com/pascalw/kindle-dash), che qui viene
usato come runtime. Questa cartella contiene solo i due file da sostituire.

## Prerequisiti, una tantum

1. **Jailbreak** del Kindle 4 NT — procedura sul
   [wiki di MobileRead](https://wiki.mobileread.com/wiki/Kindle4NTHacking).
2. **KUAL** e **USBNetwork**, per avere SSH sul dispositivo.
3. **Wi-Fi configurato** e funzionante.

Verifica di avere accesso root prima di proseguire:

```sh
ssh kindle    # oppure ssh root@192.168.15.244 via USBNetwork
```

## Installazione

```sh
# 1. Scarica l'ultima release di kindle-dash e scompattala
curl -L -o kindle-dash.zip \
  https://github.com/pascalw/kindle-dash/releases/latest/download/kindle-dash.zip
unzip kindle-dash.zip -d kindle-dash

# 2. Sovrascrivi la configurazione con quella di k4-weather
cp kindle/local/env.sh             kindle-dash/local/env.sh
cp kindle/local/fetch-dashboard.sh kindle-dash/local/fetch-dashboard.sh

# 3. Copia tutto sul Kindle
rsync -vr kindle-dash/ kindle:/mnt/us/dashboard

# 4. Avvia
ssh kindle /mnt/us/dashboard/start.sh
```

`DASH_URL` in `fetch-dashboard.sh` punta gia' a
`raw.githubusercontent.com/dev-whiterice/k4-weather-dash/output/dashboard.png`.
Va cambiato solo se rinomini il repository pubblico di destinazione.

Il dispositivo si sospende dopo 10-15 secondi e da li' in poi si sveglia da
solo ai minuti :15 e :45 di ogni ora.

Per avviarlo dal menu invece che da SSH, copia la cartella `KUAL/kindle-dash`
della release in `/mnt/us/extensions`.

## Verifica

```sh
ssh kindle
/mnt/us/dashboard/local/fetch-dashboard.sh /tmp/test.png   # deve uscire con 0
eips -f -g /tmp/test.png                                   # deve disegnare a schermo
```

Se l'immagine appare **deformata o schiacciata**, il PNG non e' in scala di
grigi: `eips` accetta solo grayscale a 8 bit senza canale alpha. Dal lato
generatore il controllo e' automatico:

```sh
make inspect
```

## Consumi

Con aggiornamento ogni 30 minuti e sospensione in RAM tra un refresh e l'altro,
l'autonomia attesa e' nell'ordine delle settimane. Per allungarla, limita
`REFRESH_SCHEDULE` alle ore in cui guardi davvero lo schermo, per esempio
`"15,45 7-23 * * *"`, e alza `SLEEP_SCREEN_INTERVAL` di conseguenza.

## Se lo schermo si blocca su un'immagine vecchia

`fetch-dashboard.sh` esce in errore senza toccare il file di destinazione:
in caso di rete assente il Kindle continua a mostrare l'ultima immagine buona
invece di sbiancare lo schermo. L'orario in basso a destra nella dashboard e'
quello di **generazione**, quindi si riconosce subito un'immagine ferma.
