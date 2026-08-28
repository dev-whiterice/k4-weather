#!/usr/bin/env sh
# Reads the battery gauge and prints how much charge is left, in whole per
# cent. Goes to /mnt/us/dashboard/local/battery.sh on the Kindle.
#
#     battery.sh              87        this is what gets drawn
#     battery.sh --probe      what this particular device answers
#
# Prints nothing and exits 1 when there is no usable reading: the caller then
# leaves in place the dash the dashboard already carries, which is honest.
#
# The number is as old as the image it lands on — the panel wakes, draws and
# suspends again, so it is read once every refresh and never in between. That
# is the whole point of it: a battery that lasts weeks does not need watching,
# it needs a figure on the wall that says roughly where it has got to.

# gasgauge-info is the Lab126 utility kindle-dash already calls once a cycle to
# write the level into its log, so it is known to be on the device; -c is its
# capacity flag and answers "87%". Anything that prints a number between 0 and
# 100 will do — `--probe` lists what this device actually exposes.
CMD=${BATTERY_CMD:-gasgauge-info -c}

read_percent() {
  # shellcheck disable=SC2086
  # Unquoted on purpose: BATTERY_CMD is a command with its arguments.
  line=$($CMD 2>/dev/null | head -n 1)
  [ -n "$line" ] || return 1

  # The first whole number on the line, whatever the source prints around it:
  # gasgauge-info answers "87%", a sysfs file answers "87". A line with no
  # number in it comes back unchanged from sed and is caught below.
  value=$(printf '%s' "$line" | sed 's/[^0-9]*\([0-9][0-9]*\).*/\1/')
  case "$value" in
    '' | *[!0-9]*) return 1 ;;
  esac
  # A leading zero would make the shell read the number as octal.
  while [ ${#value} -gt 1 ]; do
    case "$value" in 0*) value=${value#0} ;; *) break ;; esac
  done

  # Outside this the gauge is broken, not the battery.
  [ "$value" -le 100 ] || return 1
  echo "$value"
}

probe() {
  echo "battery command: $CMD"
  # shellcheck disable=SC2086
  $CMD 2>&1 | sed 's/^/    /'

  echo
  echo "sysfs candidates:"
  found=0
  # Unmatched globs stay literal, and the -r test drops them.
  for path in \
    /sys/class/power_supply/*/capacity \
    /sys/class/power_supply/*/charge_now \
    /sys/devices/platform/*batt*/*capacity*; do
    [ -r "$path" ] || continue
    echo "    $path = $(cat "$path" 2>/dev/null)"
    found=$((found + 1))
  done
  [ "$found" -gt 0 ] || echo "    (none readable)"

  echo
  value=$(read_percent) || {
    echo "reading: FAILED — this device cannot feed the battery level"
    return 1
  }
  echo "reading: ${value}%, drawn as ${value}"
}

case "${1:-}" in
  --probe)
    probe
    exit $?
    ;;
esac

read_percent
