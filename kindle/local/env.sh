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
