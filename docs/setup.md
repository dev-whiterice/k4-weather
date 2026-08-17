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
  output  dashboard.png  ──►  raw.githubusercontent.com  ──►  Kindle
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

## 3. Check the first image

```sh
gh run watch --repo dev-whiterice/k4-weather

curl -sI https://raw.githubusercontent.com/dev-whiterice/k4-weather/output/dashboard.png | head -1
# HTTP/2 200
```

From here on the workflow restarts by itself at :00 and :30.

## 4. Keep the scheduler alive (recommended)

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

### Preview page (optional)

The workflow also publishes an `index.html`. Under *Settings → Pages*, choosing
branch `output` and folder `/`, you get
`https://dev-whiterice.github.io/k4-weather/` to check the dashboard from your
phone. The Kindle keeps using `raw.githubusercontent.com`: shorter cache, one
redirect chain fewer.

---

## 5. Kindle

One-off prerequisites: a jailbroken Kindle 4 NT, KUAL, USBNetwork for SSH, and
Wi-Fi configured. Reference: [the MobileRead
wiki](https://wiki.mobileread.com/wiki/Kindle4NTHacking).

The scripted route is [`kindle/install.sh`](../kindle/install.sh), which
downloads the runtime, applies our configuration, checks that the image is
reachable, copies everything over and starts nothing:

```sh
./kindle/install.sh                      # uses root@192.168.15.244
./kindle/install.sh root@192.168.1.50    # Kindle reachable over Wi-Fi
```

By hand, it comes down to:

```sh
# Runtime: kindle-dash handles wifi, TLS, suspend and RTC wake-up.
# The archive is a .tgz that expands flat, so the directory has to exist first.
mkdir -p kindle-dash
curl -sSL "$(curl -sSL https://api.github.com/repos/pascalw/kindle-dash/releases/latest \
  | grep browser_download_url | cut -d'"' -f4 | head -n1)" | tar xz -C kindle-dash

# Our configuration: the URL is already set, nothing to edit
cp kindle/local/env.sh             kindle-dash/local/env.sh
cp kindle/local/fetch-dashboard.sh kindle-dash/local/fetch-dashboard.sh
cp kindle/local/indoor-temp.sh     kindle-dash/local/indoor-temp.sh
cp kindle/local/draw.sh            kindle-dash/local/draw.sh

# The drawing goes through our wrapper, which adds the indoor temperature
sed -i.bak 's|/usr/sbin/eips|"$DIR/local/draw.sh"|g' kindle-dash/dash.sh

rsync -vr kindle-dash/ root@192.168.15.244:/mnt/us/dashboard
ssh root@192.168.15.244 'chmod +x /mnt/us/dashboard/*.sh /mnt/us/dashboard/local/*.sh \
  /mnt/us/dashboard/xh /mnt/us/dashboard/next-wakeup'
```

Before really launching it, try it in debug mode: it stays in the foreground,
does not suspend the device and prints everything (see
[`kindle/README.md`](../kindle/README.md#try-it-in-debug-mode)).

The Kindle suspends after 10-15 seconds and wakes at :15 and :45, offset by 15
minutes from generation to absorb the delay of the GitHub Actions cron.

### Check on the device

```sh
ssh kindle
/mnt/us/dashboard/local/fetch-dashboard.sh /tmp/test.png && echo OK
/mnt/us/dashboard/local/indoor-temp.sh --probe          # the sensor
eips -f -g /tmp/test.png
```

---

## If something goes wrong

| Symptom | Cause and remedy |
|---|---|
| `curl` on the raw URL returns 404 | The `output` branch does not exist yet: the workflow has never completed successfully |
| Image **skewed or squashed** on the Kindle | The PNG is not grayscale. `make inspect` catches this before publication |
| `fetch-dashboard.sh` exits with an error | No Wi-Fi, or the wrong URL. The screen keeps the last good image instead of going blank |
| The screen shows a time frozen days ago | Scheduler disabled after 60 days of inactivity: see step 4 |
| *dati non aggiornati* in the footer | The image is fresh but the Open-Meteo observation is more than 90 minutes old |
| The indoor temperature stays a dash | The sensor is unreadable or the reading is out of range: `local/indoor-temp.sh --probe` on the device says which |
| The indoor temperature lands off its blank | `eips` does not use the 12×20 px cell the layout assumes: adjust `INDOOR_TEMP_COL/ROW` and `INDOOR_SLOT_COL/ROW` together |
| The indoor temperature reads too high | Normal before calibration: it is the battery, not the room. See [`kindle/README.md`](../kindle/README.md#calibrating-the-offset) |
| Ghosting on the screen | `FULL_DISPLAY_REFRESH_RATE` in `kindle/local/env.sh`: lower it to do full refreshes more often |
| Battery draining too fast | Restrict `REFRESH_SCHEDULE` to daytime hours, for example `"15,45 7-23 * * *"` |

## Maintenance

- **Changing location**: edit `location` in `config.yaml` and push. The
  workflow restarts on the push and the image updates within minutes.
- **Tweaking the design**: `make preview`, then open `out/dashboard.html` in a
  browser. After touching the icons, `make icons`.
- **PAT expiry**: the only deadline in the project, see step 4.
