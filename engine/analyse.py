"""Checks every round needs, done once in plain Python so the agents don't spend turns on them.

usage (cwd = job dir): python3 /app/engine/analyse.py r1      (render.mjs runs it automatically)

For each variant <v> in out/<round>/ it writes:
  <v>_zoom_top.png, _zoom_mid.png, _zoom_bot.png
      3 overlapping 200 px regions each (left, centre, right), reference | render, both at 2x.
      Together they cover the whole dial, so most fine-detail comparisons need no custom crop.
  <v>_wrist.png   onwatch, alt and every AOD image at 200 px: roughly the size on the wrist.
  metrics.md      AOD lit % per image (the <= 15 % rule) and the main colours of reference vs render.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROUND = sys.argv[1] if len(sys.argv) > 1 else 'r1'
OUT = Path('out') / ROUND
REF = Path('reference')
TILE, ZOOM, PAD, LABEL = 200, 2, 10, 22
CENTRES = (90, 240, 390)          # overlapping 200 px windows across a 480 px dial
ROWS = {'top': 90, 'mid': 240, 'bot': 390}
COLS = {'left': 90, 'centre': 240, 'right': 390}


def crop(im, cx, cy):
    h = TILE // 2
    return im.crop((cx - h, cy - h, cx + h, cy + h)).resize((TILE * ZOOM, TILE * ZOOM), Image.LANCZOS)


def zoom_sheets(v, ref, ren):
    w = 2 * TILE * ZOOM + 3 * PAD
    h = 3 * (TILE * ZOOM + LABEL + PAD) + PAD
    for row, cy in ROWS.items():
        sheet = Image.new('RGB', (w, h), '#202020')
        d = ImageDraw.Draw(sheet)
        y = PAD
        for col, cx in COLS.items():
            d.text((PAD, y + 4), f'{row}-{col}  (centre {cx},{cy})   REFERENCE | RENDER  x{ZOOM}', fill='#e0e0e0')
            y += LABEL
            sheet.paste(crop(ref, cx, cy), (PAD, y))
            sheet.paste(crop(ren, cx, cy), (2 * PAD + TILE * ZOOM, y))
            y += TILE * ZOOM + PAD
        sheet.save(OUT / f'{v}_zoom_{row}.png')


def wrist_strip(v, files):
    S = 200
    sheet = Image.new('RGB', (len(files) * (S + PAD) + PAD, S + LABEL + 2 * PAD), '#202020')
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(files):
        x = PAD + i * (S + PAD)
        d.text((x, PAD), f.stem.replace(f'{v}_', ''), fill='#e0e0e0')
        sheet.paste(Image.open(f).convert('RGB').resize((S, S), Image.LANCZOS), (x, PAD + LABEL))
    sheet.save(OUT / f'{v}_wrist.png')


def disc_mask(size):
    m = Image.new('L', size, 0)
    ImageDraw.Draw(m).ellipse((0, 0, size[0] - 1, size[1] - 1), fill=255)
    return m


def lit_percent(f):
    im = Image.open(f).convert('L')
    mask = disc_mask(im.size)
    lit = total = 0
    for p, m in zip(im.getdata(), mask.getdata()):
        if m:
            total += 1
            lit += p > 10
    return 100.0 * lit / max(total, 1)


def palette(im, n=6):
    """Main colours inside the dial disc, as (hex, share %)."""
    small = im.resize((160, 160))
    px = [p for p, m in zip(small.getdata(), disc_mask(small.size).getdata()) if m]
    strip = Image.new('RGB', (len(px), 1))
    strip.putdata(px)
    q = strip.quantize(colors=n, method=Image.MEDIANCUT)
    pal = q.getpalette()
    out = []
    for c, idx in sorted(q.getcolors(), reverse=True):
        r, g, b = pal[idx * 3:idx * 3 + 3]
        out.append((f'#{r:02x}{g:02x}{b:02x}', 100.0 * c / len(px)))
    return out


def main():
    variants = sorted(p.name[:-len('_vs_ref.png')] for p in OUT.glob('*_vs_ref.png'))
    lines = [f'# Round {ROUND} metrics (computed by analyse.py)', '']
    for v in variants:
        ren = Image.open(OUT / f'{v}.png').convert('RGB')
        ref_f = REF / f'ref_{v}.png'
        if ref_f.exists():
            ref = Image.open(ref_f).convert('RGB').resize(ren.size)
            zoom_sheets(v, ref, ren)
        aods = sorted(OUT.glob(f'{v}_aod_*.png'))
        wrist = [f for f in [OUT / f'{v}_onwatch.png', OUT / f'{v}_alt.png'] if f.exists()] + aods
        if wrist:
            wrist_strip(v, wrist)
        lines.append(f'## {v}')
        for f in aods:
            pct = lit_percent(f)
            flag = 'OK' if pct <= 15 else 'OVER 15 %'
            lines.append(f'- AOD lit {f.stem}: {pct:.1f} % ({flag}; ideal 8-12 %)')
        if ref_f.exists():
            fmt = lambda p: ', '.join(f'{h} {s:.0f}%' for h, s in p)
            lines.append(f'- main colours, reference: {fmt(palette(ref))}')
            lines.append(f'- main colours, render:    {fmt(palette(ren))}')
        lines.append('')
    (OUT / 'metrics.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'analyse: {len(variants)} variant(s) -> {OUT}/metrics.md, *_zoom_*.png, *_wrist.png')


if __name__ == '__main__':
    main()
