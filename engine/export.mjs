// Exports every WFF layer as a transparent 480x480 PNG into build/assets/:
//   <variant>__<layout>__plate.png, __plate_aod_<tint>.png, __<hand>.png, __<hand>_aod_<tint>.png, __preview.png
// (double underscores so ids may contain single underscores)
import path from 'path';
import fs from 'fs';
import { JOB, loadManifest, browser } from './lib.mjs';

const M = await loadManifest();
const outDir = path.join(JOB, 'build', 'assets');
fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });
const { b, shot } = await browser();
const f = (name) => path.join(outDir, name);

for (const v of M.variants) {
  for (const lay of M.layouts) {
    const base = { v: v.id, layout: lay.id, t: '00:00:00' };
    const p = `${v.id}__${lay.id}__`;
    await shot({ ...base, layer: 'plate' }, f(`${p}plate.png`));
    for (const h of M.hands) await shot({ ...base, layer: h.id }, f(`${p}${h.id}.png`));
    for (const tint of M.aodTints) {
      await shot({ ...base, layer: 'plate', mode: 'aod', aod: tint.id }, f(`${p}plate_aod_${tint.id}.png`));
      for (const id of M.aodHands) await shot({ ...base, layer: id, mode: 'aod', aod: tint.id }, f(`${p}${id}_aod_${tint.id}.png`));
    }
    await shot({ v: v.id, layout: lay.id, t: M.previewTime || '10:09:30', round: '1', frame: '1' }, f(`${p}preview.png`));
  }
}
await b.close();

// pivot of every hand on the 480 canvas, per layout (build() is pure string work, so it runs in node)
const pivots = {}, scales = {};
for (const lay of M.layouts) {
  const { scale } = globalThis.WatchFace.build({ variant: M.variants[0].id, layout: lay.id, aod: M.aodTints[0].id });
  scales[lay.id] = scale;
  pivots[lay.id] = Object.fromEntries(M.hands.map((h) => {
    const [x, y] = h.pivot || [0, 0];
    return [h.id, [240 + x * scale, 240 + y * scale]];
  }));
}
fs.writeFileSync(path.join(outDir, 'meta.json'), JSON.stringify({ manifest: M, pivots, scales }, null, 1));
console.log(JSON.stringify({ exported: fs.readdirSync(outDir).length }));
