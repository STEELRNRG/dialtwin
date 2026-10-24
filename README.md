# Dialtwin

Paste a link to a watch, get a working watch face for your Wear OS smartwatch.

Dialtwin fetches the product page and lets a team of Claude agents do the rest. A scout picks
the best dial photo and measures it. A builder draws the dial as code. Two critics score each
round against the photo and against the rules for a good smartwatch face. The best round is
packaged as a real [Watch Face Format](https://developer.android.com/training/wearables/wff) app
and installed on your watch over Wi-Fi.

It runs on your own machine with **your own Claude access**. Nothing is hosted, and nobody else
pays for your tokens.

![FIELD 01, the built-in example face](docs/example.png)

## What you need
- A Linux machine with Docker (a home server or a Raspberry Pi 5 is fine). On macOS or Windows see
  [Docker Desktop](#docker-desktop-macos-windows).
- A round **Wear OS** watch: Galaxy Watch 4 or newer, Pixel Watch, or others with Wear OS 4+.
- Claude access: an [Anthropic API key](https://console.anthropic.com), or your own Claude
  subscription (run `claude setup-token` with [Claude Code](https://docs.claude.com/en/docs/claude-code)
  installed and copy the token).

### What it costs
A face takes 30–90 minutes and roughly **15–30 million tokens**, most of them cheap cache reads.
With an API key, check current pricing before your first run. `MAX_TOKENS_PER_JOB` (default 40M)
stops a job before it runs away, and every job page shows the tokens it used.

## Quick start
```bash
git clone https://github.com/STEELRNRG/dialtwin.git && cd dialtwin
cp .env.example .env          # add ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN
docker build -f Dockerfile.base -t dialtwin-base .    # once; downloads the Android tools (~15 min)
docker compose up -d --build
```
Open http://localhost:8097.

The UI has **no login**. It listens on localhost only unless you set `HOST=0.0.0.0` in `.env`.
Only do that on a network you trust, and never expose it to the internet.

## Pair your watch (once)
1. On the watch: Settings → About watch → Software → tap *Software version* 7 times to unlock
   Developer options.
2. Developer options → turn on **ADB debugging** and **Wireless debugging** → *Pair new device*.
3. In Dialtwin open **Watch**, type the IP:port and the pairing code the watch shows.

To install, open Wireless debugging on the watch and keep that screen on. Watches drop to
power-save Wi-Fi as soon as the screen sleeps, and then they can't be found. Then press
**Install on my watch** on a finished face. The face appears in your watch's face picker.

## How a face is made
1. **Fetch**: headless Chromium saves the page text, a screenshot and the product images.
2. **Scout** (Opus) picks a straight-on daylight photo per colourway (up to 3), crops and measures it,
   and writes a brief. **You check the photos** before anything is built.
3. **Rounds** (default up to 5):
   - The **builder** (Opus) writes `face.js`, a parametric SVG drawing of the dial
     ([contract](engine/CONTRACT.md)).
   - A **fidelity critic** (Opus) compares the render with the photo.
   - A **watch critic** (Sonnet) checks legibility, Always-On power use and packaging risks.
   - Stops at fidelity ≥ 8 and wearability ≥ 7.5, or when the scores stop improving.
4. **Package**: layers → Watch Face Format v2 XML, validated against the official schema →
   signed APK → Google's memory-footprint check.
5. **Install** over wireless adb.

**Improve it** on a job page takes plain feedback ("thicker hands", "the red is too orange")
and runs more rounds.

Every face gets watch settings for colourway, layout (full dial or painted bezel), Always-On
colour (green lume or red night vision), and live or parked registers (battery and steps) when
the dial has subdials.

## Brands, logos and what you may share
By default (`KEEP_BRANDING=0`) faces **leave out brand names, logos and model names**. The
dial's layout, hands and colours are recreated, but the maker's marks are not.

Watch designs and logos belong to their makers. Use this for faces of watches you own, on your
own wrist. Don't publish, sell or share faces of other people's designs. Watch companies do send
legal notices over smartwatch copies, and Google Play removes them. `KEEP_BRANDING=1` exists
for private use only, at your own risk.

## Settings
All settings live in `.env`; see [.env.example](.env.example).

| Setting | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` | | Claude access (one of them) |
| `MAX_TOKENS_PER_JOB` | 40000000 | Stop a job past this many tokens (0 = no limit) |
| `HOST` / `PORT` | 127.0.0.1 / 8097 | Where the UI listens |
| `STUDIO_URL` | http://localhost:8097 | Your address for the UI, used in notification links |
| `PACKAGE_PREFIX` | com.dialtwin.face | Android package prefix; keep it fixed so rebuilds update in place |
| `KEEP_BRANDING` | 0 | 1 = copy logos and brand text too (private use only) |
| `IDEAS_DAILY` | 0 | 1 = run the ideas scout every morning (~3M tokens a run) |
| `NOTIFY_URL` | | POST a notification here, e.g. `https://ntfy.sh/<your-topic>` |
| `HA_URL`, `HA_TOKEN`, `HA_NOTIFY_TARGETS` | | Home Assistant notifications instead of, or as well as, ntfy |
| `TZ` | UTC | Time zone for the daily ideas scan |

## Docker Desktop (macOS, Windows)
The compose file uses host networking so adb can find the watch over mDNS. On Docker Desktop
turn on host networking (Settings → Resources → Network, Docker Desktop 4.34+). Otherwise,
replace `network_mode: host` with `ports: ["127.0.0.1:8097:8097"]`, set `HOST=0.0.0.0`, and
type the watch's IP:port on the Watch page each time instead of relying on discovery.

## Other smartwatches
Only Wear OS is supported today. The engine draws every face as layers plus a list of hands, so
other platforms need an exporter, not a rewrite:

| Platform | Status |
|---|---|
| Wear OS (Samsung, Pixel, others) | ✅ Supported |
| Pebble (Core Devices) | Planned: open platform, good fit |
| Amazfit / Zepp OS | Planned |
| Garmin Connect IQ | Possible, more work (Monkey C) |
| Apple Watch | ❌ Apple doesn't allow custom watch faces |
| Fitbit | ❌ Third-party faces are being wound down |

Pull requests for an exporter are very welcome.

## Project layout
```
engine/      renderer and packager, no Claude needed: face.html, render.mjs, export.mjs,
             package.py, build_apk.sh, fetch_page.mjs, fonts/, xsd/ (WFF v2), CONTRACT.md,
             examples/fieldchrono/ (the worked example the builder learns from)
studio/      FastAPI app and job worker: app.py, pipeline.py, claude.py, adb.py, notify.py,
             ideas.py, config.py, agents/*.md (the agents' instructions), templates/
```
Runtime folders (git-ignored): `jobs/` (one folder per face, including every agent's log),
`data/` (database, APK signing key), `adb/` (watch pairing keys), `claude-home/`.

Try the engine without Claude: copy `engine/examples/fieldchrono/face.js` into an empty folder and
run `node /app/engine/render.mjs r1` there inside the container.

## Support the project
Dialtwin is free and MIT-licensed. If it made you a face you love, you can
[sponsor it on GitHub](https://github.com/sponsors/STEELRNRG).

## Credits
- Watch Face Format schema: © Samsung Electronics and Google, Apache 2.0.
- Memory-footprint checker: [google/watchface](https://github.com/google/watchface), Apache 2.0
  (downloaded during the Docker build).
- Fonts: Google Fonts, SIL Open Font License 1.1 / Apache 2.0. See [NOTICE](NOTICE).

Not affiliated with Google, Samsung or any watch brand. "Wear OS" is a trademark of Google LLC.
