# Messa in servizio

Procedura completa dal repository al Kindle appeso al muro.

## Perche' il repository e' pubblico

Il Kindle 4 scarica l'immagine con un client HTTP minimale e non ha modo di
autenticarsi in sicurezza: un token scritto in chiaro su una partizione FAT non
protetta e' peggio del problema che risolve. La sorgente deve quindi essere
leggibile senza credenziali.

C'e' anche una ragione di costo, che da sola decide la questione: 48 esecuzioni
al giorno da un paio di minuti l'una fanno circa **3.000 minuti di Actions al
mese**, contro i 2.000 inclusi nel piano gratuito per i repository privati. Sui
repository pubblici Actions non ha limiti.

```
k4-weather (pubblico)
  main    codice, config, workflow
  output  dashboard.png  ──►  raw.githubusercontent.com  ──►  Kindle
```

Il branch `output` viene riscritto a ogni run con un force push di un singolo
commit: non accumula storia e resta di dimensione costante.

> Il repository e' pubblico: **l'immagine e il codice sono leggibili da
> chiunque**, e la dashboard riporta il nome della localita. Diventano pubblici
> anche i metadati dei commit, indirizzo email dell'autore compreso.

---

## 1. Rendi pubblico il repository

```sh
gh repo edit dev-whiterice/k4-weather --visibility public \
  --accept-visibility-change-consequences
```

## 2. Push del codice

```sh
git add -A
git commit -m "dashboard meteo per Kindle 4"
git push origin main
```

Il push su `main` fa gia' partire il workflow: [`dashboard.yml`](../.github/workflows/dashboard.yml)
si attiva sia a orario sia quando cambiano `src/`, `config.yaml` o il workflow
stesso.

## 3. Verifica la prima immagine

```sh
gh run watch --repo dev-whiterice/k4-weather

curl -sI https://raw.githubusercontent.com/dev-whiterice/k4-weather/output/dashboard.png | head -1
# HTTP/2 200
```

Da qui in poi il workflow riparte da solo ai minuti :00 e :30.

## 4. Tieni vivo lo scheduler (consigliato)

GitHub disattiva i workflow schedulati dopo **60 giorni senza attivita** sul
repository, e i commit fatti con il token automatico **non contano**. Senza
rimedio, la dashboard si congela dopo due mesi.

Crea un PAT fine-grained su
**github.com/settings/personal-access-tokens/new**:

| Campo | Valore |
|---|---|
| Token name | `k4-weather-publish` |
| Resource owner | `dev-whiterice` |
| Repository access | *Only select repositories* → `k4-weather` |
| Permissions → Repository → **Contents** | **Read and write** |

e salvalo come secret:

```sh
gh secret set PUBLISH_TOKEN --repo dev-whiterice/k4-weather
```

Il workflow lo usa al posto del token automatico e i commit risultano tuoi.
Segnati la scadenza in calendario: e' l'unica del progetto, e alla scadenza la
pubblicazione si ferma senza preavviso.

### Pagina di anteprima (opzionale)

Il workflow pubblica anche un `index.html`. In *Settings → Pages*, scegliendo
branch `output` e cartella `/`, ottieni
`https://dev-whiterice.github.io/k4-weather/` per controllare la dashboard dal
telefono. Il Kindle continua a usare `raw.githubusercontent.com`: ha una cache
piu corta e una catena di redirect in meno.

---

## 5. Kindle

Prerequisiti una tantum: jailbreak del Kindle 4 NT, KUAL, USBNetwork per avere
SSH, Wi-Fi configurato. Riferimento: [wiki di
MobileRead](https://wiki.mobileread.com/wiki/Kindle4NTHacking).

```sh
# Runtime: kindle-dash gestisce wifi, TLS, sospensione e sveglia da RTC.
# L'archivio e' un .tgz che si espande piatto, quindi la cartella va creata.
mkdir -p kindle-dash
curl -sSL "$(curl -sSL https://api.github.com/repos/pascalw/kindle-dash/releases/latest \
  | grep browser_download_url | cut -d'"' -f4)" | tar xz -C kindle-dash

# La nostra configurazione: URL gia' impostato, non serve modificare nulla
cp kindle/local/env.sh             kindle-dash/local/env.sh
cp kindle/local/fetch-dashboard.sh kindle-dash/local/fetch-dashboard.sh

rsync -vr kindle-dash/ root@192.168.15.244:/mnt/us/dashboard
ssh root@192.168.15.244 'chmod +x /mnt/us/dashboard/*.sh /mnt/us/dashboard/local/*.sh \
  /mnt/us/dashboard/xh /mnt/us/dashboard/next-wakeup'
```

Prima di lanciarlo davvero, provalo in modalita' debug: resta in primo piano,
non sospende il dispositivo e stampa tutto (vedi
[`kindle/README.md`](../kindle/README.md#prova-in-modalita-debug)).

Il Kindle si sospende dopo 10-15 secondi e si risveglia ai minuti :15 e :45,
sfasato di 15 minuti rispetto alla generazione per assorbire il ritardo del
cron di GitHub Actions.

### Verifica sul dispositivo

```sh
ssh kindle
/mnt/us/dashboard/local/fetch-dashboard.sh /tmp/test.png && echo OK
eips -f -g /tmp/test.png
```

---

## Se qualcosa non va

| Sintomo | Causa e rimedio |
|---|---|
| `curl` sull'URL raw da 404 | Il branch `output` non esiste ancora: il workflow non e' mai andato a buon fine |
| Immagine **deformata o schiacciata** sul Kindle | Il PNG non e' in scala di grigi. `make inspect` lo intercetta prima della pubblicazione |
| `fetch-dashboard.sh` esce in errore | Wi-Fi assente o URL sbagliato. Lo schermo conserva l'ultima immagine buona invece di sbiancarsi |
| Lo schermo mostra un orario fermo da giorni | Scheduler disattivato dopo 60 giorni di inattivita: vedi il punto 4 |
| Scritta *dati non aggiornati* nel piede | L'immagine e' fresca ma l'osservazione di Open-Meteo ha piu di 90 minuti |
| Ghosting sullo schermo | `FULL_DISPLAY_REFRESH_RATE` in `kindle/local/env.sh`: abbassalo per fare refresh completi piu spesso |
| Batteria che cala troppo in fretta | Limita `REFRESH_SCHEDULE` alle ore diurne, per esempio `"15,45 7-23 * * *"` |

## Manutenzione

- **Cambiare localita**: modifica `location` in `config.yaml` e fai push. Il
  workflow riparte al push e l'immagine si aggiorna in pochi minuti.
- **Ritoccare il design**: `make preview`, poi apri `out/dashboard.html` nel
  browser. Dopo aver toccato le icone, `make icons`.
- **Scadenza del PAT**: unica scadenza del progetto, vedi il punto 4.
