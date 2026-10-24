// Round renders for the builder, the critics and the web page.
// usage (cwd = job dir): node /app/engine/render.mjs r1
//   out/r1/<v>.png          photo pose, layout that best matches the product photo (manifest.photoLayout or first)
//   out/r1/<v>_vs_ref.png   reference | render
//   out/r1/<v>_onwatch.png  default layout at preview time (what the watch shows)
//   out/r1/<v>_aod_<tint>.png
//   out/r1/sheet.png        all variants: reference row over render row (shown on the job page)
//   then analyse.py adds <v>_zoom_{top,mid,bot}.png, <v>_wrist.png and metrics.md (see that file)
import path from 'path';
import fs from 'fs';
import { pathToFileURL, fileURLToPath } from 'url';
import { execFileSync } from 'child_process';
import { JOB, loadManifest, browser } from './lib.mjs';

const round = process.argv[2] || 'r1';
const M = await loadManifest();
const out = path.join(JOB, 'out', round);
fs.mkdirSync(out, { recursive: true });
const { b, shot, html } = await browser();
const pose = M.photoPose || { time: '10:09:30' };
const poseAngles = Object.fromEntries(Object.entries(pose.angles || {}).map(([k, v]) => ['a_' + k, String(v)]));
const photoLayout = M.photoLayout || M.layouts[0].id;
const url = (f) => pathToFileURL(f).href;

for (const v of M.variants) {
  const base = { v: v.id, round: '1', frame: '1' };
  await shot({ ...base, layout: photoLayout, t: pose.time, ...poseAngles }, path.join(out, `${v.id}.png`));
  await shot({ ...base, layout: M.layouts[0].id, t: M.previewTime || '10:09:30' }, path.join(out, `${v.id}_onwatch.png`));
  // structure checks: the plate alone (anything hand-like here is a bug) and a different time
  // (everything that is a hand in the photo must have moved)
  await shot({ ...base, layout: photoLayout, layer: 'plate', t: pose.time }, path.join(out, `${v.id}_plate.png`));
  await shot({ ...base, layout: photoLayout, t: '04:38:47' }, path.join(out, `${v.id}_alt.png`));
  for (const tint of M.aodTints) {
    await shot({ ...base, layout: M.layouts[0].id, mode: 'aod', aod: tint.id, t: M.previewTime || '10:09:30' }, path.join(out, `${v.id}_aod_${tint.id}.png`));
  }
  const ref = path.join(JOB, 'reference', `ref_${v.id}.png`);
  if (fs.existsSync(ref)) {
    await html(`<body style="margin:0;background:#111;display:flex;gap:20px;padding:20px">
      <img src="${url(ref)}" width="480" height="480" style="border-radius:50%"><img src="${url(path.join(out, `${v.id}.png`))}" width="480" height="480"></body>`,
    path.join(out, `${v.id}_vs_ref.png`), 1020, 520);
  }
}

// summary sheet for the web page
const S = 300;
const cells = M.variants.map((v) => {
  const ref = path.join(JOB, 'reference', `ref_${v.id}.png`);
  return `<div style="display:flex;flex-direction:column;gap:8px;align-items:center">
    <div style="color:#ff8a3d;font:600 15px system-ui">${v.label}</div>
    ${fs.existsSync(ref) ? `<img src="${url(ref)}" width="${S}" height="${S}" style="border-radius:50%">` : `<div style="width:${S}px;height:${S}px"></div>`}
    <img src="${url(path.join(out, `${v.id}.png`))}" width="${S}" height="${S}">
    <img src="${url(path.join(out, `${v.id}_onwatch.png`))}" width="${S}" height="${S}">
  </div>`;
}).join('');
await html(`<body style="margin:0;background:#111;display:flex;gap:18px;padding:18px">
  <div style="display:flex;flex-direction:column;justify-content:space-around;padding-top:28px;color:#aaa;font:13px system-ui;width:70px">
    <div>Real watch</div><div>Build (photo pose)</div><div>On your watch</div></div>${cells}</body>`,
path.join(out, 'sheet.png'), 106 + M.variants.length * (S + 18), 3 * S + 80);

await b.close();
// zoom sheets, wrist view and AOD/colour metrics: free here, many agent turns otherwise
try {
  execFileSync('python3', [path.join(path.dirname(fileURLToPath(import.meta.url)), 'analyse.py'), round], { cwd: JOB, stdio: ['ignore', 'ignore', 'inherit'] });
} catch (e) { console.error(`analyse.py failed (renders are fine): ${e.message}`); }
console.log(JSON.stringify({ round, out, variants: M.variants.map((v) => v.id) }));
