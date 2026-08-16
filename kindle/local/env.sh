#!/usr/bin/env sh
# Configurazione kindle-dash per k4-weather.
# Va copiata in /mnt/us/dashboard/local/env.sh sul Kindle.

export WIFI_TEST_IP=${WIFI_TEST_IP:-1.1.1.1}

# Il workflow genera l'immagine ai minuti :00 e :30, ma il cron di GitHub
# Actions arriva con 5-20 minuti di ritardo. Svegliandoci a :15 e :45 diamo
# alla generazione un margine di 15 minuti e scarichiamo quasi sempre
# l'immagine appena pubblicata.
export REFRESH_SCHEDULE=${REFRESH_SCHEDULE:-"15,45 * * * *"}

export TIMEZONE=${TIMEZONE:-"Europe/Rome"}

# Refresh completo ogni 4 aggiornamenti parziali: senza, il ghosting dell'e-ink
# diventa visibile dopo poche ore di aggiornamenti parziali.
export FULL_DISPLAY_REFRESH_RATE=${FULL_DISPLAY_REFRESH_RATE:-4}

# Aggiornando ogni 30 minuti non si raggiunge mai un'ora di attesa, quindi la
# schermata "kindle is sleeping" non compare. Alzalo solo se limiti il
# REFRESH_SCHEDULE alle sole ore diurne.
export SLEEP_SCREEN_INTERVAL=3600

export LOW_BATTERY_REPORTING=${LOW_BATTERY_REPORTING:-true}
export LOW_BATTERY_THRESHOLD_PERCENT=10
