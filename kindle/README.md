# The client on the Kindle 4

The Kindle computes almost nothing: it wakes up, downloads a PNG, draws it,
writes its own temperature on top of it and goes back to sleep. All the fragile
parts — waiting for Wi-Fi, modern TLS, suspend to RAM, wake-up scheduled by the
hardware clock — are already solved by
[pascalw/kindle-dash](https://github.com/pascalw/kindle-dash), used here as the
runtime. This directory holds the files that replace or extend its own:

| File | Role |
|---|---|
| `local/env.sh` | configuration of the loop, and of everything below |
| `local/fetch-dashboard.sh` | the download, with retries |
| `local/indoor-temp.sh` | the temperature sensor, read and calibrated |
| `local/draw.sh` | `eips` plus the temperature stamped on top, with `fbink` |
| `extensions/k4weather/` | the KUAL menu, to start the panel without a computer |
| `fbink` | not in this repository: the binary that draws the value large (below) |

## What `kindle-dash` actually does

On start-up `dash.sh` **shuts down the Kindle interface**:

```sh
/etc/init.d/framework stop          # goodbye ebook reader
initctl stop webreader
echo powersave > .../scaling_governor
lipc-set-prop com.lab126.powerd preventScreenSaver 1
```

From that moment the device is no longer a reader: it is a panel. Getting back
takes `stop.sh` **followed by** `/etc/init.d/framework start`, or a reboot.

Then it enters the main loop, which on every pass:

1. records the battery level in the log;
2. asks the `next-wakeup` binary how many seconds remain until the next
   `REFRESH_SCHEDULE` slot;
3. if that is more than `SLEEP_SCREEN_INTERVAL` seconds away it shows
   `sleeping.png`, otherwise it refreshes the dashboard: waits for Wi-Fi, calls
   `local/fetch-dashboard.sh`, and draws with `eips`;
4. **waits 10 seconds** — the only useful window to interrupt it;
5. writes the duration to the RTC and suspends to RAM with
   `echo mem > /sys/power/state`.

Two behaviours that explain how our configuration is written:

- **If the fetch exits non-zero, the screen is not touched at all.** That is
  why `fetch-dashboard.sh` retries and then fails instead of writing an empty
  file: an old dashboard beats a blank panel.
- **One full refresh every `FULL_DISPLAY_REFRESH_RATE` partial updates.**
  Partial updates do not flash the screen but accumulate ghosting; the full one
  clears it.

## Installation

Jailbreak, USBNetwork and Wi-Fi have to be configured already.

The scripted way, from the Mac, is [`install.sh`](install.sh): it downloads the
runtime, applies our configuration, checks the image URL, copies everything to
the device and deliberately starts nothing.

```sh
./kindle/install.sh                      # uses root@192.168.15.244
./kindle/install.sh root@192.168.1.50    # Kindle reachable over Wi-Fi
```

By hand it is four steps:

```sh
# 1. Download the runtime. The archive is a .tgz that expands flat.
mkdir -p kindle-dash
curl -sSL "$(curl -sSL https://api.github.com/repos/pascalw/kindle-dash/releases/latest \
  | grep browser_download_url | cut -d'"' -f4 | head -n1)" | tar xz -C kindle-dash

# 2. Replace the example configuration with ours, and route the drawing
#    through our wrapper (see "The indoor temperature" below)
cp kindle/local/env.sh             kindle-dash/local/env.sh
cp kindle/local/fetch-dashboard.sh kindle-dash/local/fetch-dashboard.sh
cp kindle/local/indoor-temp.sh     kindle-dash/local/indoor-temp.sh
cp kindle/local/draw.sh            kindle-dash/local/draw.sh
cp kindle/fbink                    kindle-dash/fbink        # optional, see below
sed -i.bak 's|/usr/sbin/eips|"$DIR/local/draw.sh"|g' kindle-dash/dash.sh

# 3. Copy to the Kindle (USBNetwork on, cable connected)
rsync -vr kindle-dash/ root@192.168.15.244:/mnt/us/dashboard

# 4. Restore the executable bits, which the transfer can lose
ssh root@192.168.15.244 'chmod +x /mnt/us/dashboard/*.sh \
  /mnt/us/dashboard/local/*.sh /mnt/us/dashboard/xh \
  /mnt/us/dashboard/next-wakeup /mnt/us/dashboard/fbink'

# 5. Optional, and only if KUAL is installed: the menu entries
rsync -vr kindle/extensions/k4weather/ root@192.168.15.244:/mnt/us/extensions/k4weather
ssh root@192.168.15.244 'chmod +x /mnt/us/extensions/k4weather/bin/*.sh'
```

As an alternative to step 3, a Kindle plugged in as a normal USB drive exposes
`/mnt/us` as a disk: you can copy the `dashboard` folder in Finder and use SSH
only for the commands.

`DASH_URL` in `fetch-dashboard.sh` already points at the GitHub Pages site that
serves the `output` branch — not at `raw.githubusercontent.com`, whose rate
limit would freeze the panel ([why, and how to turn Pages
on](../docs/setup.md#3-turn-on-pages)). It embeds owner and repository name, so
it needs changing if either does.

### If SSH times out with USBNetwork on

USBNetwork **is not a DHCP server**. macOS brings the interface up (it appears
as `RNDIS/Ethernet Gadget`), asks for an address, gets no answer and after the
timeout falls back to a link-local `169.254.x.x`. At that point there is no
route towards `192.168.15.0/24`, so packets for the Kindle leave through the
Wi-Fi towards the internet and die there:

```sh
ifconfig en8 | grep inet          # inet 169.254.243.126  ← the symptom
route -n get 192.168.15.244       # interface: en0        ← leaving via Wi-Fi
```

The host address on the subnet has to be set by hand:

```sh
sudo ifconfig en8 192.168.15.201 netmask 255.255.255.0
```

The interface name comes from:

```sh
networksetup -listallhardwareports | grep -A1 "Ethernet Gadget"
```

It has to be redone every time the cable is reconnected — `install.sh` notices
on its own and prints the right command. **Do not set a gateway** on this
interface: it sits above the Wi-Fi in the network service order and would
become the default route, leaving you without internet.

## Try it in debug mode

Do not run `start.sh` as your first move: with `DEBUG=true` the loop stays in
the foreground, prints every command and **uses `sleep` instead of
suspending**, so the device stays reachable over SSH and you can stop it with
Ctrl-C.

```sh
ssh root@192.168.15.244
cd /mnt/us/dashboard

# The download alone first, without touching the screen
./local/fetch-dashboard.sh /tmp/test.png && echo OK && ls -l /tmp/test.png
./xh --version                    # must run: it is a static ARM binary

# The sensor, without touching the screen either
./local/indoor-temp.sh --probe

# Then the drawing, temperature included
. ./local/env.sh && ./local/draw.sh -f -g /tmp/test.png

# Finally the whole loop, in the foreground
DEBUG=true ./start.sh
```

If the image comes out **skewed or squashed**, the PNG is not grayscale: `eips`
only accepts 8-bit gray with no alpha channel. On the generator side that check
is automatic (`make inspect`).

## The indoor temperature

The dashboard arrives from the cloud with a dash where the indoor temperature
goes — right of the rule that splits the temperature band, under the label
*INTERNA* — and the Kindle fills it in. It has to be that way round: the sensor
is on the device, the image is built four hundred kilometres away, and the
device cannot authenticate anywhere to send a number back.

**There is no ambient sensor on a Kindle 4.** The only thermometer on board is
the one inside the battery gas gauge — the same chip `gasgauge-info` already
answers for the battery level — and it measures the pack, not the room. That
makes it usable as a room thermometer only because of how this panel lives:
suspended to RAM for 29 minutes out of every 30, awake for a handful of
seconds, never charging. Self-heating is therefore small and, more importantly,
**constant**, which is exactly what an offset can absorb.

What you get: about half a degree of resolution (the utility answers in whole
degrees Fahrenheit), a lag of a few hours behind a real change in the room, and
an accuracy that depends entirely on the calibration below. Good enough to see
that the living room is at 19 and not 23. Not a laboratory instrument.

### Does this device have it at all

```sh
/mnt/us/dashboard/local/indoor-temp.sh --probe
```

It prints what `gasgauge-info -k` answers, lists every sysfs file on the device
that looks like a thermometer, and ends with the reading it would draw. If the
first section is an error and the second is empty, the feature is not available
on this device: set `INDOOR_TEMP=false` in `local/env.sh` and the dashboard
keeps its dash. If instead the probe turns up a sysfs file with a finer
resolution than whole Fahrenheit, point `INDOOR_TEMP_CMD` and
`INDOOR_TEMP_UNIT` at it:

```sh
export INDOOR_TEMP_CMD="cat /sys/class/power_supply/max170xx_battery/temp"
export INDOOR_TEMP_UNIT=dC        # F, C, dC (tenths), mC (thousandths)
```

### Calibrating the offset

The reading sits **above** the room, so the offset is almost always negative.
Measure it once, in place, and only in place:

1. Hang the panel where it will live and let the normal cycle run for a few
   hours — not straight after a charge, which leaves the pack warm for a long
   time, and not right after moving it from another room.
2. Read what the sensor says, uncalibrated:

   ```sh
   /mnt/us/dashboard/local/indoor-temp.sh --raw      # e.g. 23.4
   ```

3. Read a thermometer you trust, next to the Kindle, at the same moment.
4. Set the difference in `local/env.sh`:

   ```sh
   # thermometer 21.0, Kindle 23.4  ->  21.0 - 23.4
   export INDOOR_TEMP_OFFSET=${INDOOR_TEMP_OFFSET:--2.4}
   ```

5. Check the result, and the whole conversion behind it:

   ```sh
   . /mnt/us/dashboard/local/env.sh
   /mnt/us/dashboard/local/indoor-temp.sh --debug
   # source=gasgauge-info -k unit=F raw=23.4C offset=-2.4C calibrated=21.0C drawn=21 …
   ```

Redo it if you move the panel: the offset is a property of that wall, that
enclosure and that duty cycle, not of the device. Two figures far apart —
say more than 5 °C — mean something else is wrong: the device had just woken
from a charge, or the sensor is not the one you think it is.

Readings outside `INDOOR_TEMP_MIN`..`INDOOR_TEMP_MAX` (−10..50 °C) are treated
as a broken sensor: nothing is drawn and the dash stays. On a wall, no number
beats a wrong one.

### How the number gets on screen

`kindle-dash` calls `/usr/sbin/eips` inline and offers no hook that runs once
the screen is up, so the installer rewrites those call sites to
`local/draw.sh`, a drop-in wrapper: it draws the image with the real `eips`,
then writes the value on top of it with a second call.

```
eips -g dash.png                                        the dashboard, dash included
fbink -q -F IBM -S 3 -x 0 -y 0 -X 492 -Y 126 -- " 21"   the value, in the blank
```

The second call is **not** `eips`. `eips` has one font and one size, 12×20 px
cells, which next to an outdoor temperature 96 px tall reads as a footnote.
[`fbink`](https://github.com/NiLuJe/FBInk) scales its 8×16 bitmap font by a
whole number — `-S 3` gives characters of 24×48 px — and `-X`/`-Y` place them to
the pixel instead of to the cell.

It is a static ARM binary, not ours to vendor: download the **legacy** build
(the Kindle 4 is an einkfb device, not one of the newer mxcfb ones) from [its
releases](https://github.com/NiLuJe/FBInk/releases), drop it in `kindle/fbink`,
and `install.sh` carries it to `/mnt/us/dashboard/fbink`. Run that second line
by hand once, from the device, and check the flags against `fbink -h`: they are
the one thing here a future version could rename.

**Without it nothing breaks**: `draw.sh` falls back to `eips` and writes the
value small, centred in the very same blank.

`INDOOR_TEMP_X/Y/SCALE/CHARS` in `local/env.sh` say where the value goes and how
big it is drawn, and must match `INDOOR_SLOT_X/Y`, `INDOOR_SCALE` and
`INDOOR_SLOT_CHARS` in `src/k4weather/model.py`, which is where the hole is
left. `tests/test_kindle.py` fails when the two drift apart. The eips fallback
derives its own cell coordinates from those same four numbers, so there is one
slot to move and not two: if the value lands off its blank, `INDOOR_TEMP_X/Y`
are the knobs — in pixels, so the correction is as fine as the error — and the
generator has to move by the same amount, or the dash underneath will still be
sitting where it was.

Two details of the wrapper worth knowing:

- **the sleeping screen gets nothing.** It is not the dashboard and has no slot.
- **a failed refresh gets nothing either.** When the download fails,
  `kindle-dash` leaves the previous image on screen; writing a fresh number
  over a stale dashboard would be the one genuinely misleading combination.

## The real start

```sh
ssh root@192.168.15.244 /mnt/us/dashboard/start.sh
```

It starts in the background, logs to `/mnt/us/dashboard/logs/dash.log`, and
after ten seconds or so the device suspends. From then on it wakes by itself at
:15 and :45.

## Starting it from the Kindle, without a computer

`install.sh` also puts a KUAL extension in `/mnt/us/extensions/k4weather`, so
the panel can be brought up from the device's own menu — no cable, no SSH.
Three entries, under **k4-weather**:

| Entry | What it does |
|---|---|
| *Meteo: avvia il pannello* | the real start, detached (see below) |
| *Meteo: prova (scarica e disegna)* | one download, one draw, no loop and no suspend — the reader keeps running underneath |
| *Meteo: ferma e torna al lettore* | `stop.sh` followed by `framework start` |

KUAL itself is not part of this project: it has to be installed already, from
[its own page](https://wiki.mobileread.com/wiki/KUAL). On a Kindle 4 it is the
KDK build, a kindlet that runs inside the framework — which is the whole reason
the start entry is not simply a menu item pointing at `start.sh`, the way
kindle-dash's own extension is.

**Why the wrapper.** The first thing `dash.sh` does is stop the framework, and
KUAL lives inside it. A loop launched as a child of the menu is in the
framework's session and gets torn down with the thing it just killed. So
`bin/start.sh` puts it in a session of its own with `setsid` first — falling
back to `nohup` and a double fork where busybox has no `setsid` — and only then
lets go of it. It also refuses to start a second loop, which would mean two
processes competing for the screen and for the RTC wakeup.

Everything these scripts have to say goes on the screen with `eips` as well as
into `logs/kual.log`: a device driven from its own menu has no terminal to
print to. The messages are in Italian, like the panel.

**On the stop entry.** While the dashboard runs the framework is down, so KUAL
is not on screen and this entry cannot be reached — the way back is a reboot
(power button held for ~20 seconds), which comes back a reader because nothing
starts the dashboard at boot. What the entry is for is the untidy case: a loop
left running behind a framework that is still up. It is safe to pick when
nothing is running.

## Stopping it and taking the Kindle back

```sh
ssh root@192.168.15.244
/mnt/us/dashboard/stop.sh        # stops the loop
/etc/init.d/framework start      # turns the ebook reader back on
```

`stop.sh` on its own leaves the screen frozen and the framework down: without
the second command it looks like the Kindle has died. When in doubt, a reboot
(power button held for ~20 seconds) puts everything back.

The moment to catch it is the 10-second window before suspend. Miss it and the
device only becomes reachable again at the next wake-up — at most 30 minutes
later.

## Power draw

With a refresh every 30 minutes and suspend to RAM in between, expected battery
life is in the order of weeks. To stretch it, restrict `REFRESH_SCHEDULE` to
the hours you actually look at the screen, for example `"15,45 7-23 * * *"`.

Careful: raising the interval beyond `SLEEP_SCREEN_INTERVAL` (3600 s) makes the
"kindle is sleeping" screen appear instead of the dashboard. If you add a night
pause and want the weather to stay visible, raise that threshold too.
