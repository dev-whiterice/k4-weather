#!/usr/bin/env bash
# Installs kindle-dash on the Kindle, configured for k4-weather.
#
# RUNS ON THE MAC, not on the Kindle. From any directory:
#
#     ./kindle/install.sh                      # uses root@192.168.15.244
#     ./kindle/install.sh root@192.168.1.50    # Kindle reachable over Wi-Fi
#
# It starts nothing: when it finishes the dashboard is installed but idle, so
# you can try it in debug mode before handing it to the suspend loop.

set -euo pipefail

KINDLE="${1:-root@192.168.15.244}"
REMOTE_DIR="/mnt/us/dashboard"

# Paths relative to the script, not to the directory you launched it from.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="${HERE}/../build/kindle-dash"

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

step "Applying the k4-weather configuration"
cp "$HERE/local/env.sh" "$BUILD/local/env.sh"
cp "$HERE/local/fetch-dashboard.sh" "$BUILD/local/fetch-dashboard.sh"
cp "$HERE/local/indoor-temp.sh" "$BUILD/local/indoor-temp.sh"
cp "$HERE/local/draw.sh" "$BUILD/local/draw.sh"
url="$(grep -m1 '^DASH_URL=' "$BUILD/local/fetch-dashboard.sh" | cut -d'"' -f2)"
echo "    image source: $url"

# The indoor temperature exists only on the device, and kindle-dash has no hook
# that runs once the screen is up: it calls /usr/sbin/eips inline. Rewriting
# those call sites to our wrapper is the smallest change that creates one — it
# draws the image first, then stamps the value on top of it.
sed -i.bak 's|/usr/sbin/eips|"$DIR/local/draw.sh"|g' "$BUILD/dash.sh"
rm -f "$BUILD/dash.sh.bak"
patched="$(grep -c 'local/draw.sh' "$BUILD/dash.sh" || true)"
[ "$patched" -ge 2 ] || fail "dash.sh no longer calls /usr/sbin/eips: kindle-dash
    has changed and the overlay needs rewiring. To install without it, drop the
    two sed lines from this script and set INDOOR_TEMP=false in local/env.sh."
echo "    indoor temperature: $patched eips call sites routed through local/draw.sh"

step "Checking that the image is reachable"
# Better to find out now that the URL is wrong, than in front of an e-ink
# screen that does not refresh and does not say why.
code="$(curl -sS -o /dev/null -w '%{http_code}' "$url" || true)"
if [ "$code" = "200" ]; then
  echo "    HTTP 200, the image is there"
else
  echo "    WARNING: HTTP ${code:-no response}"
  echo "    The 'dashboard' workflow has not published to the output branch yet."
  echo "    Installation continues: the Kindle will work as soon as the image exists."
fi

# USBNetwork is not a DHCP server: macOS asks for an address, gets no answer
# and falls back to a link-local 169.254.x.x. At that point traffic for the
# Kindle leaves through the Wi-Fi towards the internet and times out. The host
# address on the subnet has to be set by hand.
diagnose_usbnet() {
  [ "$(uname)" = "Darwin" ] || return 0
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
  $REMOTE_DIR/xh $REMOTE_DIR/next-wakeup" 2>/dev/null \
  || echo "    chmod not applicable (FAT): normal, carrying on"

cat <<EOF

Installation complete. Nothing was started, on purpose.

Try the pieces one at a time first, from the Kindle:

    ssh $KINDLE
    cd $REMOTE_DIR
    ./local/fetch-dashboard.sh /tmp/test.png && echo OK    # download only
    eips -f -g /tmp/test.png                               # drawing only
    DEBUG=true ./start.sh                                  # full loop, Ctrl-C to quit

Once that works, the real start (background, then the Kindle suspends):

    ssh $KINDLE $REMOTE_DIR/start.sh

To get your Kindle back as an ebook reader:

    ssh $KINDLE '$REMOTE_DIR/stop.sh; /etc/init.d/framework start'
EOF
