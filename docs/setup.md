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
  output  dashboard.png  ──►  GitHub Pages  ──►  Kindle
```

The `output` branch is rewritten on every run with a force push of a single
commit: it accumulates no history and stays a constant size.

> The repository is public: **the image and the code are readable by anyone**,
> and the dashboard shows the name of the location. Commit metadata becomes
> public too, the author's email address included.

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

## 4. Check the first image

```sh
gh run watch --repo dev-whiterice/k4-weather

curl -sI https://dev-whiterice.github.io/k4-weather/dashboard.png | head -1
# HTTP/2 200
```

From here on the workflow restarts by itself at :00 and :30.

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
carries it over. It is what draws the indoor temperature at a size you can read
from a doorway; without it that one number comes out small
([details](../kindle/README.md#how-the-number-gets-on-screen)).

```sh
./kindle/install.sh                      # uses root@192.168.15.244
./kindle/install.sh root@192.168.1.50    # Kindle reachable over Wi-Fi
```

It downloads the runtime, applies our configuration, checks that the image is
reachable, copies everything to the device and deliberately starts nothing. The
same by hand, plus what to do when SSH times out with USBNetwork on:
[`kindle/README.md`](../kindle/README.md#installation).

Do not make `start.sh` your first move. Try the pieces one at a time — the
download, the sensor, one draw, then the whole loop with `DEBUG=true`, which
stays in the foreground and does not suspend the device:
[`kindle/README.md`](../kindle/README.md#try-it-in-debug-mode).

Once started for real, the Kindle suspends after 10-15 seconds and wakes at :15
and :45, offset by 15 minutes from generation to absorb the delay of the GitHub
Actions cron.

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
| Ghosting on the screen | `FULL_DISPLAY_REFRESH_RATE` in `kindle/local/env.sh`: lower it to do full refreshes more often |
| Battery draining too fast | Restrict `REFRESH_SCHEDULE` to daytime hours, for example `"15,45 7-23 * * *"` |

## Maintenance

- **Changing location**: edit `location` in `config.yaml` and push. The
  workflow restarts on the push and the image updates within minutes.
- **Tweaking the design**: `make preview`, then open `out/dashboard.html` in a
  browser. After touching the icons, `make icons`.
- **PAT expiry**: the only deadline in the project, see step 5.

### Updating an installation

The two halves live on two machines and neither updates the other. The Kindle
downloads **the image**, never the code, so a push alone never reaches it.

| What changed | What to do |
|---|---|
| Anything under `src/`, or `config.yaml` | `git push`. The workflow re-renders and republishes within minutes; the Kindle picks the new image up at its next wake-up |
| Anything under `kindle/` | `./kindle/install.sh`, then restart the loop |

Restarting matters: `kindle-dash` reads `local/env.sh` once, at start-up, so a
loop already running keeps handing the old variables to `draw.sh`.

```sh
ssh root@192.168.15.244 /mnt/us/dashboard/stop.sh
./kindle/install.sh
ssh root@192.168.15.244 /mnt/us/dashboard/start.sh
```

A change that moves the blank left for the indoor temperature touches both
halves at once. Update them in either order: until the second one lands, at most
one refresh cycle draws the value beside its blank instead of inside it.
