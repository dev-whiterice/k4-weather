#!/usr/bin/env bash
# Installs kindle-dash on the Kindle, configured for k4-weather.
#
# RUNS ON THE COMPUTER, not on the Kindle. From any directory:
#
#     ./kindle/install.sh                      # uses root@192.168.15.244
#     ./kindle/install.sh root@192.168.1.50    # Kindle reachable over Wi-Fi
#
# macOS, Linux and Windows. On Windows it needs the Git Bash that comes with
# Git for Windows — it is bash, and it brings the ssh, tar and curl this script
# uses. From PowerShell there is kindle/install.ps1, which is a wrapper around
# this same file and nothing more.
#
# It starts nothing: when it finishes the dashboard is installed but idle, so
# you can try it in debug mode before handing it to the suspend loop.

set -euo pipefail

# A note on Git Bash and paths, because the obvious defence here is a trap.
#
# Git Bash rewrites an argument that looks like a Unix path into a Windows one
# before handing it to a native program, so `ssh kindle /mnt/us/dashboard/x.sh`
# typed at a prompt reaches the Kindle as `C:/Program Files/Git/mnt/us/...`.
# Turning that off globally — MSYS_NO_PATHCONV=1 — looks like the fix and is
# not: `curl -o /dev/null` and every other native program in this script stop
# understanding their own arguments, and curl starts failing with "client
# returned ERROR on write" in the middle of a step that worked.
#
# It is also unnecessary. Every remote path below travels inside a quoted
# command string that begins with a command name — `"mkdir -p /mnt/us/..."` —
# and MSYS converts only arguments that look like a path from their first
# character. The one place it does bite is a command typed by hand, which is
# why the instructions printed at the end quote theirs.

# Two ways in, because SSH is not always available and does not have to be.
#
#     ./kindle/install.sh [user@host]     over the network, the normal way
#     ./kindle/install.sh --drive E:      onto the Kindle mounted as a USB disk
#
# The second exists because on Windows the USB network link can be blocked by
# something outside this project's reach: the Kindle presents the Linux RNDIS
# gadget, Windows binds a serial driver to it, and the only clean fix is an
# unsigned INF — which means turning off driver signature enforcement on the
# whole machine. Not a price worth paying to copy a hundred kilobytes.
#
# In USB drive mode the Kindle exposes /mnt/us as a volume, so `dashboard` and
# `extensions` can simply be written to it. Nothing else is needed: the KUAL
# menu starts, tests and diagnoses the panel from the device itself, and the
# execute bits it would otherwise chmod are not stored on FAT anyway — which is
# why every menu action names /bin/sh explicitly.
DRIVE=""
if [ "${1:-}" = "--drive" ]; then
  [ -n "${2:-}" ] || { echo "usage: $0 --drive E:" >&2; exit 1; }
  DRIVE="$2"
  shift 2
fi

KINDLE="${1:-root@192.168.15.244}"
REMOTE_DIR="/mnt/us/dashboard"
EXT_DIR="/mnt/us/extensions/k4weather"

# Paths relative to the script, not to the directory you launched it from.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="${HERE}/../build/kindle-dash"
# The KUAL extension is staged rather than copied straight from the working
# tree, so that the line-ending pass below has somewhere to write.
EXT_BUILD="${HERE}/../build/extension"

RELEASES="https://api.github.com/repos/pascalw/kindle-dash/releases/latest"

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
fail() { printf '\033[31mError: %s\033[0m\n' "$1" >&2; exit 1; }

for tool in curl tar ssh; do
  command -v "$tool" >/dev/null || fail "missing command '$tool'"
done

step "Downloading kindle-dash"
rm -rf "$BUILD"
mkdir -p "$BUILD"
# head -n1: a release may carry several assets, and only the first is the
# runtime archive. Without it `asset` would hold a multi-line list.
asset="$(curl -sSfL "$RELEASES" | grep browser_download_url | cut -d'"' -f4 | head -n1)"
[ -n "$asset" ] || fail "cannot find the release asset on GitHub"
echo "    $asset"
# The archive expands flat, with no containing directory.
curl -sSfL "$asset" | tar xz -C "$BUILD"
[ -x "$BUILD/dash.sh" ] || fail "the archive does not contain dash.sh"

# Every shell script that leaves this computer goes through here first.
#
# The Kindle runs busybox `ash`, and that shell does not treat a carriage
# return as whitespace: it is an ordinary character that becomes part of the
# token it ends. A script checked out with CRLF line endings — which is what
# Git for Windows does by default — therefore reads
#
#     DASH_DIR=${DASH_DIR:-/mnt/us/dashboard}
#
# as an assignment of "/mnt/us/dashboard<CR>", a directory that does not
# exist, and
#
#     export INTERACT=${INTERACT:-true}
#
# as "true<CR>", which is not equal to "true" and so quietly turns off
# everything guarded by that comparison. On a device with no terminal the two
# faults look identical: nothing happens, and nothing says why.
#
# .gitattributes stops this at the source and is the real fix. This is the
# second line of defence, because an editor, a ZIP download or a copy through
# a Windows share can all put it back after the checkout, and checking here
# costs nothing next to finding out later, in front of an e-ink screen.
strip_cr() {
  local file stripped=0 found
  # tr, not `sed -i`: BSD sed and GNU sed disagree about -i, and this has to
  # run unchanged on macOS, Linux and Git Bash.
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    found=$(LC_ALL=C tr -cd '\r' < "$file" | wc -c | tr -d ' ')
    [ "$found" = "0" ] && continue
    LC_ALL=C tr -d '\r' < "$file" > "$file.lf" && mv "$file.lf" "$file"
    stripped=$((stripped + 1))
  done < <(find "$1" -type f -name '*.sh')
  echo "$stripped"
}

step "Applying the k4-weather configuration"
for script in env.sh fetch-dashboard.sh indoor-temp.sh battery.sh draw.sh \
              locations.sh interact.sh suspend.sh; do
  cp "$HERE/local/$script" "$BUILD/local/$script"
done
base_url="$(grep -m1 '^BASE_URL=' "$BUILD/local/fetch-dashboard.sh" | cut -d'"' -f2)"
echo "    image source: $base_url"

# fbink is what draws the indoor temperature at a size worth reading, and it is
# neither on the device nor in this repository: a static ARM binary you download
# once and drop in kindle/fbink. Optional on purpose — without it the panel
# works exactly as before, with the smaller number eips draws.
# Fetched rather than asked for, because asking for it sent people to a page
# that does not have it. FBInk's own releases carry a source tarball and
# nothing else — no prebuilt binary has ever been published there, so the
# instruction this script used to print could not be followed and `fbink` was
# simply never installed. What does publish a build for this device is
# KOReader: its `kindle` package is armv7 softfloat against an old glibc, which
# is what a Kindle 4 runs, and the fbink inside it is the standalone binary
# KOReader's own startup scripts call before anything else is up. It needs
# libc and libm and nothing further.
#
# 40MB downloaded for a megabyte of binary is not elegant. It is done once,
# cached in build/, and it is the difference between a legible reading and a
# number nobody can see from the doorway.
if [ ! -f "$HERE/fbink" ]; then
  step "Fetching fbink"
  koreader="$BUILD/../koreader-kindle.zip"
  if [ ! -s "$koreader" ]; then
    kurl="$(curl -sSfL https://api.github.com/repos/koreader/koreader/releases/latest \
      | grep browser_download_url | cut -d'"' -f4 | grep -- '-kindle-v' | head -n1)"
    if [ -n "$kurl" ]; then
      echo "    $kurl"
      curl -sSfL -o "$koreader" "$kurl" || rm -f "$koreader"
    fi
  fi
  if [ -s "$koreader" ]; then
    # unzip is on macOS and in Git Bash; where it is not, this is not fatal.
    if unzip -p "$koreader" koreader/fbink > "$HERE/fbink.part" 2>/dev/null \
       && [ -s "$HERE/fbink.part" ]; then
      mv "$HERE/fbink.part" "$HERE/fbink"
      chmod +x "$HERE/fbink"
      echo "    extracted $(wc -c <"$HERE/fbink" | tr -d ' ') bytes to kindle/fbink"
    else
      rm -f "$HERE/fbink.part"
      echo "    could not extract it; the temperature will be small and there
      will be no battery level"
    fi
  else
    echo "    could not download it; the temperature will be small and there
    will be no battery level"
  fi
fi

FBINK=""
if [ -f "$HERE/fbink" ]; then
  cp "$HERE/fbink" "$BUILD/fbink"
  chmod +x "$BUILD/fbink"
  FBINK="$REMOTE_DIR/fbink"
  echo "    fbink: $(wc -c <"$HERE/fbink" | tr -d ' ') bytes"
else
  echo "    no fbink: the temperature will be drawn by eips, small, and the
    battery level not at all"
fi

# The page's own font, so the two readings the device draws look like the
# figures beside them rather than like the output of the other program that
# they are. Tiny — eleven characters — and useless without fbink, but copied
# anyway so that installing fbink later needs nothing else. Built by
# tools/indoor_font.py.
if [ -f "$HERE/fonts/indoor.ttf" ]; then
  mkdir -p "$BUILD/fonts"
  cp "$HERE/fonts/indoor.ttf" "$BUILD/fonts/indoor.ttf"
  echo "    indoor font: $(wc -c <"$HERE/fonts/indoor.ttf" | tr -d ' ') bytes"
else
  echo "    no kindle/fonts/indoor.ttf: fbink will use its own bitmap face"
fi

# The indoor temperature and the battery level exist only on the device, and
# kindle-dash has no hook that runs once the screen is up: it calls
# /usr/sbin/eips inline. Rewriting those call sites to our wrapper is the
# smallest change that creates one — it draws the image first, then stamps the
# two values on top of it.
sed -i.bak 's|/usr/sbin/eips|"$DIR/local/draw.sh"|g' "$BUILD/dash.sh"
rm -f "$BUILD/dash.sh.bak"
patched="$(grep -c 'local/draw.sh' "$BUILD/dash.sh" || true)"
[ "$patched" -ge 2 ] || fail "dash.sh no longer calls /usr/sbin/eips: kindle-dash
    has changed and the overlay needs rewiring. To install without it, drop the
    two sed lines from this script and set INDOOR_TEMP=false and BATTERY=false
    in local/env.sh."
echo "    values drawn on the device: $patched eips call sites via local/draw.sh"

# The other two rewrites, and the reason the page buttons work at all.
#
# kindle-dash sleeps ten seconds before suspending — a window left open purely
# so the loop can be interrupted by hand — and then suspends inside its own
# `rtc_sleep`, a function with nothing around it to hook into. Both become
# calls to scripts of ours:
#
#   sleep 10   ->  local/interact.sh 10        listen for the page buttons
#                                              instead of doing nothing
#   rtc_sleep  ->  local/suspend.sh            the same suspend, plus the
#                                              knowledge of whether the clock
#                                              or a person ended it
#
# `rtc_sleep` is then dead code inside dash.sh; it is left alone rather than
# deleted, so the file stays as close to upstream as possible.
sed -i.bak \
  -e 's|^    sleep 10$|    "$DIR/local/interact.sh" 10|' \
  -e 's|^    rtc_sleep "\$next_wakeup_secs"$|    "$DIR/local/suspend.sh" "$next_wakeup_secs"|' \
  "$BUILD/dash.sh"
rm -f "$BUILD/dash.sh.bak"

for hook in interact suspend; do
  grep -q "local/${hook}.sh" "$BUILD/dash.sh" || fail "dash.sh has no call site for
    local/${hook}.sh: kindle-dash has changed the shape of its main loop and the
    location switching needs rewiring. To install without it, drop this sed from
    the script and set INTERACT=false in local/env.sh — the panel then behaves
    exactly as it did before, on one location."
done
echo "    location switching: the sleep window and the suspend now go through local/"

step "Checking that the images are reachable"
# Better to find out now that the URL is wrong, than in front of an e-ink
# screen that does not refresh and does not say why.
#
# The manifest, not one image: it is the first thing the device asks for, and
# it is also the only file that says how many images there should be.
#
# Fetched once into a file rather than three times down three pipes: on Git
# Bash the short-lived pipes made curl report "client returned ERROR on write",
# which is a false alarm printed in the middle of a step that succeeded.
manifest="$BUILD/../locations.txt"
code="$(curl -sSL -o "$manifest" -w '%{http_code}' "$base_url/locations.txt" || true)"
if [ "$code" = "200" ]; then
  count="$(grep -c . "$manifest" || true)"
  echo "    HTTP 200, ${count} location(s) published:"
  cut -f1,3 "$manifest" | sed 's/^/      /'
  rm -f "$manifest"
else
  rm -f "$manifest"
  echo "    WARNING: HTTP ${code:-no response}"
  echo "    On 404, either Pages is off for this repository (Settings > Pages:"
  echo "    branch 'output', folder /) or the 'dashboard' workflow has never"
  echo "    published to the output branch. See docs/setup.md step 3."
  echo "    Installation continues: the Kindle will work as soon as the image exists."
fi

# Why the Kindle is unreachable, said in the terms of the operating system in
# front of you. USBNetwork runs no DHCP server, so the host end of the link
# never gets an address on the Kindle's subnet by itself, and until it has one
# the traffic leaves through the Wi-Fi and times out. The cure is the same
# everywhere and the command is different everywhere.
diagnose_usbnet() {
  case "$(uname -s)" in
    Darwin)             diagnose_usbnet_macos ;;
    MINGW*|MSYS*|CYGWIN*) diagnose_usbnet_windows ;;
  esac
  return 0
}

# Windows has the same problem for the same reason, and no ifconfig to fix it
# with. The Kindle appears as an RNDIS adapter; the address goes on with netsh,
# from an elevated prompt, and the interface name is whatever Windows decided
# to call it — usually "Ethernet 2" or similar.
diagnose_usbnet_windows() {
  local subnet
  subnet="${KINDLE##*@}"; subnet="${subnet%.*}"

  local rndis
  # Asked by driver description, not by the name Windows gave the connection:
  # "Ethernet 2" is whatever happened to be enumerated second and is very often
  # a USB dock or a network dongle. Configuring that one instead of the Kindle
  # takes the computer off its own LAN, which is a worse afternoon than a
  # dashboard that did not install.
  rndis="$(powershell.exe -NoProfile -Command \
    "Get-NetAdapter | Where-Object { \$_.InterfaceDescription -match 'RNDIS|Remote NDIS|Ethernet Gadget' } | Select-Object -First 1 -ExpandProperty Name" \
    2>/dev/null | tr -d '\r')"

  if [ -z "$rndis" ]; then
    # Before concluding that the Kindle is not there: it may be there and bound
    # to the wrong driver, which looks exactly the same from the network side.
    #
    # In usbnet mode the Kindle does not use Amazon's own USB vendor id at all
    # — it presents the Linux gadget, 0525:a4a2, describing itself on the bus as
    # "RNDIS/Ethernet Gadget". Windows 10 and 11 read that descriptor as a
    # CDC-ACM serial port and bind usbser.sys, so the Kindle appears under Ports
    # as a COM port and never becomes a network adapter. Same fault on a
    # Raspberry Pi Zero and on Android tethering; the cure is the same too.
    local serial
    serial="$(powershell.exe -NoProfile -Command \
      "Get-PnpDevice -PresentOnly | Where-Object { \$_.InstanceId -match 'VID_0525' } | Select-Object -First 1 -ExpandProperty FriendlyName" \
      2>/dev/null | tr -d '\r')"

    if [ -n "$serial" ]; then
      cat >&2 <<EOF

Nothing answered on ${KINDLE}, but the Kindle IS connected and USBNetwork IS
switched on. Windows has simply bound the wrong driver to it: it reads the
Linux RNDIS gadget as a serial port, so the device sits under "Ports" as

    ${serial}

instead of becoming a network adapter. Point it at the RNDIS driver Windows
already ships, in Device Manager, as an administrator:

  1. Ports (COM & LPT) > ${serial} > Update driver
  2. Browse my computer > Let me pick from a list
  3. "Have Disk...", and TYPE the path (C:\Windows\INF is hidden, so the
     Browse button will not show it):

         C:\Windows\INF\netrndis.inf

  4. Model: USB RNDIS Adapter        (not the "6" variant)
  5. Accept the compatibility warning

Naming the INF is the part that matters: unticking "Show compatible hardware"
is NOT enough, because Device Manager still filters the list to the Ports class
the device is in, where no network driver exists. And do not go looking for
"Remote NDIS based Internet Sharing Device", which most guides name — that
entry ships with a Windows Mobile INF that current Windows does not have.
If USB RNDIS Adapter does not take, repeat with C:\Windows\INF\rndiscmp.inf
and pick "Remote NDIS Compatible Device".

It then moves to Network adapters, and running this script again will find it
and tell you the address to give it. Reversible throughout, from
Properties > Driver > Roll Back Driver.

If both INFs are refused with "the folder does not contain a compatible
driver", stop here rather than reaching for an unsigned INF of your own: that
needs driver signature enforcement turned off for the whole machine, which is a
large price for copying a hundred kilobytes. Install over the USB disk instead
— it needs no network at all, and the KUAL menu does the rest on the device:

    ;un on the Kindle          (toggles USB networking off: it becomes a drive)
    ./kindle/install.sh --drive E:
EOF
      exit 1
    fi

    cat >&2 <<EOF

Nothing answered on ${KINDLE}, and Windows has no RNDIS adapter and no Linux
gadget either — so the Kindle is not presenting itself over USB at all. In
order:

  1. Is it plugged in, with a DATA cable? Many USB cables carry power only,
     and they look identical. A charging LED proves nothing: that is the one
     thing a power-only cable does do.
  2. Is USBNetwork switched on? By default the Kindle is a USB drive and
     nothing else. On the device: KUAL > USBNetwork > "toggle usbnetwork",
     or type ;un into the search box.

Then run this again. If instead the Kindle is on your Wi-Fi, skip USBNetwork
altogether and give this script the address it shows under Settings > Device
Info:

    ./kindle/install.sh root@192.168.1.50
EOF
    exit 1
  fi

  cat >&2 <<EOF

Nothing answered on ${KINDLE}. The Kindle's USB network adapter is there —
Windows calls it "${rndis}" — but it has no address on ${subnet}.x: USBNetwork
runs no DHCP server, so Windows falls back to a 169.254.x.x link-local address
and the traffic never reaches the device.

$(powershell.exe -NoProfile -Command \
  "Get-NetIPAddress -InterfaceAlias '${rndis}' -AddressFamily IPv4 | Select-Object IPAddress, PrefixLength | Format-Table -AutoSize | Out-String" \
  2>/dev/null | tr -d '\r' | sed 's/^/    /')

From an ADMINISTRATOR PowerShell:

    netsh interface ipv4 set address name="${rndis}" static ${subnet}.201 255.255.255.0

That name is the Kindle's adapter and only that one. Do not put this address on
the interface your LAN or Wi-Fi uses: it would take the computer off its own
network. Do not set a gateway either, for the same reason. Then:

    ping ${KINDLE##*@}
EOF
  exit 1
}

# USBNetwork is not a DHCP server: macOS asks for an address, gets no answer
# and falls back to a link-local 169.254.x.x. At that point traffic for the
# Kindle leaves through the Wi-Fi towards the internet and times out. The host
# address on the subnet has to be set by hand.
diagnose_usbnet_macos() {
  local iface subnet
  iface="$(networksetup -listallhardwareports 2>/dev/null \
    | awk '/^Hardware Port: RNDIS|^Hardware Port: .*Ethernet Gadget/{getline; print $2; exit}')"
  [ -n "$iface" ] || return 0

  subnet="${KINDLE##*@}"; subnet="${subnet%.*}"
  ifconfig "$iface" 2>/dev/null | grep -q "inet ${subnet}\." && return 0

  cat >&2 <<EOF

The USBNetwork interface ($iface) exists but has no address on ${subnet}.x:

$(ifconfig "$iface" | grep -E 'inet |status' | sed 's/^/    /')

Assign one and run this script again:

    sudo ifconfig $iface ${subnet}.201 netmask 255.255.255.0

This has to be redone every time the cable is reconnected. Do not set a
gateway on this interface: it would be preferred over the Wi-Fi and leave you
without internet.
EOF
  exit 1
}

step "Normalising the line endings"
# The last thing done to the build, so that nothing after it can put a CR back.
# The staging copy of the extension exists for the same reason: the KUAL
# scripts are copied straight out of the working tree, and this is where they
# get the same treatment as everything else.
rm -rf "$EXT_BUILD"
mkdir -p "$EXT_BUILD"
cp -R "$HERE/extensions/k4weather/." "$EXT_BUILD/"

dash_cr="$(strip_cr "$BUILD")"
ext_cr="$(strip_cr "$EXT_BUILD")"
if [ "$dash_cr" = "0" ] && [ "$ext_cr" = "0" ]; then
  echo "    all LF already, nothing to do"
else
  echo "    $((dash_cr + ext_cr)) script(s) had CRLF line endings and were converted."
  echo "    That means this checkout is CRLF: the .gitattributes in this"
  echo "    repository prevents it, so run 'git add --renormalize .' once to"
  echo "    fix the working tree too."
fi

# ---------------------------------------------------------- the USB disk path
#
# Everything above this point is the same either way: the build, the patching
# of dash.sh and the line endings do not care how the files travel. Only the
# transport differs, and this one is a plain copy.
if [ -n "$DRIVE" ]; then
  step "Copying to the Kindle mounted at $DRIVE"

  # E:, E:\, /e, /e/ — all the shapes this gets typed in, reduced to the one
  # Git Bash can use. A bare drive letter is the likeliest, and it is also the
  # one that means "the current directory on E:" to Windows rather than its
  # root, so it cannot be passed through untouched.
  dest="$DRIVE"
  case "$dest" in
    [A-Za-z]:*) dest="/$(printf '%s' "${dest%%:*}" | tr 'A-Z' 'a-z')${dest#?:}" ;;
  esac
  dest="${dest%/}"
  dest="${dest%\\}"
  [ -n "$dest" ] || fail "cannot make sense of the drive '$DRIVE'"

  [ -d "$dest" ] || fail "$dest is not there. Is the Kindle in USB drive mode?
    In usbnet mode it is a network device and not a disk: type ;un into the
    Kindle's search box to toggle that off, and it comes back as a drive."

  # A Kindle root, and not somebody's backup disk about to receive 40MB of
  # dashboard. `system` is Amazon's and `documents` is where books live; both
  # are on every Kindle and on almost nothing else.
  if [ ! -d "$dest/system" ] && [ ! -d "$dest/documents" ]; then
    fail "$dest does not look like a Kindle: no 'system' and no 'documents'
    directory at its root. Refusing to write to it. Pass the drive the Kindle
    is actually mounted on."
  fi

  # Only ever adds and overwrites, never deletes: this is somebody's ebook
  # reader, and the two directories below are the only part of it that is ours.
  mkdir -p "$dest/dashboard" "$dest/extensions/k4weather"
  cp -R "$BUILD/." "$dest/dashboard/"
  cp -R "$EXT_BUILD/." "$dest/extensions/k4weather/"
  echo "    $(find "$BUILD" "$EXT_BUILD" -type f | wc -l | tr -d ' ') files written"
  echo "    $dest/dashboard  and  $dest/extensions/k4weather"

  # No chmod: FAT stores no execute bit, which is exactly why menu.json names
  # /bin/sh in every action and why the scripts test for -f rather than -x.

  cat <<EOF

Installation complete, with nothing started.

There is no SSH in this mode, so everything from here happens on the Kindle:

  1. Eject the drive from Windows, and unplug it. The Kindle leaves USB drive
     mode on its own and comes back a reader.
  2. KUAL > k4-weather > "Meteo: prova (scarica e disegna)"
     One download and one draw, with the reader still running underneath. This
     is the check that the Wi-Fi, the URL and the image all work.
  3. KUAL > k4-weather > "Meteo: prova i tasti pagina"
     Twenty seconds of the real listening window, and a verdict on screen.
  4. KUAL > k4-weather > "Meteo: avvia il pannello"
     The real start. The reader goes away and the panel takes over.

If any of them looks like it did nothing:

    KUAL > k4-weather > "Meteo: diagnostica"

writes k4weather-diagnostica.txt to the root of this same drive. Plug the
Kindle back in and read it — it is the whole picture, and it needs no network.
EOF
  exit 0
fi

step "Copying to $KINDLE:$REMOTE_DIR"
ssh -o ConnectTimeout=10 "$KINDLE" "mkdir -p $REMOTE_DIR" 2>/dev/null || {
  diagnose_usbnet
  fail "cannot reach $KINDLE (is USBNetwork on? is the cable connected?)"
}
# No rsync: macOS 15+ ships openrsync (compatible with rsync 2.6.9) and the
# Kindle has busybox tar. A tar over SSH speaks a language both understand.
#
# COPYFILE_DISABLE avoids the AppleDouble `._*` sidecars, and --format=ustar
# avoids extended pax headers: busybox tar does not understand them and prints
# a burst of "skipping header 'x'".
COPYFILE_DISABLE=1 tar c --format=ustar -C "$BUILD" . \
  | ssh "$KINDLE" "mkdir -p '$REMOTE_DIR' && cd '$REMOTE_DIR' && tar x"

# Cleans up leftovers from installations made before that fix.
# busybox find has no -delete, and with -exec it deletes during the walk and
# skips part of it: collect the list first, then remove.
ssh "$KINDLE" "find '$REMOTE_DIR' -name '._*' | xargs rm -f" 2>/dev/null || true
echo "    copied $(find "$BUILD" -type f | wc -l | tr -d ' ') files"

step "Restoring the executable bits"
# On /mnt/us (a FAT filesystem) permissions may not be stored: if the chmod
# does not stick it is not a problem, the partition is mounted executable.
ssh "$KINDLE" "chmod +x $REMOTE_DIR/*.sh $REMOTE_DIR/local/*.sh \
  $REMOTE_DIR/xh $REMOTE_DIR/next-wakeup $FBINK" 2>/dev/null \
  || echo "    chmod not applicable (FAT): normal, carrying on"

step "Installing the KUAL extension in $EXT_DIR"
# So the panel can be started from the device's own menu instead of over SSH.
#
# Asked before the copy, which creates /mnt/us/extensions on its own and would
# make the question answer itself. KUAL is not part of this project and cannot
# be installed from here, so a device without it is worth a word now rather
# than a menu entry looked for in vain later.
kual="$(ssh "$KINDLE" "ls -d /mnt/us/extensions/*/ 2>/dev/null | wc -l" 2>/dev/null | tr -d ' ')"

# Copied even where KUAL is missing: a handful of small files, already in place
# if it ever arrives.
COPYFILE_DISABLE=1 tar c --format=ustar -C "$EXT_BUILD" . \
  | ssh "$KINDLE" "mkdir -p '$EXT_DIR' && cd '$EXT_DIR' && tar x"
ssh "$KINDLE" "find '$EXT_DIR' -name '._*' | xargs rm -f" 2>/dev/null || true
ssh "$KINDLE" "chmod +x $EXT_DIR/bin/*.sh" 2>/dev/null \
  || echo "    chmod not applicable (FAT): normal, carrying on"

if [ "${kual:-0}" -gt 0 ] 2>/dev/null; then
  echo "    installed, alongside $kual other extension(s)"
else
  echo "    installed, but /mnt/us/extensions held no extension: KUAL is"
  echo "    probably not on this device. The entries appear once it is."
fi

cat <<EOF

Installation complete. Nothing was started, on purpose.

Try the pieces one at a time first, from the Kindle:

    ssh $KINDLE
    cd $REMOTE_DIR
    ./local/fetch-dashboard.sh /tmp/test.png && echo OK    # download only
    eips -f -g /tmp/test.png                               # drawing only
    DEBUG=true ./start.sh                                  # full loop, Ctrl-C to quit

Once that works, the real start (background, then the Kindle suspends):

    ssh $KINDLE '$REMOTE_DIR/start.sh'

(the quotes matter in Git Bash on Windows: unquoted, it rewrites anything that
starts with a slash into a Windows path before ssh ever sees it)

or, with no computer at all, from the device: KUAL > k4-weather >
"Meteo: avvia il pannello". The same menu has a one-shot download-and-draw
that leaves the reader running, which is the quicker way to check this
installation without SSH.

To get your Kindle back as an ebook reader:

    ssh $KINDLE '$REMOTE_DIR/stop.sh; /etc/init.d/framework start'

Or hold the power button for ~20s: nothing starts the dashboard at boot, so a
reboot always comes back a reader.

If a KUAL entry looks like it does nothing — the menu prints the action, exits,
and the reader comes back — the error is not lost, it is just somewhere nobody
looks. In order:

    KUAL > k4-weather > "Meteo: diagnostica"

writes k4weather-diagnostica.txt to the root of the Kindle's USB drive, which
is the whole picture with no computer needed beyond the one you read it on. It
gathers, among other things, the two logs worth reading directly:

    ssh $KINDLE 'cat /var/tmp/KUAL.log'                  # KUAL's own: the
                                                         # shell errors of a
                                                         # menu action, and the
                                                         # only place they go
    ssh $KINDLE 'cat $EXT_DIR/kual.log'                  # this extension's
EOF
