// Shared helpers for the engine scripts. All scripts run with cwd = a job directory
// that contains face.js (and optionally fonts/fonts.css, reference/ref_<variant>.png).
import { createRequire } from 'module';
import path from 'path';
import fs from 'fs';
import { fileURLToPath, pathToFileURL } from 'url';

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require('playwright'); } catch {
  // outside Docker: point PLAYWRIGHT_DIR at any folder whose node_modules has playwright
  if (!process.env.PLAYWRIGHT_DIR) throw new Error('playwright not found: npm i playwright, or set PLAYWRIGHT_DIR');
  playwright = createRequire(path.join(process.env.PLAYWRIGHT_DIR, 'package.json'))('playwright');
}

export const ENGINE = path.dirname(fileURLToPath(import.meta.url));
export const JOB = process.cwd();
export const FACE_URL = pathToFileURL(path.join(JOB, 'face.js')).href;

export async function loadManifest() {
  // face.js assigns globalThis.WatchFace when evaluated outside a browser
  const src = fs.readFileSync(path.join(JOB, 'face.js'), 'utf-8');
  new Function(src)();
  const M = globalThis.WatchFace?.manifest;
  if (!M) throw new Error('face.js did not define WatchFace.manifest');
  for (const k of ['variants', 'layouts', 'aodTints', 'hands', 'aodHands']) {
    if (!Array.isArray(M[k]) || !M[k].length) throw new Error(`manifest.${k} must be a non-empty array`);
  }
  return M;
}

export async function browser() {
  const b = await playwright.chromium.launch({ args: ['--disable-lcd-text', '--force-color-profile=srgb', '--allow-file-access-from-files'] });
  const page = await b.newPage({ viewport: { width: 480, height: 480 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  async function shot(params, file) {
    const qs = new URLSearchParams({ face: FACE_URL, ...params }).toString();
    await page.goto(pathToFileURL(path.join(ENGINE, 'face.html')).href + '?' + qs);
    await page.waitForFunction(() => document.body.dataset.ready === '1', null, { timeout: 30000 });
    const err = await page.evaluate(() => document.body.dataset.error);
    if (err) throw new Error(`face.js error (${JSON.stringify(params)}): ${err}`);
    await page.waitForTimeout(80);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    await page.locator('#w').screenshot({ path: file, omitBackground: true });
  }
  async function html(markup, file, w, h) {
    await page.setViewportSize({ width: w, height: h });
    await page.setContent(markup);
    await page.waitForTimeout(250);
    await page.screenshot({ path: file });
    await page.setViewportSize({ width: 480, height: 480 });
  }
  return { b, page, shot, html, errors };
}
