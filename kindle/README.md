# The client on the Kindle 4

The Kindle computes nothing: it wakes up, downloads a PNG, draws it and goes
back to sleep. All the fragile parts — waiting for Wi-Fi, modern TLS, suspend
to RAM, wake-up scheduled by the hardware clock — are already solved by
[pascalw/kindle-dash](https://github.com/pascalw/kindle-dash), used here as the
runtime. This directory holds only the two configuration files that replace its
own.

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

# 2. Replace the example configuration with ours
cp kindle/local/env.sh             kindle-dash/local/env.sh
cp kindle/local/fetch-dashboard.sh kindle-dash/local/fetch-dashboard.sh

# 3. Copy to the Kindle (USBNetwork on, cable connected)
rsync -vr kindle-dash/ root@192.168.15.244:/mnt/us/dashboard

# 4. Restore the executable bits, which the transfer can lose
ssh root@192.168.15.244 'chmod +x /mnt/us/dashboard/*.sh \
  /mnt/us/dashboard/local/*.sh /mnt/us/dashboard/xh /mnt/us/dashboard/next-wakeup'
```

As an alternative to step 3, a Kindle plugged in as a normal USB drive exposes
`/mnt/us` as a disk: you can copy the `dashboard` folder in Finder and use SSH
only for the commands.

`DASH_URL` in `fetch-dashboard.sh` already points at the `output` branch of the
repository. It only needs changing if you rename the repository.

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

# Then the drawing
eips -f -g /tmp/test.png

# Finally the whole loop, in the foreground
DEBUG=true ./start.sh
```

If the image comes out **skewed or squashed**, the PNG is not grayscale: `eips`
only accepts 8-bit gray with no alpha channel. On the generator side that check
is automatic (`make inspect`).

## The real start

```sh
ssh root@192.168.15.244 /mnt/us/dashboard/start.sh
```

It starts in the background, logs to `/mnt/us/dashboard/logs/dash.log`, and
after ten seconds or so the device suspends. From then on it wakes by itself at
:15 and :45.

To start it from the menu instead of over SSH, copy `KUAL/kindle-dash` from the
[kindle-dash repository](https://github.com/pascalw/kindle-dash/tree/master/KUAL)
into `/mnt/us/extensions` — it is not part of the release.

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
