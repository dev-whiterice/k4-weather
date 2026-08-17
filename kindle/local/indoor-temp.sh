#!/usr/bin/env sh
# Reads the on-board temperature sensor and prints the calibrated indoor
# temperature, in whole degrees Celsius. Goes to
# /mnt/us/dashboard/local/indoor-temp.sh on the Kindle.
#
# The Kindle 4 has no ambient sensor. The only thermometer on board is the one
# inside the battery gas gauge, and it reads the pack, not the room: it sits
# above room temperature, because the device warms its own battery, and it lags
# behind it, because that battery has thermal mass. As a room thermometer it is
# usable only with an offset measured in place — INDOOR_TEMP_OFFSET in env.sh —
# and only because this panel spends almost all of its time suspended, which
# keeps the self-heating small and, above all, constant.
#
#     indoor-temp.sh              21        calibrated, this is what gets drawn
#     indoor-temp.sh --raw        23.4      uncalibrated °C, to measure the offset
#     indoor-temp.sh --debug      every step of the conversion
#     indoor-temp.sh --probe      what this particular device exposes
#
# Prints nothing and exits 1 when there is no usable reading: the caller then
# leaves in place the dash the dashboard already carries, which is honest.

# The sensor, and the unit it answers in: F, C, dC (tenths), mC (thousandths).
# gasgauge-info is the Lab126 utility kindle-dash already uses for the battery
# level, so it is known to be on the device; -k is its temperature flag and
# answers in whole degrees Fahrenheit. If `--probe` finds a sysfs file with a
# finer resolution, point these two at it instead.
CMD=${INDOOR_TEMP_CMD:-gasgauge-info -k}
UNIT=${INDOOR_TEMP_UNIT:-F}

# Degrees Celsius, decimal and signed, added to every reading.
OFFSET=${INDOOR_TEMP_OFFSET:-0}

# A reading outside this range is the sensor failing, not the room: better no
# number at all than a wrong one on a wall.
MIN=${INDOOR_TEMP_MIN:--10}
MAX=${INDOOR_TEMP_MAX:-50}

# "-2.5" -> -25. One decimal is as much precision as any of these sources has,
# and tenths of a degree keep every step below in integer arithmetic, which is
# all POSIX sh can do.
to_deci() {
  value=$1
  sign=1
  case "$value" in
    -*) sign=-1; value=${value#-} ;;
    +*) value=${value#+} ;;
  esac
  case "$value" in
    *.*) whole=${value%%.*}; frac=${value#*.} ;;
    *)   whole=$value;       frac=0 ;;
  esac
  [ -n "$whole" ] || whole=0
  # A leading zero would make the shell read the number as octal.
  while [ ${#whole} -gt 1 ]; do
    case "$whole" in 0*) whole=${whole#0} ;; *) break ;; esac
  done
  frac=$(printf '%s' "${frac}0" | cut -c1)
  case "$whole$frac" in
    '' | *[!0-9]*) return 1 ;;
  esac
  echo $(( sign * (whole * 10 + frac) ))
}

# 227 -> "22.7". The sign has to be pulled out first: -227/10 truncates to -22
# and -227%10 to -7, which would print "-22.-7".
from_deci() {
  value=$1
  sign=''
  if [ "$value" -lt 0 ]; then
    sign='-'
    value=$(( - value ))
  fi
  printf '%s%d.%d\n' "$sign" $(( value / 10 )) $(( value % 10 ))
}

# $1 / $2 to the nearest integer, halves away from zero: shell division
# truncates, which would bias every conversion towards zero.
div_round() {
  if [ "$1" -ge 0 ]; then
    echo $(( ($1 + $2 / 2) / $2 ))
  else
    echo $(( ($1 - $2 / 2) / $2 ))
  fi
}

# The sensor, in tenths of a degree Celsius, uncalibrated.
read_deci() {
  # shellcheck disable=SC2086
  # Unquoted on purpose: INDOOR_TEMP_CMD is a command with its arguments.
  line=$($CMD 2>/dev/null | head -n 1)
  [ -n "$line" ] || return 1

  # The first number on the line, whatever the utility prints around it:
  # gasgauge-info answers "73 Fahrenheit", a sysfs file answers "235".
  number=$(printf '%s' "$line" |
    sed 's/[^0-9.-]*\([-0-9][0-9]*\(\.[0-9][0-9]*\)\{0,1\}\).*/\1/')
  number=$(to_deci "$number") || return 1

  case "$UNIT" in
    F | f)   div_round $(( (number - 320) * 5 )) 9 ;;
    C | c)   echo "$number" ;;
    dC | dc) div_round "$number" 10 ;;
    mC | mc) div_round "$number" 1000 ;;
    *)       return 1 ;;
  esac
}

probe() {
  echo "sensor command: $CMD"
  # shellcheck disable=SC2086
  $CMD 2>&1 | sed 's/^/    /'

  echo
  echo "sysfs candidates:"
  found=0
  # Unmatched globs stay literal, and the -r test drops them.
  for path in \
    /sys/class/power_supply/*/temp* \
    /sys/class/thermal/thermal_zone*/temp \
    /sys/devices/platform/*/temperature \
    /sys/devices/platform/*batt*/*temp* \
    /sys/devices/system/*/*/*temp*; do
    [ -r "$path" ] || continue
    echo "    $path = $(cat "$path" 2>/dev/null)"
    found=$((found + 1))
  done
  [ "$found" -gt 0 ] || echo "    (none readable)"

  echo
  raw=$(read_deci) || {
    echo "reading: FAILED — this device cannot feed the indoor temperature"
    return 1
  }
  result=$("$0" 2>/dev/null) || result="refused, outside ${MIN}..${MAX}"
  echo "reading: $(from_deci "$raw")C uncalibrated, offset ${OFFSET}C, drawn: $result"
}

case "${1:-}" in
  --probe)
    probe
    exit $?
    ;;
esac

raw=$(read_deci) || exit 1

offset=$(to_deci "$OFFSET") || offset=0
calibrated=$(( raw + offset ))
degrees=$(div_round "$calibrated" 10)

case "${1:-}" in
  --raw)
    from_deci "$raw"
    exit 0
    ;;
  --debug)
    echo "source=$CMD unit=$UNIT raw=$(from_deci "$raw")C" \
      "offset=$(from_deci "$offset")C calibrated=$(from_deci "$calibrated")C" \
      "drawn=$degrees range=$MIN..$MAX"
    ;;
esac

[ "$degrees" -ge "$MIN" ] && [ "$degrees" -le "$MAX" ] || exit 1
echo "$degrees"
