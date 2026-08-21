# k4-weather

Weather dashboard for a **jailbroken non-touch Kindle 4**: every 30 minutes
GitHub Actions renders a 600×800 grayscale PNG from the
[Open-Meteo](https://open-meteo.com) API, the Kindle downloads it and draws it
with `eips`. No server to keep alive.

![preview](docs/preview.png)

> The on-screen copy is in Italian on purpose — the panel hangs on an Italian
> wall. Code, comments and documentation are in English.

## How it works

```
GitHub Actions (every 30 min)                      Kindle 4 (every 30 min)
──────────────────────────────                     ──────────────────────
Open-Meteo  ─►  data model                         wakes from RTC
                    │                                    │
                    ▼                              waits for wifi
             HTML + CSS + SVG                            │
                    │                                    ▼
                    ▼                              xh get dashboard.png
          headless Chromium (screenshot)                 │
                    │                                    ▼
                    ▼                              eips -g dashboard.png
        8-bit gray, 16 levels, 600×800                   │
                    │                                    ▼
                    ▼                              fbink -S 3 … " 21"
        branch `output` ─► GitHub Pages ───────────────► │
                                                         ▼
                                                   suspend to RAM
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

## Development

```sh
make setup      # virtualenv + dependencies + Chromium
make preview    # render out/dashboard.png from the fixture, no network
make generate   # the same, with live data
make icons      # contact sheet of every icon at its real sizes
make test
```

`make preview` also writes `out/dashboard.html`: a self-contained file (fonts
in base64, SVG icons inline) that opens straight in a browser. That is the fast
way to iterate on the design — edit the CSS, reload, no rendering step.

The fixtures in `tests/fixtures/` are real Open-Meteo responses, so previews
and tests are reproducible and never touch the network.

### Layout

| Path | Role |
|---|---|
| `src/k4weather/fetch.py` | Open-Meteo client (forecast + air quality), with retries |
| `src/k4weather/model.py` | data normalisation and chart geometry |
| `src/k4weather/wmo.py` | WMO weather codes → Italian description + icon |
| `src/k4weather/astro.py` | moon phase, compass rose |
| `src/k4weather/render.py` | Jinja template → HTML → Chromium screenshot |
| `src/k4weather/postprocess.py` | conversion and validation for `eips` |
| `src/k4weather/templates/` | HTML, CSS, SVG icons, Inter fonts |
| `kindle/local/` | what runs on the device: download, sensor, drawing |
| `kindle/extensions/` | KUAL menu, to start the panel from the Kindle itself |
| `kindle/install.sh` | installs the runtime on the Kindle, configured |

The API payloads are treated as untrusted: every series is read through a
bounds-checked helper, so a missing or truncated array degrades to a dash on
screen instead of costing a whole refresh cycle.

Two couplings worth knowing about, both between the CSS and a number computed
elsewhere:

- the width of the min–max track in `style.css` (`.day` grid) must match
  `DAY_BAR_WIDTH` in `model.py`, because the bar inside the track is positioned
  in absolute pixels computed there;
- the blank left for the indoor temperature must match the character grid of
  whatever draws it — 24×48 px per character for `fbink` at scale 3, 12×20 for
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

The Kindle reads `dev-whiterice.github.io/k4-weather/dashboard.png` from Pages
and not from `raw.githubusercontent.com`, the source the kindle-dash example
uses: raw's anti-scraping limit follows the IP address and answers 429 once it
trips, taking the panel down with it. The workflow can publish to a different
repository too, through the `PUBLISH_REPO` variable, in case the code ever goes
private again.

## Roadmap

- [x] Phase 1 — fixed location in `config.yaml`
- [x] Indoor temperature from the Kindle's own sensor, overlaid client side
      with `fbink` — see [`kindle/README.md`](kindle/README.md)
- [ ] Phase 2 — dynamic location (several locations, search by name through
      Open-Meteo geocoding, selection from a secret)
- [ ] Kindle battery level on screen, through the same overlay
- [ ] Fallback image with an explicit banner when the API does not answer

## Licence

MIT. Weather data is from [Open-Meteo](https://open-meteo.com) (CC BY 4.0);
the [Inter](https://rsms.me/inter/) font is distributed under the SIL Open Font
License 1.1.
