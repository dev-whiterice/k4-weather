#!/usr/bin/env sh
# Downloads the dashboard and writes it to "$1", as kindle-dash expects.
# Goes to /mnt/us/dashboard/local/fetch-dashboard.sh on the Kindle.
#
# The stock curl and wget on the Kindle 4 do not speak modern TLS: we use `xh`,
# the static client that kindle-dash ships in its own release.

# The `output` branch of the repository, where the workflow publishes the image.
# The Kindle has no way to authenticate: the source must be readable without a
# token, which is why the repository is public.
DASH_URL="https://raw.githubusercontent.com/dev-whiterice/k4-weather/output/dashboard.png"

XH="$(dirname "$0")/../xh"
TARGET="$1"
TMP="${TARGET}.part"
ATTEMPTS=3

i=1
while [ "$i" -le "$ATTEMPTS" ]; do
  # The cache-busting parameter keeps the CDN in front of raw.githubusercontent
  # from serving the previous image.
  #
  # Download to a scratch file first: a half-written PNG must never reach
  # "$TARGET", or eips would draw a torn image.
  if "$XH" -d -q --follow -o "$TMP" get "${DASH_URL}?t=$(date +%s)" && [ -s "$TMP" ]; then
    mv "$TMP" "$TARGET"
    exit 0
  fi
  rm -f "$TMP"
  sleep 5
  i=$((i + 1))
done

# Exiting non-zero without touching "$TARGET" makes kindle-dash leave the last
# good image on screen, which beats a blank panel.
echo "k4-weather: download failed after ${ATTEMPTS} attempts" >&2
exit 1
