#!/usr/bin/env sh
# Downloads every location and writes the current one to "$1", as kindle-dash
# expects. Goes to /mnt/us/dashboard/local/fetch-dashboard.sh on the Kindle.
#
# The stock curl and wget on the Kindle 4 do not speak modern TLS: we use `xh`,
# the static client that kindle-dash ships in its own release.
#
# Why every location and not just the one on screen: switching has to be
# instant and has to work with the Wi-Fi off. The panel is asleep 29 minutes
# out of 30, and waking the radio to answer a button press would mean ten
# seconds of a frozen screen for each press. Five images are about a hundred
# kilobytes — next to nothing beside the cost of associating with the access
# point, which we are paying anyway.

DIR=$(dirname "$0")
DASH_DIR=${DASH_DIR:-$(cd "$DIR/.." && pwd)}
# shellcheck disable=SC1091
. "$DIR/locations.sh"

# GitHub Pages, served from the `output` branch where the workflow publishes.
# The Kindle has no way to authenticate: the source must be readable without a
# token, which is why the repository is public.
#
# Not raw.githubusercontent.com, which enforces an anti-scraping rate limit per
# IP address and answers 429 once it trips — the whole address, not the
# account, so a browser open on the same connection spends the same budget the
# Kindle needs. Pages exists to serve assets and applies no such limit.
BASE_URL=${BASE_URL:-"https://dev-whiterice.github.io/k4-weather"}

XH=${XH:-$DIR/../xh}
TARGET=$1
ATTEMPTS=${ATTEMPTS:-3}

# Download $1 into $2, atomically. No cache-busting parameter: it would turn
# every poll into a unique URL, so every request would reach the origin and
# none would ever be absorbed by the CDN. It buys no freshness either — Pages
# caches for 10 minutes and the Kindle wakes every 30, so the entry from the
# previous poll has always expired by the time this runs.
download() {
  url=$1
  out=$2
  tmp="$out.part"

  i=1
  while [ "$i" -le "$ATTEMPTS" ]; do
    # `</dev/null` is not decoration, and leaving it out cost this project four
    # locations out of five.
    #
    # xh follows httpie: when its standard input is not a terminal, it takes
    # whatever is there as the body of the request. This function is called
    # from inside `while read ... done < "$LOC_MANIFEST"`, so its standard
    # input IS the manifest — xh swallowed the rest of the file, `read` found
    # end of file, and the loop ended after its first line. Every refresh
    # downloaded the first location and silently skipped the others; the panel
    # then had exactly one image, and the page buttons had nothing to move
    # between.
    #
    # It fails this way whether the network works or not, which is what made it
    # so hard to see: it looks exactly like four downloads that did not happen.
    if "$XH" -d -q --follow -o "$tmp" get "$url" </dev/null && [ -s "$tmp" ]; then
      mv "$tmp" "$out"
      return 0
    fi
    rm -f "$tmp"

    # Progressive backoff, and none after the last attempt. A flat 5s retry is
    # the wrong move against a rate limit: it spends three times the requests
    # inside the window that is already refusing them.
    [ "$i" -lt "$ATTEMPTS" ] && sleep $((i * 15))
    i=$((i + 1))
  done
  return 1
}

mkdir -p "$LOC_CACHE"

# ---------------------------------------------------------------- the manifest
#
# A failed manifest download is not fatal while we still hold one: the list of
# locations changes when somebody edits config.yaml, which is roughly never,
# and the images are what go stale. Only a device that has never had one has
# nothing to work from.
if download "$BASE_URL/locations.txt" "$LOC_CACHE/locations.txt.new"; then
  if [ -s "$LOC_CACHE/locations.txt.new" ]; then
    mv "$LOC_CACHE/locations.txt.new" "$LOC_MANIFEST"
  else
    rm -f "$LOC_CACHE/locations.txt.new"
  fi
elif [ ! -f "$LOC_MANIFEST" ]; then
  echo "k4-weather: no locations.txt, and none cached" >&2
  exit 1
fi

# ------------------------------------------------------------------ the images

downloaded=0
# Read on file descriptor 3 rather than on standard input, so that the list
# being walked cannot be eaten by anything called from inside the walk. `xh`
# did exactly that — see `download` above — and the belt goes here so that the
# next command added to this loop cannot repeat it.
while IFS="	" read -r id image name <&3; do
  [ -n "$id" ] || continue
  if download "$BASE_URL/$image" "$LOC_CACHE/$id.png.new"; then
    mv "$LOC_CACHE/$id.png.new" "$LOC_CACHE/$id.png"
    downloaded=$((downloaded + 1))
  else
    rm -f "$LOC_CACHE/$id.png.new"
    # Not fatal on its own: CI skips a location whose data did not arrive, and
    # the copy already in the cache is a few hours old at worst. It only
    # matters if it is the one on screen, which the final check below catches.
    echo "k4-weather: ${id} not downloaded, keeping the cached copy" >&2
  fi
done 3< "$LOC_MANIFEST"

# Images for locations that are no longer configured. Left behind they would
# stay in the cycle for ever, since the cycle is built from what is on disk.
for cached in "$LOC_CACHE"/*.png; do
  [ -e "$cached" ] || continue
  cached_id=$(basename "$cached" .png)
  loc_field "$cached_id" image >/dev/null || {
    echo "k4-weather: ${cached_id} is no longer configured, dropping it" >&2
    rm -f "$cached"
  }
done

# ----------------------------------------------------------------- the screen

current=$(loc_current) || {
  echo "k4-weather: no usable image after ${downloaded} download(s)" >&2
  exit 1
}

# Exiting non-zero without touching "$TARGET" makes kindle-dash leave the last
# good image on screen, which beats a blank panel.
cp "$LOC_CACHE/$current.png" "$TARGET.part" || exit 1
mv "$TARGET.part" "$TARGET" || exit 1

# Recorded only now: `loc_current` may have fallen back to another location
# because the stored one lost its image, and the state file has to follow what
# is actually on the panel.
loc_set "$current"
exit 0
