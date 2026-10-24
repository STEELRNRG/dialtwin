# Dialtwin

Paste a watch product-page URL; Claude agents (scout, builder, two critics) build a Wear OS Watch Face
Format v2 face and package an APK. Self-hosted in Docker, bring-your-own Claude key. Public docs:
README.md. Machine-specific deploy notes, if any, live in CLAUDE.local.md (git-ignored).

## Layout
- `engine/`: renderer and packager with no Claude: `fetch_page.mjs`, `render.mjs`, `export.mjs`,
  `package.py`, `build_apk.sh`, `CONTRACT.md` (the face.js contract), `xsd/` (WFF v2),
  `examples/fieldchrono/` (original worked example the builder copies techniques from)
- `studio/`: FastAPI app and worker: `app.py`, `pipeline.py`, `claude.py` (`claude -p`), `config.py`
  (all env settings), `adb.py`, `notify.py` (ntfy/HA), `ideas.py`, `agents/*.md` (prompts), `templates/`
- `Dockerfile.base` (dialtwin-base: JDK + Android build-tools + Node/Playwright + Claude CLI +
  memory-footprint.jar), `Dockerfile`, `docker-compose.yml`

## Run
`docker build -f Dockerfile.base -t dialtwin-base .` once, then `docker compose up -d --build`.
Engine only, outside Docker: in a folder with a face.js, `PLAYWRIGHT_DIR=<dir with node_modules/playwright> node engine/render.mjs r1`.

## Gotchas
- Never commit `.env`, `jobs/`, `data/`, `adb/`, `claude-home/`. Example faces and screenshots must be
  original designs: no brand dials anywhere in the repo.
- Default is `KEEP_BRANDING=0`: pipeline.py adds NO_BRANDING to the scout, builder and fidelity prompts.
- Pass rule: fidelity >= 8 and watch >= 7.5; packaging picks the best-scoring round. Jobs pause at
  `review` after the scout for the user to check the reference photos.
- Critics run a STRUCTURE CHECK on `_plate.png`/`_alt.png`: painted-in hands cap the score at 5. Keep real
  hand lengths (platform.md HARD RULE).
- Bad reference photos are the usual cause of poor faces. Akamai-protected sites need the in-page `fetch()`
  in fetch_page.mjs.
- adb: watches drop Wi-Fi when the screen sleeps; keep Wireless debugging open. Stale mDNS ports and names
  with spaces are handled in `adb.py`.
- `MAX_TOKENS_PER_JOB` stops a job (status `stopped`); a face is ~15-30M tokens.
