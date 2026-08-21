#!/usr/bin/env sh
# The location list, as the Kindle sees it. Sourced, never run.
# Goes to /mnt/us/dashboard/local/locations.sh on the Kindle.
#
# Everything here reads two things and writes one:
#
#   cache/locations.txt   the manifest CI published, one record per line:
#                         id <TAB> image <TAB> name
#   cache/<id>.png        the images, downloaded ahead of being asked for
#   state/location        the id on screen now, which survives a reboot
#
# The id is what is stored, never a position in the list. Reordering the list
# in config.yaml then costs nothing, and removing a location leaves a state
# file pointing at something that no longer exists — which `loc_current`
# notices and corrects, instead of silently showing a different place.

# The caller is in $DASH_DIR/local/, so its parent is the installation.
DASH_DIR=${DASH_DIR:-$(cd "$(dirname "$0")/.." && pwd)}

LOC_CACHE=${LOC_CACHE:-$DASH_DIR/cache}
LOC_MANIFEST=${LOC_MANIFEST:-$LOC_CACHE/locations.txt}
LOC_STATE=${LOC_STATE:-$DASH_DIR/state/location}
LOC_DASH_PNG=${LOC_DASH_PNG:-$DASH_DIR/dash.png}
LOC_DRAW=${LOC_DRAW:-$DASH_DIR/local/draw.sh}

# Internals are prefixed `_loc_`: this file is sourced, so every variable it
# sets lands in the caller's shell, and a bare `id` or `first` would quietly
# overwrite one of theirs mid-loop.

# ------------------------------------------------------------------ the list

# Every id in the manifest, in the published order — but only those we actually
# hold an image for. A location whose download has never succeeded is not in
# the cycle: a button press that led to a blank screen would look like a crash.
loc_ids() {
  [ -f "$LOC_MANIFEST" ] || return 1
  while IFS="	" read -r _loc_id _loc_image _loc_name; do
    [ -n "$_loc_id" ] || continue
    [ -s "$LOC_CACHE/$_loc_id.png" ] && echo "$_loc_id"
  done < "$LOC_MANIFEST"
}

# One field of one record. `$2` is the field number as `cut` counts them.
loc_field() {
  [ -f "$LOC_MANIFEST" ] || return 1
  # The name is the last field and may contain spaces, which is why the
  # manifest is tab-separated and read with a literal tab as IFS.
  while IFS="	" read -r _loc_id _loc_image _loc_name; do
    if [ "$_loc_id" = "$1" ]; then
      case "$2" in
        image) echo "$_loc_image" ;;
        name)  echo "$_loc_name" ;;
      esac
      return 0
    fi
  done < "$LOC_MANIFEST"
  return 1
}

loc_count() {
  loc_ids | wc -l | tr -d ' '
}

# ----------------------------------------------------------------- the state

# The location on screen. Falls back to the first available one whenever the
# stored id is missing, empty, or no longer in the manifest — the three ways a
# state file goes stale, and all three are recoverable without asking anyone.
loc_current() {
  _loc_first=""
  _loc_wanted=""
  [ -f "$LOC_STATE" ] && _loc_wanted=$(cat "$LOC_STATE" 2>/dev/null)

  for _loc_id in $(loc_ids); do
    [ -n "$_loc_first" ] || _loc_first=$_loc_id
    [ "$_loc_id" = "$_loc_wanted" ] && { echo "$_loc_id"; return 0; }
  done

  [ -n "$_loc_first" ] || return 1
  echo "$_loc_first"
}

loc_set() {
  mkdir -p "$(dirname "$LOC_STATE")" 2>/dev/null
  # Written to one side and moved into place: a half-written state file would
  # be read back as an unknown id at the next wake-up.
  echo "$1" > "$LOC_STATE.new" && mv "$LOC_STATE.new" "$LOC_STATE"
}

# ---------------------------------------------------------------- the cycle

# The id `$2` steps away from `$1`, wrapping around. `$2` is +1 or -1.
#
# Written as a walk over the list rather than as arithmetic on an index,
# because the list is what exists: the position of an id is derived every time
# and never stored, so it cannot go out of date.
loc_step() {
  _loc_from=$1
  _loc_direction=$2

  _loc_all=$(loc_ids)
  [ -n "$_loc_all" ] || return 1

  _loc_previous=""
  _loc_found=""
  _loc_before=""
  _loc_after=""
  _loc_first=""
  _loc_last=""

  for _loc_id in $_loc_all; do
    [ -n "$_loc_first" ] || _loc_first=$_loc_id
    if [ -n "$_loc_found" ] && [ -z "$_loc_after" ]; then
      _loc_after=$_loc_id
    fi
    if [ "$_loc_id" = "$_loc_from" ]; then
      _loc_found=$_loc_id
      _loc_before=$_loc_previous
    fi
    _loc_previous=$_loc_id
    _loc_last=$_loc_id
  done

  # An id that is not in the list any more: treat the move as a fresh start
  # rather than refusing it, or a stale state file would jam the buttons.
  [ -n "$_loc_found" ] || { echo "$_loc_first"; return 0; }

  if [ "$_loc_direction" = "-1" ]; then
    [ -n "$_loc_before" ] && echo "$_loc_before" || echo "$_loc_last"
  else
    [ -n "$_loc_after" ] && echo "$_loc_after" || echo "$_loc_first"
  fi
}

# ---------------------------------------------------------------- the screen

# Put a location on screen: the cached image becomes the one kindle-dash
# considers current, and `draw.sh` paints it with the indoor temperature on top
# exactly as it does after a download.
#
# Always a full refresh (`-f`): a location change replaces every pixel on the
# panel, and a partial update would leave the previous place ghosting through.
loc_draw() {
  [ -s "$LOC_CACHE/$1.png" ] || return 1

  cp "$LOC_CACHE/$1.png" "$LOC_DASH_PNG.new" || return 1
  mv "$LOC_DASH_PNG.new" "$LOC_DASH_PNG" || return 1

  "$LOC_DRAW" -f -g "$LOC_DASH_PNG"
}

# Move to a location and record it, but only record it once it is on screen:
# a state file that ran ahead of the panel would survive a power cut and show
# the wrong name after the next boot.
loc_go() {
  loc_draw "$1" || return 1
  loc_set "$1"
}
