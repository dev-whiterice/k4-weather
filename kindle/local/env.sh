#!/usr/bin/env sh
# kindle-dash configuration for k4-weather.
# Goes to /mnt/us/dashboard/local/env.sh on the Kindle.
#
# Every value keeps a ${VAR:-default} form so it can be overridden from the
# environment without editing the file on the device.

export WIFI_TEST_IP=${WIFI_TEST_IP:-1.1.1.1}

# The workflow generates the image at :00 and :30, but the GitHub Actions cron
# runs 5-20 minutes late. Waking at :15 and :45 gives generation a 15-minute
# head start, so we almost always download the image just published.
export REFRESH_SCHEDULE=${REFRESH_SCHEDULE:-"15,45 * * * *"}

export TIMEZONE=${TIMEZONE:-"Europe/Rome"}

# One full refresh every 4 partial updates: without it, e-ink ghosting becomes
# visible after a few hours of partial updates.
export FULL_DISPLAY_REFRESH_RATE=${FULL_DISPLAY_REFRESH_RATE:-4}

# Refreshing every 30 minutes we never reach an hour of waiting, so the
# "kindle is sleeping" screen never appears. Raise this only if you restrict
# REFRESH_SCHEDULE to daytime hours.
export SLEEP_SCREEN_INTERVAL=3600

export LOW_BATTERY_REPORTING=${LOW_BATTERY_REPORTING:-true}
export LOW_BATTERY_THRESHOLD_PERCENT=10

# ---------------------------------------------------------- indoor temperature
# The Kindle draws its own temperature reading on top of the image it downloads:
# the sensor is here, the image is built in the cloud. false makes local/draw.sh
# a plain wrapper around eips and leaves the dashboard exactly as it arrives.
export INDOOR_TEMP=${INDOOR_TEMP:-true}

# There is no ambient sensor on this device: the reading comes from the battery
# gas gauge and lands a few degrees above the room, because the Kindle warms its
# own pack. Measure the difference once, with the panel already hanging where it
# lives and after a few hours of the normal refresh cycle:
#
#     /mnt/us/dashboard/local/indoor-temp.sh --raw     # e.g. 23.4
#
# then set the offset to (what a thermometer next to it says) minus that value.
# Redo it if you move the panel, and not straight after a charge: the pack takes
# hours to come back down. Details in kindle/README.md.
export INDOOR_TEMP_OFFSET=${INDOOR_TEMP_OFFSET:-0}

# Where the reading comes from, and the unit it answers in (F, C, dC, mC).
# `indoor-temp.sh --probe` lists what this device actually exposes.
export INDOOR_TEMP_CMD=${INDOOR_TEMP_CMD:-"gasgauge-info -k"}
export INDOOR_TEMP_UNIT=${INDOOR_TEMP_UNIT:-F}

# Outside this range the sensor is broken, not the room: nothing is drawn and
# the dash printed on the image stays.
export INDOOR_TEMP_MIN=${INDOOR_TEMP_MIN:--10}
export INDOOR_TEMP_MAX=${INDOOR_TEMP_MAX:-50}

# Where it goes, on the 12x20 px character grid of eips (50 columns by 40 rows
# on this panel). Must match INDOOR_SLOT_COL/ROW/CHARS in
# src/k4weather/model.py, which is where the layout leaves the hole.
export INDOOR_TEMP_COL=${INDOOR_TEMP_COL:-4}
export INDOOR_TEMP_ROW=${INDOOR_TEMP_ROW:-38}
export INDOOR_TEMP_CHARS=${INDOOR_TEMP_CHARS:-4}
