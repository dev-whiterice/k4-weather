#!/usr/bin/env sh
# Downloads the dashboard and writes it to "$1", as kindle-dash expects.
# Goes to /mnt/us/dashboard/local/fetch-dashboard.sh on the Kindle.
#
# The stock curl and wget on the Kindle 4 do not speak modern TLS: we use `xh`,
# the static client that kindle-dash ships in its own release.

# GitHub Pages, served from the `output` branch where the workflow publishes the
# image. The Kindle has no way to authenticate: the source must be readable
# without a token, which is why the repository is public.
#
# Not raw.githubusercontent.com, which enforces an anti-scraping rate limit per
# IP address and answers 429 once it trips — the whole address, not the account,
# so a browser open on the same connection spends the same budget the Kindle
# needs. Pages exists to serve assets and applies no such limit.
DASH_URL="https://dev-whiterice.github.io/k4-weather/dashboard.png"

XH="$(dirname "$0")/../xh"
TARGET="$1"
TMP="${TARGET}.part"
ATTEMPTS=3

i=1
while [ "$i" -le "$ATTEMPTS" ]; do
  # No cache-busting parameter: it would turn every poll into a unique URL, so
  # every request would reach the origin and none would ever be absorbed by the
  # CDN. It buys no freshness either — Pages caches for 10 minutes and the
  # Kindle wakes up every 30 (see env.sh), so the entry from the previous poll
  # has always expired by the time this runs.
  #
  # Download to a scratch file first: a half-written PNG must never reach
  # "$TARGET", or eips would draw a torn image.
  if "$XH" -d -q --follow -o "$TMP" get "$DASH_URL" && [ -s "$TMP" ]; then
    mv "$TMP" "$TARGET"
    exit 0
  fi
  rm -f "$TMP"

  # Progressive backoff, and none after the last attempt. A flat 5s retry is
  # the wrong move against a rate limit: it spends three times the requests
  # inside the window that is already refusing them.
  [ "$i" -lt "$ATTEMPTS" ] && sleep $((i * 15))
  i=$((i + 1))
done

# Exiting non-zero without touching "$TARGET" makes kindle-dash leave the last
# good image on screen, which beats a blank panel.
echo "k4-weather: download failed after ${ATTEMPTS} attempts" >&2
exit 1
