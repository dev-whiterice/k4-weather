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

# ------------------------------------------------------------ location switching
# The panel shows one location at a time and the page buttons walk through the
# list CI publishes. All of it is off with INTERACT=false, which also gives the
# upstream behaviour back: the window below becomes the plain ten-second sleep
# kindle-dash does before suspending.
export INTERACT=${INTERACT:-true}

# How long the panel listens after being woken up by hand, and how much each
# press adds to that. Walking five locations must not need five presses inside
# one shrinking window.
export INTERACT_SECONDS=${INTERACT_SECONDS:-25}
export INTERACT_EXTEND=${INTERACT_EXTEND:-15}

# A full refresh when the listening window opens, as the only feedback that the
# device is awake and paying attention. It costs one flash of the screen and
# leaves nothing on the image to clean off afterwards.
export INTERACT_FLASH=${INTERACT_FLASH:-true}

# Which device the buttons arrive on, and the codes they send. Measured on this
# Kindle 4 with kindle/tools/keytest.sh — they are not the standard input.h
# meanings and are not worth guessing:
#
#   191  page forward, right side      104  page forward, left side
#   109  page back, right side         193  page back, left side
#
# Both sides are accepted for each direction, so the panel answers whichever
# thumb is on it. event0 is "tequila-keypad"; the 5-way is event1 (105 left,
# 106 right) if you would rather use that.
export KEY_DEVICE=${KEY_DEVICE:-/dev/input/event0}
export KEY_NEXT=${KEY_NEXT:-"191 104"}
export KEY_PREV=${KEY_PREV:-"109 193"}

# How much shorter than the alarm counts as "somebody woke it up" rather than
# "the clock did". Generous on purpose: the RTC has second resolution and the
# resume itself takes a moment, so a scheduled wake-up can land slightly early.
export EARLY_WAKE_MARGIN=${EARLY_WAKE_MARGIN:-10}

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

# What draws the number. `eips` has exactly one font size, 12x20 px per
# character, which is too small to read a room temperature from a doorway:
# fbink draws the same string in the same place with its bitmap font enlarged
# INDOOR_TEMP_SCALE times, 32x64 px per character at 4. It is a static binary
# that is not part of the device — put it in /mnt/us/dashboard/fbink and it is
# used, leave it out and local/draw.sh falls back to eips. See kindle/README.md.
export INDOOR_TEMP_FBINK=${INDOOR_TEMP_FBINK:-/mnt/us/dashboard/fbink}
export INDOOR_TEMP_SCALE=${INDOOR_TEMP_SCALE:-4}

# Where it goes: the top left corner of the blank, in pixels of the image, and
# how many characters wide that blank is (three, for readings down to -10).
# Must match INDOOR_SLOT_X/Y, INDOOR_SCALE and INDOOR_SLOT_CHARS in
# src/k4weather/model.py, which is where the layout leaves the hole. The eips
# fallback derives its own cell coordinates from these four numbers.
export INDOOR_TEMP_X=${INDOOR_TEMP_X:-468}
export INDOOR_TEMP_Y=${INDOOR_TEMP_Y:-118}
export INDOOR_TEMP_CHARS=${INDOOR_TEMP_CHARS:-3}
