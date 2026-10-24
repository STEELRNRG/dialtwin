// Fetch a watch product page: text + the larger product images.
// usage (cwd = job dir): node /app/engine/fetch_page.mjs <url>
//   source/page.txt, source/page.png (screenshot), source/images/NN.<ext>, source/images.json
import path from 'path';
import fs from 'fs';
import crypto from 'crypto';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require('playwright'); } catch {
  // outside Docker: point PLAYWRIGHT_DIR at any folder whose node_modules has playwright
  if (!process.env.PLAYWRIGHT_DIR) throw new Error('playwright not found: npm i playwright, or set PLAYWRIGHT_DIR');
  playwright = createRequire(path.join(process.env.PLAYWRIGHT_DIR, 'package.json'))('playwright');
}

const url = process.argv[2];
if (!url) { console.error('usage: fetch_page.mjs <url>'); process.exit(2); }
const out = path.join(process.cwd(), 'source');
const imgDir = path.join(out, 'images');
fs.mkdirSync(imgDir, { recursive: true });

const browser = await playwright.chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 1400, height: 1000 },
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36',
  locale: 'en-AU',
});
const page = await ctx.newPage();
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
await page.waitForTimeout(2500);
// scroll to trigger lazy loading
for (let y = 0; y < 12; y++) { await page.mouse.wheel(0, 1200); await page.waitForTimeout(350); }
await page.waitForTimeout(1500);

const found = await page.evaluate(() => {
  const urls = new Map();
  const add = (u, w = 0, h = 0, alt = '') => {
    if (!u || u.startsWith('data:')) return;
    try { u = new URL(u, location.href).href; } catch { return; }
    const prev = urls.get(u);
    if (!prev || w * h > prev.w * prev.h) urls.set(u, { url: u, w, h, alt });
  };
  const best = (srcset) => {
    let top = null, topW = 0;
    for (const part of (srcset || '').split(',')) {
      const [u, d] = part.trim().split(/\s+/);
      const w = parseInt(d) || 1;
      if (u && w >= topW) { top = u; topW = w; }
    }
    return top;
  };
  for (const img of document.images) {
    const s = best(img.srcset) || img.currentSrc || img.src;
    add(s, img.naturalWidth, img.naturalHeight, img.alt || '');
  }
  for (const src of document.querySelectorAll('picture source')) add(best(src.srcset));
  for (const m of document.querySelectorAll('meta[property="og:image"],meta[name="twitter:image"]')) add(m.content, 1200, 1200, 'og');
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const walk = (o) => { if (!o) return; if (Array.isArray(o)) return o.forEach(walk);
        if (typeof o === 'object') { const im = o.image; if (typeof im === 'string') add(im, 1200, 1200, 'ld'); else if (Array.isArray(im)) im.forEach((x) => add(typeof x === 'string' ? x : x.url, 1200, 1200, 'ld')); Object.values(o).forEach(walk); } };
      walk(JSON.parse(s.textContent));
    } catch {}
  }
  return { title: document.title, text: document.body.innerText.slice(0, 25000), images: [...urls.values()] };
});

fs.writeFileSync(path.join(out, 'page.txt'), `${found.title}\n${url}\n\n${found.text}`);
// we scrolled to the footer to trigger lazy images; screenshot the product hero instead
await page.evaluate(() => window.scrollTo(0, 0));
await page.waitForTimeout(800);
await page.screenshot({ path: path.join(out, 'page.png'), fullPage: false });

// keep images that are big enough to be product shots; ask CDNs for a large rendition
const bumped = (u) => u.replace(/([?&])(w|width)=\d+/i, '$1$2=2400').replace(/_(\d{2,4})x(\d{2,4})?\./, '_2400x.')
  .replace(/([?&])crop=[^&]*(&crop_[a-z]+=[^&]*)*/i, '$1');
// the product's own gallery first (URLs usually contain the product slug), related models last
const slug = new URL(url).pathname.split('/').filter(Boolean).pop() || '';
const words = slug.toLowerCase().split(/[-_]+/).filter((w) => w.length > 2);
const score = (u) => words.filter((w) => u.toLowerCase().includes(w)).length;
found.images.sort((a, b) => score(b.url) - score(a.url));
const candidates = found.images.filter((i) => !/\.svg(\?|$)/i.test(i.url) && (i.w === 0 || i.w >= 400 || i.h >= 400));
// download from inside the page first: bot-protected CDNs (Akamai on omegawatches.com) tarpit
// Playwright's APIRequestContext until it times out, but serve the browser's own fetch() instantly
const inPage = async (u) => {
  const res = await page.evaluate(async (u) => {
    const ac = new AbortController(); const t = setTimeout(() => ac.abort(), 20000);
    try {
      const r = await fetch(u, { signal: ac.signal });
      if (!r.ok) return null;
      const buf = new Uint8Array(await r.arrayBuffer());
      let s = ''; for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode(...buf.subarray(i, i + 0x8000));
      return { type: r.headers.get('content-type') || '', b64: btoa(s) };
    } catch { return null; } finally { clearTimeout(t); }
  }, u);
  return res && { type: res.type, body: Buffer.from(res.b64, 'base64') };
};
const viaRequest = async (u) => {
  const r = await ctx.request.get(u, { timeout: 10000 });
  return r.ok() ? { type: r.headers()['content-type'] || '', body: await r.body() } : null;
};
const deadline = Date.now() + 180000;     // big CDN renditions are slow; stop well before the pipeline's timeout
const seen = new Set();                   // galleries repeat the same shot under different URLs
const saved = [];
let n = 0;
for (const img of candidates.slice(0, 80)) {
  if (Date.now() > deadline) break;
  for (const u of [...new Set([bumped(img.url), img.url])]) {
    try {
      const r = (await inPage(u).catch(() => null)) || (await viaRequest(u));
      if (!r) continue;
      const type = r.type;
      if (!type.startsWith('image/') || type.includes('svg')) continue;
      const body = r.body;
      if (body.length < 25000) break;           // icons, logos, swatches
      const hash = crypto.createHash('sha1').update(body).digest('hex');
      if (seen.has(hash)) break;
      seen.add(hash);
      const ext = type.includes('png') ? 'png' : type.includes('webp') ? 'webp' : 'jpg';
      const file = `${String(++n).padStart(2, '0')}.${ext}`;
      fs.writeFileSync(path.join(imgDir, file), body);
      saved.push({ file, url: u, alt: img.alt, bytes: body.length });
      break;
    } catch {}
  }
  if (saved.length >= 40) break;
}
fs.writeFileSync(path.join(out, 'images.json'), JSON.stringify({ title: found.title, url, images: saved }, null, 1));
await browser.close();
console.log(JSON.stringify({ title: found.title, images: saved.length }));
