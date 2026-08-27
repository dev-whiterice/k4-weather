# k4-weather

Weather dashboard for a **jailbroken non-touch Kindle 4**: every 30 minutes
GitHub Actions renders one 600×800 grayscale PNG per configured location from
the [Open-Meteo](https://open-meteo.com) API, the Kindle downloads them all and
draws one with `eips`. The page buttons switch between them. No server to keep
alive.

![preview](docs/preview.png)

> The on-screen copy is in Italian on purpose — the panel hangs on an Italian
> wall. Code, comments and documentation are in English.

## How it works

```
GitHub Actions (every 30 min)                      Kindle 4 (every 30 min)
──────────────────────────────                     ──────────────────────
for each location:                                 wakes from RTC
Open-Meteo  ─►  data model                               │
                    │                              waits for wifi
                    ▼                                    │
             HTML + CSS + SVG                            ▼
                    │                              xh get locations.txt
                    ▼                              xh get dashboard-<id>.png × N
          headless Chromium (screenshot)                 │
                    │                                    ▼
                    ▼                              eips -g the current one
        8-bit gray, 16 levels, 600×800                   │
                    │                                    ▼
                    ▼                              fbink -S 4 … " 21"
     dashboard-<id>.png + locations.json                 │
                    │                                    ▼
        branch `output` ─► GitHub Pages ───────────────► suspend to RAM
                                                         │
                                             power ──────┤ wakes into a
                                             ◄ ► ────────┘ 25s window that
                                                           switches location
```

The Kindle is kept deliberately dumb: it downloads an image and draws it. All
the logic lives in CI, where it is easy to test and to look at in a browser.
The one exception is the indoor temperature, which no server can know: the
device reads its own sensor and writes the number into a blank the layout
leaves for it.

## What it shows

- **Now**: on the left of the rule everything outdoors — temperature,
  condition, and as labelled figures today's high, today's low and the
  apparent temperature — and on the right of it the temperature of the room,
  which the Kindle reads from its own sensor and writes on the image itself
- **Metric strip**: humidity, wind with direction, max UV, rain probability,
  air quality (European EAQI index)
- **Next 24 hours**: temperature curve with the coldest and warmest hours
  annotated, rain-probability bars
- **7 days**: icon, min–max range on a **shared scale** — the shape of the week
  reads from the position of the bars, without reading the numbers — plus rain
  probability and maximum wind speed
- **Footer**: sunrise, sunset, moon phase with illumination percentage, and the
  time the image was generated

## Several locations

`config.yaml` holds a list of up to eight places; the first is the one on
screen after an install and the order is the order the buttons walk through.
Each gets its own image, and the Kindle downloads all of them on every refresh
so switching costs a redraw rather than a Wi-Fi round trip.

```yaml
locations:
  - id: caoria            # lowercase ASCII: it becomes a file name and a URL
    name: "Caoria"        # what appears on the panel; anything goes here
    latitude: 46.19647
    longitude: 11.67804
    timezone: "auto"
```

The `id` is written by hand rather than derived from `name` on purpose. It is
an identity, not a position: reordering or renaming a location changes nothing
anywhere else, and no slugifier has to guess what `Sant'Anna di Valdieri`
should be called. What CI publishes beside the images is `locations.json` and
`locations.txt` — the same list twice, for the preview page and for a device
whose shell has no JSON parser.

On the Kindle: **press power**, then the page buttons.
[`kindle/README.md`](kindle/README.md#switching-locations) explains why it takes
power first — the keypad on a Kindle 4 cannot wake the device, and that is a
property of the driver, not a setting.

## Development

```sh
make setup      # virtualenv + dependencies + Chromium
make preview    # render the primary location from the fixture, no network
make generate   # every location, with live data
make icons      # contact sheet of every icon at its real sizes
make test
```

`make preview` also writes `out/dashboard-<id>.html`: a self-contained file
(fonts in base64, SVG icons inline) that opens straight in a browser. That is the fast
way to iterate on the design — edit the CSS, reload, no rendering step.

The fixtures in `tests/fixtures/` are real Open-Meteo responses, so previews
and tests are reproducible and never touch the network.

### On Windows

Everything above works from **Git Bash** (the shell that comes with Git for
Windows); `make` comes from `winget install GnuWin32.Make` or Scoop. The
Makefile finds the virtualenv under `.venv/Scripts` on its own, and the test
suite skips the one case that needs POSIX process groups.

To install on the Kindle from PowerShell, [`kindle/install.ps1`](kindle/install.ps1)
finds Git Bash and hands over to `install.sh`; from Git Bash, run
`./kindle/install.sh` directly as everywhere else.

If the USB network link cannot be made to work — on Windows the Kindle presents
a Linux RNDIS gadget that the system binds a serial driver to, and the clean fix
needs an unsigned INF — there is a transport that needs no network at all:

```sh
./kindle/install.sh --drive E:      # the Kindle mounted as a USB disk
```

The KUAL menu then starts, tests and diagnoses the panel from the device.

**One thing matters more than the rest.** The scripts under `kindle/` run on
busybox `ash`, which does *not* treat a carriage return as whitespace — it is
an ordinary character and it ends up inside the value of whatever assignment it
terminates. A CRLF checkout therefore ships a `DASH_DIR` naming a directory
that does not exist and an `INTERACT` that is not equal to `true`, and on a
device with no terminal both faults look like nothing happening at all.

The [`.gitattributes`](.gitattributes) at the root of the repository forces LF
on every platform and overrides `core.autocrlf`, so a fresh clone is already
right. A working tree cloned *before* it was added is not:

```sh
make lineendings      # git add --renormalize .
```

`tests/test_kindle.py` fails if a device script ever carries a CR again,
`install.sh` strips them on the way to the Kindle, and the KUAL start entry
repairs an installation that already has them.

### Layout

| Path | Role |
|---|---|
| `src/k4weather/fetch.py` | Open-Meteo client (forecast + air quality), with retries |
| `src/k4weather/model.py` | data normalisation and chart geometry |
| `src/k4weather/wmo.py` | WMO weather codes → Italian description + icon |
| `src/k4weather/astro.py` | moon phase, compass rose |
| `src/k4weather/render.py` | Jinja template → HTML → Chromium screenshot |
| `src/k4weather/postprocess.py` | conversion and validation for `eips` |
| `src/k4weather/manifest.py` | the list published beside the images |
| `src/k4weather/templates/` | HTML, CSS, SVG icons, Inter fonts |
| `kindle/local/` | what runs on the device: download, switching, sensor, drawing |
| `kindle/extensions/` | KUAL menu, to start the panel from the Kindle itself |
| `kindle/tools/keytest.sh` | button diagnostics, run on the device |
| `kindle/install.sh` | installs the runtime on the Kindle, configured |
| `kindle/install.ps1` | the same, launched from PowerShell |

The API payloads are treated as untrusted: every series is read through a
bounds-checked helper, so a missing or truncated array degrades to a dash on
screen instead of costing a whole refresh cycle.

Two couplings worth knowing about, both between the CSS and a number computed
elsewhere:

- the width of the min–max track in `style.css` (`.day` grid) must match
  `DAY_BAR_WIDTH` in `model.py`, because the bar inside the track is positioned
  in absolute pixels computed there;
- the blank left for the indoor temperature must match the character grid of
  whatever draws it — 32×64 px per character for `fbink` at scale 4, 12×20 for
  the `eips` fallback. `INDOOR_SLOT_*` in `model.py` and `INDOOR_TEMP_*` in
  `kindle/local/env.sh` say it once per machine and `tests/test_kindle.py`
  compares them. It is the only element positioned in absolute page pixels, and
  label, degree sign and dividing rule all hang off that one rectangle, so the
  browser measurement in `tests/test_render.py` covers the whole block.

## Kindle 4 constraints that explain the choices

| Constraint | Consequence in the project |
|---|---|
| 600×800 panel, 16 gray levels | Palette limited to multiples of 17, so flat areas lose nothing in quantisation |
| `eips` skews RGB PNGs | `postprocess.py` forces 8-bit grayscale with no alpha, and `make inspect` verifies it |
| Thin strokes and light grays vanish at 167 ppi | Solid-shape icons, hairlines never below 1 px, text in full black |
| Stock curl/wget do not speak modern TLS | The download uses `xh`, the static client bundled with kindle-dash |
| `eips` has one font size, 12×20 px | The indoor temperature is drawn by `fbink`, which scales its font; without it the value still appears, small |
| The GitHub Actions cron runs 5-20 minutes late | The Kindle wakes 15 minutes offset and the image always carries its generation time |

### Icons

A monochrome set drawn for this screen, in `templates/icons/`. Shared geometry
on a 64×64 viewBox:

```
canonical cloud   circle(25,28,13) circle(41,31.5,10) rect(11,33,42,11,r5.5)   y 15..44
high cloud        the same, translated by -7 (icons with precipitation)        y  8..37
mid cloud         circle(24,36,11) circle(37,39,8.5) rect(12,40,35,10,r5)      y 25..50
small cloud       circle(38,43,8)  circle(48,45.5,6) rect(30,46,26,8,r4)       y 35..54
```

Overlaps (sun behind a cloud) are separated by a white outline rather than a
`<mask>`: the background is always white paper, and this way there are no
duplicate `id`s when the same icon appears several times on the page.

After every change, `make icons` draws the whole set at 112, 26 and 15 px — the
three sizes it actually appears at. At 26 px many ideas that work large become
illegible, and it is worth finding out immediately.

## Putting it into service

Step by step in [`docs/setup.md`](docs/setup.md); the shape of it:

1. **Public repository** — the Kindle cannot authenticate, so the source has to
   be readable without a token, and 48 runs a day would cost some 3,000 Actions
   minutes a month against the 2,000 the free plan includes for private ones.
2. **Push to `main`** — the workflow starts by itself and creates the `output`
   branch, which GitHub Pages serves.
3. **`PUBLISH_TOKEN` secret** (recommended) — a fine-grained PAT with
   `contents: write`, or GitHub disables the scheduler after 60 days of
   inactivity: commits made with the automatic token do not count as activity.
4. **Kindle** — [`kindle/README.md`](kindle/README.md).

The Kindle reads `dev-whiterice.github.io/k4-weather/locations.txt` from Pages,
and then the image file names that list gives it — not from
`raw.githubusercontent.com`, the source the kindle-dash example uses: raw's anti-scraping limit follows the IP address and answers 429 once it
trips, taking the panel down with it. The workflow can publish to a different
repository too, through the `PUBLISH_REPO` variable, in case the code ever goes
private again.

## Roadmap

- [x] Phase 1 — fixed location in `config.yaml`
- [x] Indoor temperature from the Kindle's own sensor, overlaid client side
      with `fbink` — see [`kindle/README.md`](kindle/README.md)
- [x] Phase 2 — several locations, chosen on the device with the page buttons
      — see [`kindle/README.md`](kindle/README.md#switching-locations)
- [ ] Search by name through Open-Meteo geocoding, instead of coordinates
      written into `config.yaml` by hand
- [ ] Kindle battery level on screen, through the same overlay
- [ ] Fallback image with an explicit banner when the API does not answer

## Licence

MIT. Weather data is from [Open-Meteo](https://open-meteo.com) (CC BY 4.0);
the [Inter](https://rsms.me/inter/) font is distributed under the SIL Open Font
License 1.1.
