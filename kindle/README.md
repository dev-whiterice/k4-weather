# Il client sul Kindle 4

Il Kindle non calcola nulla: si sveglia, scarica un PNG, lo disegna e torna a
dormire. Tutta la parte fragile — attesa del Wi-Fi, TLS moderno, sospensione in
RAM, sveglia programmata dall'orologio hardware — e' gia' risolta da
[pascalw/kindle-dash](https://github.com/pascalw/kindle-dash), usato qui come
runtime. Questa cartella contiene solo i due file di configurazione da
sostituire.

## Cosa fa `kindle-dash`, in concreto

All'avvio `dash.sh` **spegne l'interfaccia del Kindle**:

```sh
/etc/init.d/framework stop          # via il lettore di ebook
initctl stop webreader
echo powersave > .../scaling_governor
lipc-set-prop com.lab126.powerd preventScreenSaver 1
```

Da quel momento il dispositivo non e' piu un lettore: e' un pannello. Per
tornare indietro serve `stop.sh` **seguito da** `/etc/init.d/framework start`,
oppure un riavvio.

Poi entra nel ciclo principale, che a ogni giro:

1. registra il livello di batteria nel log;
2. chiede al binario `next-wakeup` quanti secondi mancano al prossimo slot del
   `REFRESH_SCHEDULE`;
3. se mancano piu di `SLEEP_SCREEN_INTERVAL` secondi mostra `sleeping.png`,
   altrimenti aggiorna la dashboard: attende il Wi-Fi, chiama
   `local/fetch-dashboard.sh`, e disegna con `eips`;
4. **aspetta 10 secondi** — l'unica finestra utile per interromperlo;
5. scrive la durata sull'RTC e sospende in RAM con `echo mem > /sys/power/state`.

Due comportamenti che contano per come e' scritta la nostra configurazione:

- **Se il fetch esce con codice diverso da zero, lo schermo non viene toccato.**
  Per questo `fetch-dashboard.sh` ritenta e poi fallisce invece di scrivere un
  file vuoto: meglio una dashboard vecchia che un pannello bianco.
- **Un refresh completo ogni `FULL_DISPLAY_REFRESH_RATE` aggiornamenti
  parziali.** I parziali non fanno lampeggiare lo schermo ma accumulano
  ghosting; il completo lo azzera.

## Installazione

Servono jailbreak, USBNetwork e Wi-Fi gia' configurati.

```sh
# 1. Scarica il runtime. L'archivio e' un .tgz che si espande piatto.
mkdir -p kindle-dash
curl -sSL "$(curl -sSL https://api.github.com/repos/pascalw/kindle-dash/releases/latest \
  | grep browser_download_url | cut -d'"' -f4)" | tar xz -C kindle-dash

# 2. Sovrascrivi la configurazione di esempio con la nostra
cp kindle/local/env.sh             kindle-dash/local/env.sh
cp kindle/local/fetch-dashboard.sh kindle-dash/local/fetch-dashboard.sh

# 3. Copia sul Kindle (USBNetwork attivo, cavo collegato)
rsync -vr kindle-dash/ root@192.168.15.244:/mnt/us/dashboard

# 4. Ripristina i permessi di esecuzione, che il transito puo' perdere
ssh root@192.168.15.244 'chmod +x /mnt/us/dashboard/*.sh \
  /mnt/us/dashboard/local/*.sh /mnt/us/dashboard/xh /mnt/us/dashboard/next-wakeup'
```

In alternativa al punto 3, il Kindle collegato come normale chiavetta USB
espone `/mnt/us` come disco: puoi copiare la cartella `dashboard` col Finder e
usare SSH solo per i comandi.

`DASH_URL` in `fetch-dashboard.sh` punta gia' al branch `output` del
repository. Va cambiato solo se rinomini il repository.

### Se l'SSH va in timeout con USBNetwork attivo

USBNetwork **non fa da server DHCP**. macOS collega l'interfaccia (compare come
`RNDIS/Ethernet Gadget`), chiede un indirizzo, non riceve risposta e dopo il
timeout ripiega su un link-local `169.254.x.x`. A quel punto non esiste alcuna
rotta verso `192.168.15.0/24`, quindi i pacchetti per il Kindle escono dal
Wi-Fi verso internet e muoiono lì:

```sh
ifconfig en8 | grep inet          # inet 169.254.243.126  ← sintomo
route -n get 192.168.15.244       # interface: en0        ← esce dal Wi-Fi
```

L'indirizzo host della subnet va messo a mano:

```sh
sudo ifconfig en8 192.168.15.201 netmask 255.255.255.0
```

Il nome dell'interfaccia si ricava con:

```sh
networksetup -listallhardwareports | grep -A1 "Ethernet Gadget"
```

Va rifatto a ogni riconnessione del cavo — `install.sh` se ne accorge da solo e
stampa il comando giusto. **Non assegnare un gateway** su questa interfaccia:
si trova sopra il Wi-Fi nell'ordine dei servizi di rete e diventerebbe la rotta
di default, lasciandoti senza internet.

## Prova in modalita' debug

Non lanciare `start.sh` come prima cosa: con `DEBUG=true` il ciclo resta in
primo piano, stampa ogni comando e **usa `sleep` invece di sospendere**, quindi
il dispositivo resta raggiungibile via SSH e puoi fermarlo con Ctrl-C.

```sh
ssh root@192.168.15.244
cd /mnt/us/dashboard

# Prima il solo download, senza toccare lo schermo
./local/fetch-dashboard.sh /tmp/test.png && echo OK && ls -l /tmp/test.png
./xh --version                    # deve girare: e' un binario ARM statico

# Poi il disegno
eips -f -g /tmp/test.png

# Infine il ciclo completo, in primo piano
DEBUG=true ./start.sh
```

Se l'immagine appare **deformata o schiacciata**, il PNG non e' in scala di
grigi: `eips` accetta solo grayscale a 8 bit senza canale alpha. Dal lato
generatore il controllo e' automatico (`make inspect`).

## Avvio vero

```sh
ssh root@192.168.15.244 /mnt/us/dashboard/start.sh
```

Parte in background, scrive su `/mnt/us/dashboard/logs/dash.log`, e dopo una
decina di secondi il dispositivo si sospende. Da li' in poi si sveglia da solo
ai minuti :15 e :45.

Per avviarlo dal menu invece che da SSH, copia `KUAL/kindle-dash` dal
[repository di kindle-dash](https://github.com/pascalw/kindle-dash/tree/master/KUAL)
in `/mnt/us/extensions` — non e' incluso nella release.

## Fermarlo e riprendersi il Kindle

```sh
ssh root@192.168.15.244
/mnt/us/dashboard/stop.sh        # ferma il ciclo
/etc/init.d/framework start      # riaccende il lettore di ebook
```

`stop.sh` da solo lascia lo schermo congelato e il framework spento: senza il
secondo comando sembra che il Kindle sia morto. In caso di dubbio, un riavvio
(power button tenuto premuto ~20 secondi) rimette tutto a posto.

Il momento buono per intercettarlo e' la finestra di 10 secondi prima della
sospensione. Se lo manchi, il dispositivo torna raggiungibile solo al risveglio
successivo — al massimo 30 minuti dopo.

## Consumi

Con aggiornamento ogni 30 minuti e sospensione in RAM tra un refresh e l'altro,
l'autonomia attesa e' nell'ordine delle settimane. Per allungarla, limita
`REFRESH_SCHEDULE` alle ore in cui guardi davvero lo schermo, per esempio
`"15,45 7-23 * * *"`.

Attenzione: alzare l'intervallo oltre `SLEEP_SCREEN_INTERVAL` (3600 s) fa
comparire la schermata "kindle is sleeping" al posto della dashboard. Se metti
una pausa notturna e vuoi che resti visibile il meteo, alza anche quella
soglia.
