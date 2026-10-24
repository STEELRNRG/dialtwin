# face.js contract (Dialtwin engine)

A job directory holds one `face.js`. The engine renders it with headless Chromium
(`engine/face.html`), exports layers to PNG, and packages a Watch Face Format v2 APK for
**round Wear OS watches: a 480×480 canvas (the watch scales it), sized for a ~38 mm AMOLED screen (≈12.6 px/mm)**.
The worked example is `engine/examples/fieldchrono/face.js`: read it before writing a new face.

## Shape of the file
```js
(function (global) {
  // ... geometry, palettes, SVG helpers ...
  const manifest = { ... };
  function build({ variant, layout, aod }) { ... return { scale, svg, plate, aod, hands, aodHands }; }
  global.WatchFace = { build, manifest };
})(typeof window !== 'undefined' ? window : globalThis);
```
- Plain ES2020, no imports, no DOM access, no network, **no raster images**: everything is SVG you
  generate as strings. `build()` must be pure (it also runs in Node).
- Work in **dial units** around the centre (0,0), clock degrees (0 = 12 o'clock, clockwise).
  `svg(inner)` wraps `inner` in `translate(240 240) scale(scale)` and returns a full 480×480 `<svg>`
  string including your `<defs>`.

## manifest
| key | meaning |
|---|---|
| `name` | Display name, e.g. `'PILOT GMT'` |
| `variants` | `[{id, label}]` colourways (1–3). ids: lowercase `[a-z0-9]` |
| `layouts` | `[{id, label}]`: first is the default on the watch. Use `dial` (dial fills the screen, no painted bezel) first; add `bezel` only if the real watch has a distinctive bezel |
| `photoLayout` | layout id that matches the product photo for comparison renders (usually `bezel` if present) |
| `aodTints` | `[{id, label}]`: always provide `red` (night vision) and `green` (lume) unless the watch's lume colour suggests otherwise; first = default |
| `hands` | paint order bottom→top: `{id, kind, pivot?: [x, y] (dial units), sweep?}` |
| `aodHands` | ids of hands shown in Always-On (no seconds!) |
| `photoPose` | `{time: 'HH:MM:SS', angles: {handId: deg}}`: hand pose matching the product photo |
| `previewTime` | time shown in the watch's picker, default `'10:09:30'` |
| `dateWindow` | optional `{x, y, w, h, size, color, colors: {variant: '#AARRGGBB'}, font: 'Oxanium.ttf', format: 'DAY_Z', offset: 0}` (dial units, box centre x,y), or a **list** of them. `offset` -1/0/+1 = yesterday/today/tomorrow, for rolling date wheels (never bake date numbers into the plate). Add `aodColors: {red: '#AARRGGBB', green: '#AARRGGBB'}` to show that digit (dimmed) in Always-On too, which you should do for the main date. The plate draws the window frame; the engine draws the live digits |

### Hand kinds
`hour`, `minute` (system hands) · `second` (running seconds, `sweep: '2'|'5'|'10'|'15'|'SYNC_TO_DEVICE'|'tick'`)
· `chrono` (central chrono hand, parked at 12 or sweeping via a watch setting) · `gmt24` (24 h hand)
· `battery`, `steps` (register hands showing live data 0–99 % → 0–356°, or at rest) · `weekday`
· `static` (hub caps, fixed ornaments that must sit above the hands).
Map real complications to the nearest kind: e.g. a chronograph's 30-minute register → `steps`,
12-hour register → `battery`, small seconds → `second`, second time zone → `gmt24`.
A register you cannot map sensibly: bake it into the plate at rest.

## build() return value
- `plate`: full static dial for `variant` + `layout`, **no moving hands**.
- `hands[id]`: SVG for each hand, drawn **pointing at 12 around its own pivot (0,0)**. The engine
  places it at `pivot` and rotates it.
- `aod`, `aodHands[id]`: Always-On plate and hands in the tint `aod`.
- `scale`: dial-units → pixels factor for this layout (the example uses `240 / flangeOuter`
  for `dial` and `1` for `bezel`).

## Rules learned the hard way (critics will check these)
1. **Shadows must look the same at every angle**: hands rotate as images, so use a centred halo
   (`feDropShadow dx=0 dy=0`), never an offset drop shadow.
2. **Minimum sizes at 480 px**: readable text ≥ 12 px, decorative text ≥ 8 px, lines ≥ 1.5 px,
   dots ≥ 2 px radius. Hand outlines ≥ 2 px on light dials.
3. **Hands must stand out from the dial**: on light dials give the lume fill a dark frame of 2.5–3 px.
   Hour and minute must be told apart instantly (length ratio ≈ 0.7, different widths).
4. **Always-On**: black background, ≤ 15 % of the round screen lit (aim 8–12 %), no seconds,
   static elements dimmer than hands, keep the face recognisable (indices + key text dimmed). Both
   tints must use the same geometry.
5. **Default layout fills the screen**: most watches have a physical bezel; the `dial` layout scales
   the dial so the outermost printed ring reaches ~r 236–240, with numerals ≥ 10 px inside the edge.
6. Everything that isn't a hand goes in the plate (text, logos, indices, date frame, register rims).
7. Fonts available in `engine/fonts/fonts.css` (family names): ShareTechMono, Oxanium, B612Mono,
   BarlowCondensed, BebasNeue, Cinzel, EBGaramond, Michroma, Orbitron, Rajdhani, RobotoCondensed,
   Saira, SpaceMono. A job may add OFL fonts in `fonts/` with its own `fonts/fonts.css`.
   Fake bold with `stroke` of the fill colour (0.3–0.55 px) when no bold weight exists.
8. Logos/emblems: trace the shape from a zoomed reference crop with real geometry (arcs, bars), and
   check the silhouette at the real rendered size; outline tricks collapse below ~4 px band width.
9. Keep `face.js` under ~60 KB and deterministic (seeded noise only).

## Engine commands (cwd = job dir)
```
node /app/engine/render.mjs r3     # out/r3/<v>.png, <v>_vs_ref.png, <v>_onwatch.png, <v>_aod_<tint>.png, sheet.png
node /app/engine/export.mjs        # build/assets/*
python3 /app/engine/package.py --package com.x.y --label NAME   # build/wff + XSD validation
```
Render preview in a browser: `engine/face.html?face=file:///app/jobs/<id>/face.js&v=<variant>&layout=dial&t=10:09:30`
