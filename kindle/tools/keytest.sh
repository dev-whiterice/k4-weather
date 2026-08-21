#!/usr/bin/env sh
# Finds out whether the Kindle's buttons can drive the dashboard.
#
# RUNS ON THE KINDLE, not on the Mac. Copy it over with:
#
#     ssh root@192.168.15.244 'cat > /mnt/us/keytest.sh && chmod +x /mnt/us/keytest.sh' \
#       < kindle/tools/keytest.sh
#
# Three phases, least invasive first:
#
#     /mnt/us/keytest.sh probe     # what this device exposes. Reads only.
#     /mnt/us/keytest.sh keys      # which code each button sends, while awake.
#     /mnt/us/keytest.sh wake      # whether a button wakes it from suspend.
#
# `probe` and `keys` are safe to run any time. `wake` suspends the device: it
# detaches itself, drops the SSH session with it, and leaves its answer in a
# log file to read once the device is back. There is always an RTC alarm armed
# as a safety net, so the worst case is a wait, not a brick — and holding power
# for ~20s reboots out of anything.
#
# Dependencies: dd, wc and the shell. Nothing else. This device turned out to
# have no `od`, which is why the decoder below is written the long way.

set -u

RTC=/sys/devices/platform/mxc_rtc.0/wakeup_enable
KEYPAD_WAKEUP=/sys/devices/platform/tequila-keypad/power/wakeup
LOG=/mnt/us/keytest-wake.log
TMP=/tmp/keytest
EIPS=/usr/sbin/eips

# Every input_event is 16 bytes on this 32-bit kernel: two 4-byte timeval
# fields, then type, code (2 each) and a 4-byte value. That fixed size is what
# lets plain `dd` read exactly one event at a time.
EVENT_SIZE=16
# Byte offsets inside a record. Only the low half of each field is read: key
# types, key codes and press/release values all fit in one byte, and reading
# the high halves would double the number of `dd` calls for nothing.
OFF_TYPE=8
OFF_CODE=10
OFF_VALUE=12

# A long capture (a button held down repeats) is not worth decoding in full.
MAX_RECORDS=60

usage() {
  cat <<EOF
usage: $0 probe
       $0 keys [seconds]          (default 5 per button)
       $0 wake [seconds]          (default 120, the RTC safety net)
       $0 wake-log                (print the last wake test result)

wake accepts:
  --delay N          seconds before suspending, to unplug the USB cable (20)
  --after N          seconds to keep listening after it wakes up (15)
  --keep-framework   do not stop the reader framework first (not advised)
  --dry-run          everything except the suspend, attached to the terminal
  --enable-wakeup    try arming the keypad as a wakeup source before suspending
EOF
  exit 1
}

# ------------------------------------------------------------------ decoding
#
# There is no od, no hexdump and no xxd on this device, so a byte is turned
# into a number by looking up its position in a string that holds every byte
# from 1 to 255 in order. Slow — three `dd` calls per event — but it depends on
# nothing that could be missing, and the captures here are a handful of events.

BYTES=""
init_bytes() {
  [ -n "$BYTES" ] && return
  fmt=""
  i=1
  while [ "$i" -le 255 ]; do
    # \ooo, three octal digits: the form POSIX specifies for the printf
    # format operand, and the only one bash, dash and busybox agree on. The
    # \0ooo spelling is NOT equivalent — bash counts the leading zero as one
    # of the three digits and silently truncates.
    fmt="$fmt\\$((i / 64))$((i / 8 % 8))$((i % 8))"
    i=$((i + 1))
  done
  BYTES=$(printf "$fmt")
}

byte_at() {  # file, offset -> decimal value of that byte
  init_bytes
  # The X is a sentinel: command substitution strips trailing newlines, and
  # without it byte 0x0A would come back indistinguishable from a NUL.
  b=$(dd if="$1" bs=1 skip="$2" count=1 2>/dev/null; printf X)
  b=${b%X}
  if [ -z "$b" ]; then
    echo 0        # a NUL cannot survive a shell variable, and reads as empty
    return
  fi
  rest=${BYTES%%"$b"*}
  echo $((${#rest} + 1))
}

# The names on the right are what this Kindle 4 was measured to send, not what
# the code means in input.h: 104 is KEY_PAGEUP but sits under the left thumb
# going forward, and 191/193/194 are outside the standard range entirely.
keyname() {
  case "$1" in
    102) echo HOME ;;
    104) echo FWD-L ;;      # left side, page forward
    105) echo 5WAY-L ;;
    106) echo 5WAY-R ;;
    109) echo BACK-R ;;     # right side, page back
    139) echo MENU ;;
    158) echo BACK ;;
    191) echo FWD-R ;;      # right side, page forward
    193) echo BACK-L ;;     # left side, page back
    194) echo 5WAY-IN ;;
    103) echo UP ;;         108) echo DOWN ;;
    1)   echo ESC ;;        28)  echo ENTER ;;   116) echo POWER ;;
    *)   echo "?" ;;
  esac
}

# Raw capture -> one "type code value" line per event.
records() {
  size=$(wc -c < "$1" 2>/dev/null | tr -d ' ')
  [ -n "$size" ] || size=0
  count=$((size / EVENT_SIZE))
  [ "$count" -gt "$MAX_RECORDS" ] && count=$MAX_RECORDS
  r=0
  while [ "$r" -lt "$count" ]; do
    base=$((r * EVENT_SIZE))
    echo "$(byte_at "$1" $((base + OFF_TYPE))) \
$(byte_at "$1" $((base + OFF_CODE))) \
$(byte_at "$1" $((base + OFF_VALUE)))"
    r=$((r + 1))
  done
}

decode() {
  if [ ! -s "$1" ]; then
    echo "    (no events)"
    return 1
  fi
  # Decoded once into a scratch file, then read twice: every record costs
  # three `dd` forks and this device is slow enough for that to show.
  records "$1" > "$TMP.rec"
  while read -r type code value; do
    if [ "$type" = 1 ]; then
      case "$value" in
        0) act=release ;;
        1) act=press ;;
        2) act=repeat ;;
        *) act=$value ;;
      esac
      printf '    EV_KEY   code=%-4s %-9s %s\n' "$code" "$(keyname "$code")" "$act"
    elif [ "$type" != 0 ]; then
      # EV_SYN (0) is only the separator between events, not worth a line.
      printf '    type=%-3s code=%-4s value=%s\n' "$type" "$code" "$value"
    fi
  done < "$TMP.rec"

  pressed=$(while read -r type code value; do
    [ "$type" = 1 ] && [ "$value" = 1 ] && echo "$code"
  done < "$TMP.rec" | sort -u | tr '\n' ',' | sed 's/,$//')
  [ -n "$pressed" ] && printf '    >> codes pressed: %s\n' "$pressed"
  rm -f "$TMP.rec"
  return 0
}

# ------------------------------------------------------------------ capture

# One reader per input device, so nothing has to be guessed about which one
# carries the buttons: whichever produced bytes is the answer.
capture_start() {
  # Empty the directory rather than remove and recreate it: the first run of
  # the previous version lost its `readers` file here, and a directory that
  # background readers are writing into is not worth deleting under them.
  mkdir -p "$TMP" 2>/dev/null
  [ -d "$TMP" ] || {
    echo "cannot create $TMP — no writable scratch directory, giving up"
    exit 1
  }
  rm -f "$TMP"/*.bin "$TMP/readers" 2>/dev/null
  for dev in /dev/input/event*; do
    [ -r "$dev" ] || continue
    name=$(basename "$dev")
    dd if="$dev" of="$TMP/$name.bin" bs="$EVENT_SIZE" 2>/dev/null &
    echo "$! $dev $TMP/$name.bin" >> "$TMP/readers"
  done
  [ -f "$TMP/readers" ] || { echo "no readable /dev/input/event*"; exit 1; }
}

capture_stop() {
  [ -f "$TMP/readers" ] || return 0
  while read -r pid dev file; do
    kill "$pid" 2>/dev/null
  done < "$TMP/readers"
  # Let the kills land before anything reads the files.
  sleep 1
}

capture_report() {
  found=1
  while read -r pid dev file; do
    [ -s "$file" ] || continue
    found=0
    echo "  $dev:"
    decode "$file"
  done < "$TMP/readers"
  return $found
}

# -------------------------------------------------------------------- probe

cmd_probe() {
  echo "== input devices =========================================="
  cat /proc/bus/input/devices 2>/dev/null || echo "  (/proc/bus/input/devices missing)"

  echo
  echo "== keypad as a wakeup source =============================="
  # The one line the whole plan hangs on. An empty value is not the same as
  # "disabled": the kernel prints enabled/disabled only for devices that CAN
  # wake the system, and an empty string for those that cannot. Empty here
  # means the driver never registered the keypad as a wakeup source, and
  # writing to the file will be refused.
  for f in "$KEYPAD_WAKEUP" \
           /sys/devices/platform/tequila-keypad/input/input1/power/wakeup \
           /sys/devices/platform/fiveway/power/wakeup \
           /sys/devices/platform/mxc_rtc.0/power/wakeup ; do
    [ -f "$f" ] || continue
    v=$(cat "$f" 2>/dev/null)
    printf '  %-62s %s\n' "$f" "${v:-(empty: not wakeup capable)}"
  done

  echo
  echo "== RTC ===================================================="
  if [ -f "$RTC" ]; then
    printf '  %-62s %s\n' "$RTC" "$(cat "$RTC")"
  else
    echo "  MISSING: $RTC"
    echo "  Without it the wake test has no safety net and will refuse to run."
  fi

  echo
  echo "== tools =================================================="
  # Run them, do not ask whether they exist: this device has no `command`
  # builtin, so `command -v` answered "missing" for things that work fine.
  printf 'x' > "$TMP.t" 2>/dev/null
  if [ "$(dd if="$TMP.t" bs=1 count=1 2>/dev/null)" = "x" ]; then
    echo "  dd         ok"
  else
    echo "  dd         BROKEN — nothing below will work"
  fi
  if [ "$(wc -c < "$TMP.t" 2>/dev/null | tr -d ' ')" = "1" ]; then
    echo "  wc         ok"
  else
    echo "  wc         BROKEN"
  fi
  rm -f "$TMP.t"

  echo
  echo "== decoder self-test ======================================"
  # A hand-built input_event — timestamp zero, EV_KEY, code 104, press — fed
  # through the same path a real capture takes.
  printf '\000\000\000\000\000\000\000\000\001\000\150\000\001\000\000\000' \
    > "$TMP.selftest"
  expected="    EV_KEY   code=104  PAGEUP    press"
  actual=$(decode "$TMP.selftest" | head -n1)
  rm -f "$TMP.selftest"
  if [ "$actual" = "$expected" ]; then
    echo "  ok: a synthetic PAGEUP press decodes correctly"
  else
    echo "  FAILED. Expected:"
    echo "  |$expected|"
    echo "  got:"
    echo "  |$actual|"
    echo "  The captures below cannot be trusted until this line is fixed."
  fi

  echo
  echo "== framework =============================================="
  if ps 2>/dev/null | grep -q '[c]vm'; then
    echo "  running (the reader is up)"
  else
    echo "  not running"
  fi
  if ps 2>/dev/null | grep -q '[d]ash\.sh'; then
    echo "  WARNING: dash.sh is running. Stop it first:"
    echo "           /mnt/us/dashboard/stop.sh"
  fi
}

# --------------------------------------------------------------------- keys

cmd_keys() {
  window=${1:-5}

  if ps 2>/dev/null | grep -q '[c]vm'; then
    echo "NOTE: the reader framework is up, so your presses will also turn"
    echo "      pages underneath. Events still reach us — evdev broadcasts to"
    echo "      every reader — but for a clean run stop it first:"
    echo "          /etc/init.d/framework stop     (and 'start' to get it back)"
    echo
  fi

  echo "Press the button when asked, once, and wait for the next prompt."
  echo "Decoding takes a moment after each window; that is normal."
  echo

  for button in \
    "PAGE FORWARD (right side)" \
    "PAGE BACK (right side)" \
    "PAGE FORWARD (left side)" \
    "PAGE BACK (left side)" \
    "5-WAY, press it in" \
    "5-WAY, push it LEFT" \
    "5-WAY, push it RIGHT" \
    "MENU" \
    "BACK" \
    "HOME"
  do
    printf '>> %s ... ' "$button"
    capture_start
    sleep "$window"
    capture_stop
    echo
    capture_report || echo "    (nothing on any device)"
    echo
  done

  echo "Done. What matters: the codes of the two page buttons, since those are"
  echo "the ones the dashboard would use to move between locations."
}

# --------------------------------------------------------------------- wake

# The real test. Runs detached because suspending drops USB and Wi-Fi, and with
# them the SSH session that started it.
cmd_wake() {
  timeout=120
  delay=20
  after=15
  stop_framework=true
  enable_wakeup=false
  dry_run=false

  while [ $# -gt 0 ]; do
    case "$1" in
      --delay) delay=$2; shift 2 ;;
      --after) after=$2; shift 2 ;;
      --keep-framework) stop_framework=false; shift ;;
      # Everything except the one irreversible step, attached to the terminal:
      # the way to find out that a run never started without having to guess
      # from a device that is asleep.
      --dry-run) dry_run=true; stop_framework=false; delay=3; shift ;;
      --enable-wakeup) enable_wakeup=true; shift ;;
      --detached) shift ;;
      [0-9]*) timeout=$1; shift ;;
      *) usage ;;
    esac
  done

  [ -f "$RTC" ] || {
    echo "refusing to run: $RTC is missing, so there is no safety net."
    exit 1
  }

  # Re-exec into a session of its own, for the same reason bin/start.sh does:
  # this process is a child of sshd, and sshd is about to die with the link.
  if [ "${KEYTEST_DETACHED:-}" != 1 ] && [ "$dry_run" = false ]; then
    export KEYTEST_DETACHED=1
    cmd="$0 wake $timeout --delay $delay --after $after --detached"
    [ "$stop_framework" = true ] || cmd="$cmd --keep-framework"
    [ "$enable_wakeup" = false ] || cmd="$cmd --enable-wakeup"
    # No `command -v` here: this device has no `command` builtin, which is
    # what stopped the first version of this test from ever starting. Both
    # branches below are probed by running them, and the fallback needs
    # nothing but the shell — `trap '' HUP` in a subshell is what detaches it,
    # so a missing `nohup` cannot break it either.
    echo "== launch $(date): $cmd" >> "$LOG"
    if setsid true 2>/dev/null; then
      echo "   (detaching with setsid)" >> "$LOG"
      setsid $cmd </dev/null >>"$LOG" 2>&1 &
    else
      echo "   (no setsid: detaching with a HUP-proof subshell)" >> "$LOG"
      ( trap '' HUP INT; $cmd </dev/null >>"$LOG" 2>&1 & ) &
    fi
    # Evidence on the screen that the parent got this far, before it lets go.
    "$EIPS" 1 1 "keytest: avviato, stacca il cavo" 2>/dev/null
    cat <<EOF

Wake test launched. From here on it writes only to $LOG.

  1. UNPLUG THE USB CABLE now: you have ${delay}s. A connected cable both keeps
     the device awake and wakes it back up, which would fake a positive result.
  2. Wait about 10 seconds after that, then press PAGE FORWARD once.
     - if the screen wakes up, a page button is a wakeup source: best case.
     - if nothing happens, press POWER briefly instead, and then, once the
       screen says it is awake, press PAGE FORWARD a couple of times. That
       second half is the fallback design being tested.
  3. If you do nothing at all the RTC brings it back after ${timeout}s.
  4. Plug back in, and read the answer:

         ssh root@192.168.15.244 /mnt/us/keytest.sh wake-log

EOF
    exit 0
  fi

  # ---- from here on we are detached, and the log is the only output ----
  echo "=========================================================="
  echo "wake test $(date)"
  echo "  rtc timeout   : ${timeout}s"
  echo "  unplug delay  : ${delay}s"
  echo "  listen after  : ${after}s"
  echo "  stop framework: $stop_framework"
  [ "$dry_run" = true ] && echo "  DRY RUN       : will not suspend"

  restore() {
    if [ "$stop_framework" = true ]; then
      echo "restarting the framework"
      /etc/init.d/framework start >/dev/null 2>&1
    fi
  }
  trap 'restore' EXIT INT TERM

  if [ "$enable_wakeup" = true ]; then
    echo "-- trying to arm the keypad as a wakeup source"
    for f in "$KEYPAD_WAKEUP" \
             /sys/devices/platform/tequila-keypad/input/input1/power/wakeup \
             /sys/devices/platform/fiveway/power/wakeup ; do
      [ -f "$f" ] || continue
      before=$(cat "$f" 2>/dev/null)
      echo enabled > "$f" 2>/dev/null
      after_v=$(cat "$f" 2>/dev/null)
      echo "   $f: '${before}' -> '${after_v}'"
    done
    echo "   (a value that stays empty means the kernel refused: the driver"
    echo "    never declared this device able to wake the system)"
  fi

  if [ "$stop_framework" = true ]; then
    # The point is to reproduce the conditions dash.sh suspends under, not some
    # other ones: the framework is down there, and powerd is told to keep out.
    echo "-- stopping the framework"
    /etc/init.d/framework stop >/dev/null 2>&1
    initctl stop webreader >/dev/null 2>&1
    lipc-set-prop com.lab126.powerd preventScreenSaver 1 >/dev/null 2>&1
  fi

  "$EIPS" 1 1 "keytest: sospensione tra ${delay}s, stacca il cavo" 2>/dev/null
  sleep "$delay"

  echo "-- opening the input readers"
  capture_start
  # Readers are opened before the suspend on purpose: userspace is frozen, so
  # the fd survives, and whatever event woke the device is queued and delivered
  # the moment it thaws. That queued event is the first half of the result.

  if [ "$dry_run" = true ]; then
    echo "-- DRY RUN: the RTC is left alone and nothing is suspended"
    "$EIPS" 1 1 "keytest: prova a vuoto, non dormo" 2>/dev/null
    t0=$(date +%s)
    sleep 3
    t1=$(date +%s)
  else
    armed=$(cat "$RTC")
    if [ "$armed" -eq 0 ]; then
      echo "-- arming the RTC for ${timeout}s"
      echo -n "$timeout" > "$RTC"
    else
      echo "-- WARNING: the RTC was already armed at ${armed}s, leaving it alone."
      timeout=$armed
    fi

    "$EIPS" 1 1 "keytest: dormo. Premi un tasto pagina." 2>/dev/null

    t0=$(date +%s)
    echo "-- suspending at $t0"
    echo mem > /sys/power/state
    t1=$(date +%s)
  fi
  elapsed=$((t1 - t0))

  echo "-- resumed after ${elapsed}s"
  # What the RTC reads after a wake that was NOT the RTC's doing. dash.sh only
  # re-arms the alarm when this says 0, so if an early wake leaves a stale
  # value here the loop would skip its next arming and sleep until someone
  # pressed power. The number below is what decides how the real loop re-arms.
  echo "-- RTC wakeup_enable now reads: '$(cat "$RTC" 2>/dev/null)'"
  "$EIPS" 1 1 "keytest: sveglio dopo ${elapsed}s" 2>/dev/null

  # Anything the wake source queued needs a moment to reach the readers.
  sleep 2
  capture_stop
  echo
  echo "-- [A] events delivered across the suspend:"
  if capture_report; then woke_with_events=true; else woke_with_events=false; fi

  # Second, separate capture: this is the fallback design under test — the
  # device is awake, the framework is down, and the question is whether the
  # page buttons can be read here. Keeping it apart from [A] is what makes the
  # two answers unambiguous without decoding event timestamps.
  echo
  echo "-- [B] listening for ${after}s while awake, press PAGE FORWARD now:"
  "$EIPS" 1 1 "keytest: premi un tasto pagina (${after}s)" 2>/dev/null
  capture_start
  sleep "$after"
  capture_stop
  if capture_report; then keys_readable=true; else keys_readable=false; fi

  echo
  echo "-- verdict:"
  if [ "$dry_run" = true ]; then
    echo "   DRY RUN: the only line that means anything here is [B]. If the"
    echo "   page presses show up above, the plumbing works and the real run"
    echo "   is worth doing."
  elif [ "$elapsed" -lt $((timeout - 3)) ] && [ "$woke_with_events" = true ]; then
    echo "   [1] WOKEN EARLY, with input events."
    echo "       A button is a wakeup source: the codes in [A] are the ones to"
    echo "       wire into the loop, and no power press is needed at all."
  elif [ "$elapsed" -lt $((timeout - 3)) ]; then
    echo "   [2] Woken early, with no input event across the suspend."
    echo "       That is the power slider (it wakes below the evdev layer) or"
    echo "       the USB cable coming back."
  else
    echo "   [3] Slept the full ${timeout}s: only the RTC brought it back."
    echo "       Either nothing was pressed, or buttons do not wake this device."
  fi
  if [ "$keys_readable" = true ]; then
    echo "   [B] page buttons ARE readable while awake with the framework down."
    echo "       The 'power to wake, then page buttons to switch' design works."
  else
    echo "   [B] no events while awake either. If you did press something, that"
    echo "       is a problem worth understanding before writing any of this."
  fi
  echo "=========================================================="
}

cmd_wake_log() {
  [ -f "$LOG" ] || { echo "no wake test has run yet ($LOG is missing)"; exit 1; }
  # The tail unconditionally: when a run fails before it can write its own
  # header, printing "nothing found" would hide the very lines that explain it.
  tail -n 150 "$LOG"
}

mkdir -p "$(dirname "$TMP")" 2>/dev/null

case "${1:-}" in
  probe)    shift; cmd_probe "$@" ;;
  keys)     shift; cmd_keys "$@" ;;
  wake)     shift; cmd_wake "$@" ;;
  wake-log) shift; cmd_wake_log "$@" ;;
  *)        usage ;;
esac
