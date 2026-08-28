# The client on the Kindle 4

The Kindle computes almost nothing: it wakes up, downloads the images, draws
one, writes its own temperature and its own battery level on top of it and goes
back to sleep. All the
fragile parts — waiting for Wi-Fi, modern TLS, suspend to RAM, wake-up
scheduled by the hardware clock — are already solved by
[pascalw/kindle-dash](https://github.com/pascalw/kindle-dash), used here as the
runtime. This directory holds the files that replace or extend its own:

| File | Role |
|---|---|
| `local/env.sh` | configuration of the loop, and of everything below |
| `local/fetch-dashboard.sh` | the download: every location, with retries |
| `local/locations.sh` | the list, the cycle and the state file (sourced, not run) |
| `local/interact.sh` | listens to the page buttons and moves between locations |
| `local/suspend.sh` | suspend to RAM, and telling the clock from a person |
| `local/indoor-temp.sh` | the temperature sensor, read and calibrated |
| `local/battery.sh` | the gas gauge, read as whole per cent |
| `local/draw.sh` | `eips` plus the two device readings stamped on top, with `fbink` |
| `extensions/k4weather/` | the KUAL menu, to start the panel without a computer |
| `tools/keytest.sh` | diagnostics for the buttons, run on the device (below) |
| `fonts/indoor.ttf` | the page's own font, subset and with its features frozen, so the device can draw its readings in it (below) |
| `fbink` | not in this repository: fetched by install.sh, draws the values (below) |

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

Steps 4 and 5 are the two the installer rewrites, and
[switching locations](#switching-locations) is why.

Two behaviours that explain how our configuration is written:

- **If the fetch exits non-zero, the screen is not touched at all.** That is
  why `fetch-dashboard.sh` retries and then fails instead of writing an empty
  file: an old dashboard beats a blank panel.
- **One full refresh every `FULL_DISPLAY_REFRESH_RATE` partial updates.**
  Partial updates do not flash the screen but accumulate ghosting; the full one
  clears it.

## Installation

Jailbreak, USBNetwork and Wi-Fi have to be configured already.

The scripted way, from the computer, is [`install.sh`](install.sh): it downloads
the runtime, applies our configuration, normalises the line endings, checks the
image URL, copies everything to the device and deliberately starts nothing.

```sh
./kindle/install.sh                      # uses root@192.168.15.244
./kindle/install.sh root@192.168.1.50    # Kindle reachable over Wi-Fi
```

On Windows the same script runs under Git Bash, or from PowerShell through
[`install.ps1`](install.ps1), which only finds that bash and hands over to it:

```powershell
.\kindle\install.ps1
```

### Without SSH, over the USB disk

```sh
./kindle/install.sh --drive E:
```

Same build, same patching, same line endings — only the transport differs. In
USB drive mode the Kindle exposes `/mnt/us` as a volume, so `dashboard` and
`extensions` are simply written to it; the KUAL menu then starts, tests and
diagnoses the panel from the device itself. Nothing is lost but the `chmod`,
and FAT stores no execute bit anyway, which is why every menu action names
`/bin/sh` and every script tests for `-f` rather than `-x`.

It refuses to write to a volume with no `system` and no `documents` directory
at its root, and it only ever adds and overwrites: nothing on the Kindle is
deleted.

This is the way out when the USB network link cannot be made to work — on
Windows that is a real possibility and not a fault of this project, see below.
Toggle usbnet off with `;un` on the device and the Kindle comes back a drive.

By hand it is four steps:

```sh
# 1. Download the runtime. The archive is a .tgz that expands flat.
mkdir -p kindle-dash
curl -sSL "$(curl -sSL https://api.github.com/repos/pascalw/kindle-dash/releases/latest \
  | grep browser_download_url | cut -d'"' -f4 | head -n1)" | tar xz -C kindle-dash

# 2. Replace the example configuration with ours, and rewrite the three call
#    sites kindle-dash offers no hook for: the drawing (see "The indoor
#    temperature"), the sleep window and the suspend (see "Switching locations")
cp kindle/local/*.sh kindle-dash/local/
cp kindle/fbink      kindle-dash/fbink        # optional, see below
sed -i.bak 's|/usr/sbin/eips|"$DIR/local/draw.sh"|g' kindle-dash/dash.sh
sed -i.bak \
  -e 's|^    sleep 10$|    "$DIR/local/interact.sh" 10|' \
  -e 's|^    rtc_sleep "\$next_wakeup_secs"$|    "$DIR/local/suspend.sh" "$next_wakeup_secs"|' \
  kindle-dash/dash.sh

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

`BASE_URL` in `fetch-dashboard.sh` already points at the GitHub Pages site that
serves the `output` branch — not at `raw.githubusercontent.com`, whose rate
limit would freeze the panel ([why, and how to turn Pages
on](../docs/setup.md#3-turn-on-pages)). It embeds owner and repository name, so
it needs changing if either does. Nothing else is a URL: the device asks for
`locations.txt` and then for exactly the file names that file gives it, so the
naming of the images is never guessed on this side.

### Carriage returns

The one platform difference that reaches the device. busybox `ash` does not
treat a carriage return as whitespace — it is an ordinary character, and it
becomes part of the value of whatever assignment it terminates. A copy of these
scripts with CRLF line endings therefore reads

```sh
DASH_DIR=${DASH_DIR:-/mnt/us/dashboard}     # -> "/mnt/us/dashboard<CR>"
export INTERACT=${INTERACT:-true}           # -> "true<CR>", which is not "true"
```

so the panel reports that it is not installed, and the page buttons stop being
read — neither of which says anything on a device with no terminal. Git for
Windows produces exactly that unless it is told otherwise.

Three things now prevent it, in the order they act: the `.gitattributes` at the
root of the repository forces LF on every platform, `install.sh` strips any
remaining CR from every script before it copies it, and *Meteo: avvia il
pannello* repairs an installation that already has them. *Meteo: diagnostica*
names the offending files. If you cloned before `.gitattributes` existed, run
`make lineendings` once.

### If SSH times out with USBNetwork on

USBNetwork **is not a DHCP server**, on any operating system: the host end of
the link never gets an address on the Kindle's subnet by itself, and until it
has one the packets leave through the Wi-Fi and die there. `install.sh` detects
this and prints the right command for the platform it is running on.

On **Windows** the Kindle appears as an RNDIS adapter — but find it by the
*driver description*, never by the connection name. `netsh interface ipv4 show
interfaces` lists `Ethernet 2`, `Ethernet 3` and so on, and which of them is
the Kindle is an accident of enumeration order: on this author's machine
`Ethernet 2` is a USB network dongle carrying the whole LAN, and putting the
Kindle's address on it takes the computer off its own network.

```powershell
Get-NetAdapter | Where-Object InterfaceDescription -match 'RNDIS|Remote NDIS'
```

Then, from an *administrator* PowerShell, with the `Name` that came back:

```powershell
netsh interface ipv4 set address name="<that name>" static 192.168.15.201 255.255.255.0
```

If that query returns nothing, look under **Ports (COM & LPT)** before
concluding anything, because the likeliest cause on Windows is not that the
Kindle is absent:

```powershell
Get-PnpDevice -PresentOnly | Where-Object InstanceId -match 'VID_0525'
```

In usbnet mode the Kindle does not use Amazon's own USB vendor id at all — it
presents the **Linux gadget, `0525:a4a2`**, whose bus description reads
`RNDIS/Ethernet Gadget`. Windows 10 and 11 take that descriptor for a CDC-ACM
serial port and bind `usbser.sys`, so a perfectly healthy Kindle turns up as
`Dispositivo seriale USB (COM6)` and never becomes a network adapter at all.
The same fault hits the Raspberry Pi Zero and Android tethering.

The driver it should have is already in Windows; it just has to be pointed at
the device by hand, from Device Manager as an administrator:

1. **Ports (COM & LPT)** → the COM device → **Update driver**
2. **Browse my computer** → **Let me pick from a list**
3. **Have Disk…**, and type the path — `C:\Windows\INF` is hidden, so Browse
   will not show it:
   ```
   C:\Windows\INF\netrndis.inf
   ```
4. Model **USB RNDIS Adapter** — not the *6* variant
5. Accept the compatibility warning

Two details that cost an evening if you do not know them. **Unticking "Show
compatible hardware" is not enough**: Device Manager still filters the list to
the *Ports* setup class the device is currently in, so no network driver can
appear there at all, whatever the tick says. Naming the INF is what escapes
that. And the model to look for is **not** *Remote NDIS based Internet Sharing
Device*, which most guides on the web name: that entry comes from a Windows
Mobile INF that a current Windows 11 does not ship. What is there is:

| INF | Models it offers |
|---|---|
| `netrndis.inf` | **USB RNDIS Adapter**, USB RNDIS6 Adapter |
| `rndiscmp.inf` | Remote NDIS Compatible Device |

`USB RNDIS Adapter` is the one to take: it sets `Rndis5to6Conversion=1`, which
is exactly what a Linux gadget speaking RNDIS 5.x needs. If it does not take,
`rndiscmp.inf` → *Remote NDIS Compatible Device* is the fallback.

The device then moves to *Network adapters* and the `netsh` step above applies.
It is reversible throughout, from Properties → Driver → Roll Back Driver.

Only if there is no RNDIS adapter *and* no `VID_0525` device is the Kindle
really not presenting itself over USB: a power-only cable (a charging LED
proves nothing — that is the one thing such a cable does do), or USBNetwork
switched off, which is the default. Turn it on from the device with KUAL >
USBNetwork > *toggle usbnetwork*, or by typing `;un` into the search box.
`install.sh` distinguishes all three cases and says which one it is.

On **macOS**, the same thing with the tools that exist there. macOS brings the
interface up (it appears
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

# The download alone first, without touching the screen. It fetches every
# location, so what to look at is the cache, not only the file it hands back.
./local/fetch-dashboard.sh /tmp/test.png && echo OK && ls -l /tmp/test.png
ls -l cache/                      # one PNG per location, plus locations.txt
cat state/location                # the one that would be on screen
./xh --version                    # must run: it is a static ARM binary

# The two sensors, without touching the screen either
./local/indoor-temp.sh --probe
./local/battery.sh --probe

# Then the drawing, both values included
. ./local/env.sh && ./local/draw.sh -f -g /tmp/test.png

# Finally the whole loop, in the foreground
DEBUG=true ./start.sh
```

If the image comes out **skewed or squashed**, the PNG is not grayscale: `eips`
only accepts 8-bit gray with no alpha channel. On the generator side that check
is automatic (`make inspect`).

## Switching locations

The panel shows one place at a time and the page buttons walk through the list
in `config.yaml`. From the wall it is two gestures:

1. **press power** — briefly. The screen does not change, the panel is now
   awake and listening;
2. **press a page button** — forward for the next location, back for the
   previous one. The image changes in about a second, and every press buys
   another fifteen seconds to press again. Then it goes back to sleep, on
   schedule: pressing power at :20 does not postpone the :45 refresh.

The same window also opens for ten seconds after every scheduled refresh, so at
:15 and :45 the buttons work without touching power at all.

### Why power first, and not just the buttons

Because on a Kindle 4 the keypad cannot wake the device. It is not a setting:

```sh
cat /sys/devices/platform/tequila-keypad/power/wakeup     # prints nothing
cat /sys/devices/platform/mxc_rtc.0/power/wakeup          # enabled
```

An **empty** value there is not the same as `disabled`. The kernel prints
`enabled`/`disabled` only for devices that *can* wake the system and an empty
string for those that cannot, so the driver never registered the keypad as a
wakeup source and writing to the file is refused. Measured twice with
[`tools/keytest.sh`](tools/keytest.sh): with the alarm armed for two minutes,
pressing a page button changed nothing and no input event was delivered across
the suspend; pressing power woke the device at 18 and 25 seconds, and the page
buttons were then perfectly readable with the framework down.

So: the power slider wakes it, below the evdev layer where the buttons live,
and the buttons choose. That is the whole design.

### The buttons

Measured on this device, not taken from `input.h` — the codes are not the
standard meanings and two of them are outside the normal range:

| Button | Code | Device |
|---|---|---|
| page forward, right side | 191 | `event0` |
| page forward, left side | 104 | `event0` |
| page back, right side | 109 | `event0` |
| page back, left side | 193 | `event0` |
| 5-way in / left / right | 194 / 105 / 106 | `event1` |
| MENU / BACK / HOME | 139 / 158 / 102 | `event0` |

Both sides are accepted for each direction, so the panel answers whichever
thumb is on it. Everything else is ignored on purpose: a Kindle that did
something unexpected when someone pressed HOME would be worse than one that did
nothing. The power slider is **not** in the table because it is not an evdev
key at all on this device — it sits on `/sys/devices/virtual/misc/yoshibutton`
and never reaches the input layer, which is exactly why it can wake the device
and the others cannot.

`KEY_NEXT` and `KEY_PREV` in `local/env.sh` hold those codes as space-separated
lists. To drive the panel with the 5-way instead:

```sh
export KEY_DEVICE=${KEY_DEVICE:-/dev/input/event1}
export KEY_NEXT=${KEY_NEXT:-"106"}     # push right
export KEY_PREV=${KEY_PREV:-"105"}     # push left
```

### How it works

The device holds three things under `/mnt/us/dashboard`:

```
cache/locations.txt   the list CI published: id <TAB> image <TAB> name
cache/<id>.png        one image per location, downloaded ahead of being asked for
state/location        the id on screen now, which survives a reboot
```

**Every location is downloaded on every refresh**, not just the one on screen.
Switching then costs a file copy and a redraw — about a second, with the Wi-Fi
off. Downloading on demand instead would mean waking the radio for each press:
ten seconds of frozen screen, and nothing at all when the network is down. Five
images are about a hundred kilobytes, next to nothing beside the cost of
associating with the access point, which the refresh is paying anyway.

**What is stored is the id, never a position in the list.** Reordering
`config.yaml` therefore costs nothing, and removing a location leaves a state
file naming something that no longer exists — which is noticed and corrected on
the spot, instead of silently showing a different place under the wrong name. A
location whose image has never downloaded is skipped by the buttons entirely: a
press that led to a blank screen would look like a crash.

**The image and the state file move in that order.** The id is recorded only
once the panel is actually showing it, so a power cut between the two leaves the
device naming what is on its screen rather than what it meant to draw.

### The two rewrites in `dash.sh`

`kindle-dash` has no hooks: `install.sh` rewrites two lines of its main loop,
the same way it already redirects `eips` to `local/draw.sh`.

| Upstream | Becomes | Why |
|---|---|---|
| `sleep 10` | `local/interact.sh 10` | that window did nothing but pass time; now it listens |
| `rtc_sleep "$next_wakeup_secs"` | `local/suspend.sh "$next_wakeup_secs"` | the same suspend, plus knowing what ended it |

`suspend.sh` compares how long the device actually slept against the alarm it
set. Short by more than `EARLY_WAKE_MARGIN` seconds means a person pressed
power, and the listening window opens; otherwise the clock did its job and the
loop carries on. The remaining time is then slept off, so a wake-up by hand
costs the schedule nothing.

`rtc_sleep` is left in `dash.sh`, unused, so the file stays as close to
upstream as it can. The installer fails loudly if either line has moved — that
is a kindle-dash release having changed the shape of its loop, and it wants
looking at rather than silently ignoring.

One quirk worth knowing about, and handled: upstream arms the hardware clock
only when `wakeup_enable` reads `0`. After a wake-up that the clock did not
cause, a stale value left in that file would make every later arming a no-op
and the panel would sleep until somebody pressed power again. `suspend.sh`
reports what it found, clears it, and arms its own.

### Turning it off

```sh
export INTERACT=${INTERACT:-false}     # in local/env.sh, then restart the loop
```

The listening window becomes the plain `sleep` it replaced — abort window
included — and the panel shows the first location in the list and nothing else.
The images for the others are still downloaded, which costs a few kilobytes and
keeps the feature one variable away.

### If the buttons do nothing

[`tools/keytest.sh`](tools/keytest.sh) runs on the device and answers this in
three phases, least invasive first. It needs nothing but `dd` and the shell —
this Kindle has no `od`, no `hexdump` and no `xxd`, which is why it decodes raw
`input_event` structures the long way round.

```sh
ssh root@192.168.15.244 'cat > /mnt/us/keytest.sh && chmod +x /mnt/us/keytest.sh' \
  < kindle/tools/keytest.sh

ssh root@192.168.15.244 /mnt/us/keytest.sh probe      # what this device exposes
ssh -t root@192.168.15.244 /mnt/us/keytest.sh keys    # which code each button sends
ssh root@192.168.15.244 /mnt/us/keytest.sh wake       # what can wake it from suspend
ssh root@192.168.15.244 /mnt/us/keytest.sh wake-log   # the verdict of the last one
```

`probe` and `keys` are safe at any time. `wake` suspends the device: it detaches
itself, drops the SSH session with it, and leaves its answer in
`/mnt/us/keytest-wake.log`. There is always an RTC alarm armed as a safety net,
so the worst case is a wait — and holding power for ~20 seconds reboots out of
anything. Run `wake --dry-run` first: it does everything except the one
irreversible step and stays attached to the terminal.

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
then writes each value on top of it with a call of its own.

```
eips -g dash.png                                          the dashboard, dashes included
fbink -q -t regular=fonts/indoor.ttf,px=30,top=134,      bottom=634,left=492,right=60,padding=BOTH -- " 21"  the temperature
fbink -q -t regular=fonts/indoor.ttf,px=15,top=769,      bottom=15,left=542,right=34,padding=BOTH -- " 87"   the battery level
```

The second call is **not** `eips`, and it draws in **the page's own font**.

`eips` has one font and one size, 12×20 px cells, which beside the 26 px
figures across the rule reads as a footnote — that is what the panel showed for
as long as fbink was missing.
[`fbink`](https://github.com/NiLuJe/FBInk) can do better in two ways, and
`local/draw.sh` tries them in order, falling through on failure:

| | draws with | looks like |
|---|---|---|
| 1 | `fbink -t`, `fonts/indoor.ttf` | Inter SemiBold at the size of the figures beside it — the same thing |
| 2 | `fbink -F IBM -S 2` | its own bitmap face, the right size, visibly another program |
| 3 | `eips` | 12×20 cells, small |

**The font is the interesting part.** fbink renders through `stb_truetype`,
which reads outlines and applies no OpenType features — while the page asks for
`font-feature-settings: "tnum" 1, "cv05" 1`, so its digits are the tabular
variants. Handed the page's own woff2, fbink would draw different glyph shapes
of different widths: Inter's proportional `1` advances 0.42 em against `4` at
0.67, so the reading would also jitter between refreshes.

`tools/indoor_font.py` builds `kindle/fonts/indoor.ttf` instead: it applies
those substitutions to the character map directly, widens the blank to a digit
so that padding right-aligns exactly, and subsets the result to the eleven
characters a temperature can use. 8 KB, committed, and rebuilt with
`make indoor-font` when the page's font or its features change.

Two consequences of that widened blank, both load-bearing: `" 21"` and `"-10"`
end in the same place against the degree sign, and a padded string fills the
box — so the background fbink paints behind it covers the dash the image
carries for a sensor that cannot be read. A narrower string would leave that
dash struck through the digits.

**Where fbink comes from.** Not from its own releases, whatever this file used
to say: FBInk publishes a source tarball and has never published a build, so
the instruction could not be followed and the binary was simply never
installed. `install.sh` fetches it from **KOReader**, whose `kindle` package is
armv7 softfloat against an old glibc — what a Kindle 4 runs — and whose `fbink`
is the standalone binary its own startup scripts call. It needs `libc` and
`libm` and nothing else. Drop your own build in `kindle/fbink` and that is used
instead.

**Without any of it nothing breaks**: `draw.sh` falls back a step at a time,
and the last step still writes the value into the very same blank.

`INDOOR_TEMP_X/Y/SCALE/CHARS` in `local/env.sh` say where the value goes and how
big it is drawn, and must match `INDOOR_SLOT_X/Y`, `INDOOR_SCALE` and
`INDOOR_SLOT_CHARS` in `src/k4weather/model.py`, which is where the hole is
left. `tests/test_kindle.py` fails when the two drift apart, and it checks the
same four numbers a third time where `local/draw.sh` repeats them as its own
fallbacks. The eips step derives its cell coordinates from them too, so there
is one slot to move and not two: if the value lands off its blank,
`INDOOR_TEMP_X/Y` are the knobs — in pixels, so the correction is as fine as
the error — and the generator has to move by the same amount, or the dash
underneath will still be sitting where it was.

Three details of the wrapper worth knowing:

- **the sleeping screen gets nothing.** It is not the dashboard and has no slots.
- **a failed refresh gets nothing either.** When the download fails,
  `kindle-dash` leaves the previous image on screen; writing fresh numbers
  over a stale dashboard would be the one genuinely misleading combination.
- **a reading that cannot be taken gets nothing.** The dash the image carries
  stays, and says so. Each value is independent: a broken sensor does not stop
  the other one being drawn.

## The battery level

The footer carries a dash and a per-cent sign at its right end, past the
generation time, and the Kindle writes the number into it on the same pass that
writes the temperature. The reading comes from `gasgauge-info -c`, the utility
`kindle-dash` already calls once a cycle to put the level in its log.

```sh
/mnt/us/dashboard/local/battery.sh --probe
```

Same shape as the temperature probe: what the utility answers, the sysfs files
that look like a capacity, and the number that would be drawn. `BATTERY=false`
in `local/env.sh` turns it off and leaves the dash.

**It is not live, and it is not meant to be.** The panel is suspended to RAM
for 29 minutes out of every 30, so the level is read when the device wakes to
draw — exactly as old as the image beside it, at worst half an hour. On a
battery that lasts weeks that is a figure on a wall, not an instrument.

Two things differ from the temperature above.

**No `eips` step.** The number lives in the footer, whose type is 12.4 px; an
`eips` cell is 12×20 px, so drawn by `eips` the battery level would be the
largest thing in the bar it sits in. Without `fbink` it is simply not drawn and
the dash stays — where the temperature, at 25 px, can afford to come out small.

**A smaller `px`.** `BATTERY_PX` is 15 against the temperature's 30, and it is
not an arbitrary number: at 15 every character of `fonts/indoor.ttf` advances
exactly 8 px, which is the width of one cell of fbink's bitmap face at
`BATTERY_SCALE=1`. Both ways of filling the blank therefore fill exactly the
same 24×16 box, and the padding that right-aligns `" 87"` against the per-cent
sign works the same in both.

`BATTERY_X/Y/SCALE/CHARS` are the same kind of coupling as their
`INDOOR_TEMP_*` counterparts and must match `BATTERY_SLOT_X/Y`,
`BATTERY_SCALE` and `BATTERY_SLOT_CHARS` in `src/k4weather/model.py`.

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
Five entries, under **k4-weather**:

| Entry | What it does |
|---|---|
| *Meteo: avvia il pannello* | the real start, detached (see below) |
| *Meteo: prova (scarica e disegna)* | one download, one draw, no loop and no suspend — the reader keeps running underneath |
| *Meteo: prova i tasti pagina* | twenty seconds of the real listening window, then a verdict on screen |
| *Meteo: ferma e torna al lettore* | `stop.sh` followed by `framework start` |
| *Meteo: diagnostica* | writes `k4weather-diagnostica.txt` to the root of the USB drive; changes nothing |

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

**Why the start entry waits, and then checks.** `start.sh` backgrounds
`dash.sh` and returns immediately, so its exit status says nothing at all about
whether the loop survived — which is how a start that failed looked exactly like
a start that worked. The detached half now sleeps a few seconds before
launching, so KUAL has finished leaving before the framework is pulled down
underneath it, and then waits and asks the process table whether `dash.sh` is
still there. If it is not, it copies the tail of `dash.log` into `kual.log`,
starts the framework again — a Kindle that is a Kindle is a far better failure
than a black screen — and says so on the screen.

**On the button test.** *Meteo: prova i tasti pagina* runs `local/interact.sh`
itself, in the conditions it really runs in: the framework stopped, the panel
on screen, twenty seconds of listening. Not a copy of the decoding — a test
that passes against a second implementation proves nothing about the first. It
then distinguishes the three failures that look identical from the outside:

| On screen | What it means |
|---|---|
| *OK, N cambi su M pressioni* | the whole path works |
| *tasti letti ma codici sconosciuti* | the buttons send codes this device was never told about. They are in `kual.log`; put them in `KEY_NEXT` / `KEY_PREV` |
| *tasti letti, nessun cambio* | the buttons work and the cycle does not — usually one location with an image |
| *nessuna pressione rilevata* | nothing reached the input layer at all |

The framework is started again whichever way it ends, signals included.

**Why the entries name `/bin/sh` and an absolute path.** Both halves of

```json
"action": "/bin/sh /mnt/us/extensions/k4weather/bin/start.sh"
```

are there to remove an assumption. KUAL runs an action by writing a throwaway
`#!/bin/ash` script — `{ <action> ; } 2>>/var/tmp/KUAL.log &` — and launching it
with the working directory set to the extension folder. A *relative* action
rides on that last part, which is a promise made by a Java kindlet on a 2011
device; kindle-dash's own extension uses an absolute path and so does this one.
Naming `/bin/sh` removes the other assumption: `/mnt/us` is FAT, where the
execute bit is synthesised from the mount options rather than stored per file,
so calling a script directly is a bet on how the partition happens to be
mounted.

**When a menu entry appears to do nothing.** This is the failure mode of every
KUAL extension, and it looks the same whatever caused it: the status line prints
the action, the menu exits, the reader comes back, and nothing else happens. The
error is not lost — it is in a file nothing shows you:

| File | What is in it |
|---|---|
| `/var/tmp/KUAL.log`, `/mnt/us/extensions/KUAL.log` | KUAL's own — it has used both paths. The shell's `not found` / `Permission denied` for a menu action goes here and **nowhere else**. Look here first. |
| `/mnt/us/extensions/k4weather/kual.log` | what these scripts say for themselves, including runs where `/mnt/us/dashboard` was not there to log into |
| `/mnt/us/dashboard/logs/dash.log` | the loop itself, once it starts |

*Meteo: diagnostica* collects all three, plus the state of the installation and
an actual "can this device execute a script" probe, into
`k4weather-diagnostica.txt` at the root of the USB drive — readable by plugging
the Kindle into any computer. That is the entry to reach for first, because the
alternative is reading a screen that gets repainted before you can.

Everything these scripts have to say goes on the screen with `eips` as well as
into the log: a device driven from its own menu has no terminal to print to.
Failures say it twice, a few seconds apart, because KUAL exits and the framework
repaints the home screen over the first attempt. The messages are in Italian,
like the panel.

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

The moment to catch it is the 10-second window before suspend — the same one
that listens for the page buttons. `interact.sh` watches for its parent going
away and stops with it, so `stop.sh` does not leave one counting down behind a
framework that has just come back. Miss the window and the device only becomes
reachable again at the next wake-up — at most 30 minutes later, or straight
away by pressing power, which now wakes it into that same window.

## Power draw

With a refresh every 30 minutes and suspend to RAM in between, expected battery
life is in the order of weeks. To stretch it, restrict `REFRESH_SCHEDULE` to
the hours you actually look at the screen, for example `"15,45 7-23 * * *"`.

Switching locations barely shows up next to that. Downloading five images
instead of one adds about a hundred kilobytes to a transfer whose real cost is
associating with the access point; a wake-up by hand keeps the device awake for
half a minute with the radio **off**, and the screen refreshes it does are the
same ones a scheduled update would have done anyway.

Careful: raising the interval beyond `SLEEP_SCREEN_INTERVAL` (3600 s) makes the
"kindle is sleeping" screen appear instead of the dashboard. If you add a night
pause and want the weather to stay visible, raise that threshold too.
