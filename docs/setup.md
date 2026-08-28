# Putting it into service

The full procedure, from the repository to the Kindle hanging on the wall.

## Why the repository is public

The Kindle 4 downloads the image with a minimal HTTP client and has no way to
authenticate securely: a token written in clear text on an unprotected FAT
partition is worse than the problem it solves. The source therefore has to be
readable without credentials.

There is also a cost reason, which settles the question on its own: 48 runs a
day of a couple of minutes each add up to roughly **3,000 Actions minutes a
month**, against the 2,000 included in the free plan for private repositories.
On public repositories Actions has no limit.

```
k4-weather (public)
  main    code, config, workflow
  output  dashboard-<id>.png × N  ──►  GitHub Pages  ──►  Kindle
          locations.json / .txt
```

The `output` branch is rewritten on every run with a force push of a single
commit: it accumulates no history and stays a constant size.

> The repository is public: **the images and the code are readable by anyone**,
> and each dashboard shows the name of its location — so the list in
> `config.yaml` is public as well, and it is a list of places you care about.
> Commit metadata becomes public too, the author's email address included.

---

## 1. Make the repository public

```sh
gh repo edit dev-whiterice/k4-weather --visibility public \
  --accept-visibility-change-consequences
```

## 2. Push the code

```sh
git add -A
git commit -m "weather dashboard for the Kindle 4"
git push origin main
```

The push to `main` already starts the workflow:
[`dashboard.yml`](../.github/workflows/dashboard.yml) triggers both on schedule
and whenever `src/`, `config.yaml` or the workflow itself changes.

## 3. Turn on Pages

The Kindle downloads the image from GitHub Pages, not from
`raw.githubusercontent.com`: raw enforces an anti-scraping rate limit per IP
address and answers `429: Too Many Requests` once it trips. The limit follows
the address rather than the account, so opening the image in a browser on the
same connection spends the budget the panel needs, and the panel then holds a
stale image until the window slides. Pages exists to serve assets and applies no
such limit.

The workflow already writes `.nojekyll` and an `index.html` next to the PNG, so
the branch needs no preparation:

```sh
gh api -X POST repos/dev-whiterice/k4-weather/pages \
  -f "source[branch]=output" -f "source[path]=/"
```

Same thing under *Settings → Pages*, choosing branch `output` and folder `/`.
The first build takes a couple of minutes, then
`https://dev-whiterice.github.io/k4-weather/` shows the dashboard — handy for
checking it from your phone, and it is the URL
[`fetch-dashboard.sh`](../kindle/local/fetch-dashboard.sh) uses.

## 4. Check the first images

```sh
gh run watch --repo dev-whiterice/k4-weather

# The manifest first: it is what the Kindle asks for before anything else, and
# it names every image that should exist.
curl -sL https://dev-whiterice.github.io/k4-weather/locations.txt
# caoria	dashboard-caoria.png	Caoria
# fumane	dashboard-fumane.png	Fumane
# ...

curl -sI https://dev-whiterice.github.io/k4-weather/dashboard-caoria.png | head -1
# HTTP/2 200
```

The Pages site itself shows all of them side by side, which is the quickest way
to see that a location you have just added really renders.

From here on the workflow restarts by itself at :07 and :37 — off the top and
the bottom of the hour, which are the two minutes the GitHub Actions scheduler
is most likely to delay or drop a run asked for.

## 5. Keep the scheduler alive (recommended)

GitHub disables scheduled workflows after **60 days without activity** on the
repository, and commits made with the automatic token **do not count**. With no
remedy, the dashboard freezes after two months.

Create a fine-grained PAT at
**github.com/settings/personal-access-tokens/new**:

| Field | Value |
|---|---|
| Token name | `k4-weather-publish` |
| Resource owner | `dev-whiterice` |
| Repository access | *Only select repositories* → `k4-weather` |
| Permissions → Repository → **Contents** | **Read and write** |

and store it as a secret:

```sh
gh secret set PUBLISH_TOKEN --repo dev-whiterice/k4-weather
```

The workflow uses it instead of the automatic token and the commits show up as
yours. Put the expiry date in your calendar: it is the only one in the project,
and when it passes publishing stops without warning.

If the token is ever rejected, the workflow does not freeze the dashboard: on
this same repository it falls back to the automatic token and records a warning
in the run summary. On a different `PUBLISH_REPO` there is no fallback and the
run fails, on purpose.

---

## 6. Kindle

One-off prerequisites: a jailbroken Kindle 4 NT, KUAL, USBNetwork for SSH, and
Wi-Fi configured. Reference: [the MobileRead
wiki](https://wiki.mobileread.com/wiki/Kindle4NTHacking).

Worth doing first: put the `fbink` binary in `kindle/fbink`, so the installer
carries it over. It is what writes on the image the two numbers only the device
can know. Without it the indoor temperature comes out small, drawn by `eips`,
and the battery level is not drawn at all — an `eips` cell is bigger than the
footer it would land in
([details](../kindle/README.md#how-the-number-gets-on-screen)).

```sh
./kindle/install.sh                      # uses root@192.168.15.244
./kindle/install.sh root@192.168.1.50    # Kindle reachable over Wi-Fi
```

On Windows, the same from Git Bash, or `.\kindle\install.ps1` from PowerShell.
If SSH over USB cannot be established there, `./kindle/install.sh --drive E:`
writes to the Kindle mounted as a disk instead and needs no network at all:
[`kindle/README.md`](../kindle/README.md#without-ssh-over-the-usb-disk).

It downloads the runtime, applies our configuration, normalises the line
endings, checks that the image is reachable, copies everything to the device
and deliberately starts nothing. The same by hand, plus what to do when SSH
times out with USBNetwork on:
[`kindle/README.md`](../kindle/README.md#installation).

Do not make `start.sh` your first move. Try the pieces one at a time — the
download, the sensor, one draw, then the whole loop with `DEBUG=true`, which
stays in the foreground and does not suspend the device:
[`kindle/README.md`](../kindle/README.md#try-it-in-debug-mode).

Once started for real, the Kindle suspends after 10-15 seconds and wakes at :15
and :45, offset by 15 minutes from generation to absorb the delay of the GitHub
Actions cron.

To change the location on the panel: **press power**, then the page buttons —
forward for the next place in the list, back for the previous one. It needs
power first because the keypad on a Kindle 4 cannot wake the device, which is a
property of the driver and not a setting:
[`kindle/README.md`](../kindle/README.md#switching-locations).

If the buttons do nothing, do not guess: **KUAL > k4-weather > *Meteo: prova i
tasti pagina*** runs the real listening window for twenty seconds and says which
of the four possible faults it is.

---

## If something goes wrong

| Symptom | Cause and remedy |
|---|---|
| `curl` on the Pages URL returns 404 | Either Pages is off (see step 3) or the `output` branch does not exist yet, because the workflow has never completed successfully |
| `429: Too Many Requests` on the image | You are on `raw.githubusercontent.com`, whose anti-scraping limit follows the IP address. Use the Pages URL, from the browser too |
| Image **skewed or squashed** on the Kindle | The PNG is not grayscale. `make inspect` catches this before publication |
| `fetch-dashboard.sh` exits with an error | No Wi-Fi, or the wrong URL. The screen keeps the last good image instead of going blank |
| The screen shows a time frozen days ago | Scheduler disabled after 60 days of inactivity: see step 5 |
| *dati non aggiornati* in the footer | The image is fresh but the Open-Meteo observation is more than 90 minutes old |
| The indoor temperature stays a dash | The sensor is unreadable or the reading is out of range: `local/indoor-temp.sh --probe` on the device says which |
| The indoor temperature lands off its blank | Move it with `INDOOR_TEMP_X/Y`, in pixels, and `INDOOR_SLOT_X/Y` in `model.py` by the same amount — or the dash underneath stays where it was |
| The indoor temperature is drawn small | `fbink` is not on the device, or not executable: `local/draw.sh` fell back to `eips`. See [`kindle/README.md`](../kindle/README.md#how-the-number-gets-on-screen) |
| The indoor temperature reads too high | Normal before calibration: it is the battery, not the room. See [`kindle/README.md`](../kindle/README.md#calibrating-the-offset) |
| The battery level stays a dash | Either `fbink` is missing — it is the only thing that draws this one — or the gauge is unreadable: `local/battery.sh --probe` on the device says which |
| The battery level is half an hour old | By design: it is read when the panel wakes to draw, so it is exactly as old as the image beside it |
| The KUAL entry starts nothing | Since the panel is launched detached, a failed start now says so on the screen and puts the tail of `dash.log` into `extensions/k4weather/kual.log`. If it does not even get that far, the installation was copied with **CRLF line endings** — see the row below |
| Installed from Windows, and nothing works | busybox `ash` reads a carriage return as part of the value before it, so `DASH_DIR` names a directory that does not exist and `INTERACT` is not equal to `true`. *Meteo: diagnostica* names the files; *Meteo: avvia il pannello* repairs them; `make lineendings` then reinstalling fixes it at the source |
| The page buttons do nothing | Press **power** first: the keypad on a Kindle 4 cannot wake the device. Then **KUAL > k4-weather > *Meteo: prova i tasti pagina***, which runs the real listening window and distinguishes the four causes: nothing read at all, codes this device sends that `KEY_NEXT`/`KEY_PREV` do not list, one location in the cache, or `INTERACT` not equal to `true`. `logs/dash.log` carries the same lines |
| A location is skipped by the buttons | Its image never downloaded, so it is not in the cycle: check `cache/` on the device and the Pages site for `dashboard-<id>.png`. CI publishes nothing for a location whose data did not arrive, and says so in the run log |
| One location shows an old time, the others are current | Open-Meteo did not answer for that one. The device kept the cached copy on purpose; the next run usually fixes it |
| The panel sleeps and only power wakes it | An RTC alarm left armed after a wake-up by hand. `local/suspend.sh` clears it before arming its own — check `logs/dash.log` for `RTC still reads` |
| Ghosting on the screen | `FULL_DISPLAY_REFRESH_RATE` in `kindle/local/env.sh`: lower it to do full refreshes more often |
| Battery draining too fast | Restrict `REFRESH_SCHEDULE` to daytime hours, for example `"15,45 7-23 * * *"` |

## Maintenance

- **Adding or changing a location**: edit `locations` in `config.yaml` and push.
  The workflow restarts on the push and the images update within minutes; the
  Kindle picks up the new list at its next wake-up, with no reinstall — the
  device reads the list rather than holding a copy of it. Up to eight, each
  costing two API calls and one screenshot per run.
- **Removing one**: delete it from the list. Its image stops being published,
  and the device drops the cached copy and takes it out of the button cycle on
  its next refresh.
- **Tweaking the design**: `make preview`, then open `out/dashboard.html` in a
  browser. After touching the icons, `make icons`.
- **PAT expiry**: the only deadline in the project, see step 5.

### Updating an installation

The two halves live on two machines and neither updates the other. The Kindle
downloads **the image**, never the code, so a push alone never reaches it.

| What changed | What to do |
|---|---|
| Anything under `src/`, or `config.yaml` | `git push`. The workflow re-renders and republishes within minutes; the Kindle picks the new images up at its next wake-up. **Adding a location is only this** — nothing on the device needs touching |
| Anything under `kindle/` | `./kindle/install.sh`, then restart the loop |

Restarting matters: `kindle-dash` reads `local/env.sh` once, at start-up, so a
loop already running keeps handing the old variables to `draw.sh`.

```sh
ssh root@192.168.15.244 /mnt/us/dashboard/stop.sh
./kindle/install.sh
ssh root@192.168.15.244 /mnt/us/dashboard/start.sh
```

A change that moves either blank the device writes into — the indoor
temperature, the battery level — touches both halves at once. Update them in
either order: until the second one lands, at most one refresh cycle draws the
value beside its blank instead of inside it.
