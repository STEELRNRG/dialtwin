"""Generic Watch Face Format (v2) packager.

cwd = job dir, after `node export.mjs`. Reads build/assets/meta.json (manifest + pivots),
crops hands, writes build/wff/ and validates watchface.xml against the WFF v2 XSD (XSD 1.1).

usage: python3 package.py --package com.dialtwin.face.<slug> --label "Name" [--version 3]

Hand kinds (manifest.hands[].kind):
  hour, minute          system HourHand / MinuteHand
  second                running seconds (own AnalogClock box), sweep: '2'|'5'|'10'|'15'|'SYNC_TO_DEVICE'|'tick'
  chrono                central seconds: config "Chrono hand" parked at 12 / sweeping
  gmt24                 24-hour hand, local time
  battery, steps        register hands: config "Registers" live data / at rest (0..99% -> 0..356 deg)
  weekday               day-of-week hand (Sunday at 0 deg, 7 steps)
  static                never moves (hubs, caps, parked hands)
Optional manifest.dateWindow = {x, y, w, h, size, color, font: 'File.ttf', format: 'DAY_Z'} in dial units.
"""
import argparse
import json
import re
import shutil
from pathlib import Path

from PIL import Image

ENGINE = Path(__file__).resolve().parent
JOB = Path.cwd()
ASSETS = JOB / 'build' / 'assets'
WFF = JOB / 'build' / 'wff'
XSD = ENGINE / 'xsd' / 'watchface.xsd'

BATTERY = 'clamp([BATTERY_PERCENT], 0, 99) * 3.6'
STEPS = 'clamp([STEP_PERCENT], 0, 99) * 3.6'
GMT = '([HOUR_0_23] + [MINUTE] / 60.0) * 15'
WEEKDAY = '([DAY_OF_WEEK] - 1) * 51.4286'
AMBIENT_ONLY = '<Variant mode="AMBIENT" target="alpha" value="255"/>'
HIDE_IN_AMBIENT = '<Variant mode="AMBIENT" target="alpha" value="0"/>'
FULL = {'x': 0, 'y': 0, 'w': 480, 'h': 480, 'px': 0.5, 'py': 0.5}


def res_name(s):
    return re.sub(r'[^a-z0-9_]', '_', s.lower())


def crop_hand(src, dst, pivot):
    """Trim transparent margins keeping the box symmetric about the pivot column."""
    im = Image.open(src).convert('RGBA')
    bbox = im.getchannel('A').point(lambda a: 255 if a > 2 else 0).getbbox()
    px, py = pivot
    if not bbox:                       # empty layer: 2x2 transparent stub at the pivot
        bbox = (int(px) - 1, int(py) - 1, int(px) + 1, int(py) + 1)
    x0, y0, x1, y1 = bbox
    half = max(px - x0, x1 - px) + 1
    x0, x1 = int(px - half), int(round(px + half))
    y0, y1 = int(min(y0, py - 1)), int(round(max(y1, py + 1)))
    im.crop((x0, y0, x1, y1)).save(dst, optimize=True)
    w, h = x1 - x0, y1 - y0
    return {'x': x0, 'y': y0, 'w': w, 'h': h, 'px': round((px - x0) / w, 5), 'py': round((py - y0) / h, 5)}


class X:
    """Tiny indented XML writer."""
    def __init__(self):
        self.lines, self.d = [], 0

    def add(self, s):
        self.lines.append('  ' * self.d + s)

    def open(self, s):
        self.add(s)
        self.d += 1

    def close(self, s):
        self.d -= 1
        self.add(s)

    def group(self, name):
        self.open(f'<Group name="{name}" x="0" y="0" width="480" height="480">')

    def image(self, m, res, angle=None, ambient_only=False):
        a = ' alpha="0"' if ambient_only else ''
        self.open(f'<PartImage x="{m["x"]}" y="{m["y"]}" width="{m["w"]}" height="{m["h"]}" '
                  f'pivotX="{m["px"]}" pivotY="{m["py"]}"{a}>')
        if angle:
            self.add(f'<Transform target="angle" value="{angle}"/>')
        if ambient_only:
            self.add(AMBIENT_ONLY)
        self.add(f'<Image resource="{res}"/>')
        self.close('</PartImage>')

    def clock_hand(self, tag, m, res, ambient_only=False, own_box=False, motion=None):
        box = m if own_box else FULL
        hm = dict(m, x=0, y=0) if own_box else m
        a = ' alpha="0"' if ambient_only else ''
        self.open(f'<AnalogClock x="{box["x"]}" y="{box["y"]}" width="{box["w"]}" height="{box["h"]}"{a}>')
        if ambient_only:
            self.add(AMBIENT_ONLY)
        attrs = (f'resource="{res}" x="{hm["x"]}" y="{hm["y"]}" width="{hm["w"]}" height="{hm["h"]}" '
                 f'pivotX="{hm["px"]}" pivotY="{hm["py"]}"')
        if motion:
            self.open(f'<{tag} {attrs}>')
            self.add(motion)
            self.close(f'</{tag}>')
        else:
            self.add(f'<{tag} {attrs}/>')
        self.close('</AnalogClock>')

    def option_switch(self, config_id, options):
        """options: list of (option_id, callback) -> ListConfiguration with one Group per option."""
        self.open(f'<ListConfiguration id="{config_id}">')
        for oid, fn in options:
            self.open(f'<ListOption id="{oid}">')
            self.group(f'{config_id}_{oid}_{len(self.lines)}')
            fn()
            self.close('</Group>')
            self.close('</ListOption>')
        self.close('</ListConfiguration>')


def motion_for(sweep):
    if sweep == 'tick':
        return '<Tick duration="0.15" strength="0.6"/>'
    return f'<Sweep frequency="{sweep or "10"}"/>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--package', required=True)
    ap.add_argument('--label', required=True)
    ap.add_argument('--version', type=int, default=1)
    args = ap.parse_args()

    meta = json.loads((ASSETS / 'meta.json').read_text())
    M, pivots = meta['manifest'], meta['pivots']
    shutil.rmtree(WFF, ignore_errors=True)
    draw = WFF / 'res' / 'drawable-nodpi'
    for d in [draw, WFF / 'res' / 'raw', WFF / 'res' / 'xml', WFF / 'res' / 'values']:
        d.mkdir(parents=True, exist_ok=True)

    V = [v['id'] for v in M['variants']]
    L = [l['id'] for l in M['layouts']]
    T = [t['id'] for t in M['aodTints']]
    kinds = {h['kind'] for h in M['hands']}
    boxes = {}

    def asset(v, lay, layer):
        return ASSETS / f'{v}__{lay}__{layer}.png'

    def res(v, lay, layer):
        return res_name(f'{v}_{lay}_{layer}')

    # plates flattened onto black (opaque), hands cropped around their pivots
    for v in V:
        for lay in L:
            for layer in ['plate'] + [f'plate_aod_{t}' for t in T]:
                im = Image.open(asset(v, lay, layer)).convert('RGBA')
                flat = Image.new('RGBA', im.size, (0, 0, 0, 255))
                flat.alpha_composite(im)
                flat.convert('RGB').save(draw / f'{res(v, lay, layer)}.png', optimize=True)
            for h in M['hands']:
                pv = pivots[lay][h['id']]
                boxes[res(v, lay, h['id'])] = crop_hand(asset(v, lay, h['id']), draw / f'{res(v, lay, h["id"])}.png', pv)
                if h['id'] in M['aodHands']:
                    for t in T:
                        n = f'{h["id"]}_aod_{t}'
                        boxes[res(v, lay, n)] = crop_hand(asset(v, lay, n), draw / f'{res(v, lay, n)}.png', pv)

    # optional date window font
    # date windows: one dict or a list (e.g. a rolling date wheel: offsets +1 / 0 / -1)
    dws = M.get('dateWindow') or []
    if isinstance(dws, dict):
        dws = [dws]
    fonts = {}
    for dw in dws:
        font_file = (JOB / 'fonts' / dw['font']) if (JOB / 'fonts' / dw['font']).exists() else ENGINE / 'fonts' / dw['font']
        fam = res_name(Path(dw['font']).stem)
        fonts[dw['font']] = fam
        (WFF / 'res' / 'font').mkdir(parents=True, exist_ok=True)
        shutil.copy(font_file, WFF / 'res' / 'font' / f'{fam}.ttf')

    def date_expr(dw):
        off = int(dw.get('offset', 0))
        if off == 0:
            return f"[{dw.get('format', 'DAY_Z')}]"
        if off == 1:
            return '([DAY] % [DAYS_IN_MONTH]) + 1'
        if off == -1:   # uses this month's length on the 1st: close enough for a date wheel
            return '(([DAY] + [DAYS_IN_MONTH] - 2) % [DAYS_IN_MONTH]) + 1'
        raise SystemExit(f'dateWindow offset {off} not supported (use -1, 0, 1)')

    x = X()

    def active(v, lay):
        x.group(f'{v}_{lay}_active')
        x.add(HIDE_IN_AMBIENT)
        x.image(FULL, res(v, lay, 'plate'))
        for dw in dws:
            date_text(v, lay, dw, dw.get('colors', {}).get(v, dw.get('color', '#ffffffff')))
        for h in M['hands']:
            r = res(v, lay, h['id'])
            m = boxes[r]
            k = h['kind']
            if k in ('hour', 'minute'):
                x.clock_hand('HourHand' if k == 'hour' else 'MinuteHand', m, r)
            elif k == 'second':
                x.clock_hand('SecondHand', m, r, own_box=True, motion=motion_for(h.get('sweep')))
            elif k == 'chrono':
                x.option_switch('chrono', [
                    ('parked', lambda: x.image(m, r)),
                    ('sweep', lambda: x.clock_hand('SecondHand', m, r, motion='<Sweep frequency="SYNC_TO_DEVICE"/>')),
                ])
            elif k in ('battery', 'steps'):
                expr = BATTERY if k == 'battery' else STEPS
                x.option_switch('counters', [('live', lambda: x.image(m, r, expr)), ('rest', lambda: x.image(m, r))])
            elif k == 'gmt24':
                x.image(m, r, GMT)
            elif k == 'weekday':
                x.image(m, r, WEEKDAY)
            else:
                x.image(m, r)
        x.close('</Group>')

    def date_text(v, lay, dw, color, ambient_only=False):
        sc = meta['scales'][lay]
        bx = round(240 + (dw['x'] - dw['w'] / 2) * sc)
        by = round(240 + (dw['y'] - dw['h'] / 2) * sc)
        a = ' alpha="0"' if ambient_only else ''
        x.open(f'<PartText x="{bx}" y="{by}" width="{round(dw["w"] * sc)}" height="{round(dw["h"] * sc)}"{a}>')
        if ambient_only:
            x.add(AMBIENT_ONLY)
        x.open('<Text align="CENTER">')
        x.open(f'<Font family="{fonts[dw["font"]]}" size="{round(dw["size"] * sc, 1)}" color="{color}">')
        x.add(f'<Template>%s<Parameter expression="{date_expr(dw)}"/></Template>')
        x.close('</Font>')
        x.close('</Text>')
        x.close('</PartText>')

    def ambient(v, lay):
        def tint_group(t):
            def fn():
                x.image(FULL, res(v, lay, f'plate_aod_{t}'), ambient_only=True)
                for dw in dws:
                    col = (dw.get('aodColors') or {}).get(t)
                    if col:
                        date_text(v, lay, dw, col, ambient_only=True)
                for h in M['hands']:
                    if h['id'] not in M['aodHands']:
                        continue
                    r = res(v, lay, f'{h["id"]}_aod_{t}')
                    m = boxes[r]
                    k = h['kind']
                    if k in ('hour', 'minute'):
                        x.clock_hand('HourHand' if k == 'hour' else 'MinuteHand', m, r, ambient_only=True)
                    elif k == 'gmt24':
                        x.image(m, r, GMT, ambient_only=True)
                    elif k == 'weekday':
                        x.image(m, r, WEEKDAY, ambient_only=True)
                    elif k in ('static',):
                        x.image(m, r, ambient_only=True)
            return fn
        if len(T) > 1:
            x.option_switch('aodcolor', [(t, tint_group(t)) for t in T])
        else:
            tint_group(T[0])()

    def face(v, lay):
        x.group(f'{v}_{lay}')
        active(v, lay)
        ambient(v, lay)
        x.close('</Group>')

    def per_layout(v):
        if len(L) > 1:
            x.option_switch('layout', [(lay, lambda lay=lay: face(v, lay)) for lay in L])
        else:
            face(v, L[0])

    x.d = 2
    if len(V) > 1:
        x.option_switch('style', [(v, lambda v=v: per_layout(v)) for v in V])
    else:
        per_layout(V[0])
    scene = '\n'.join(x.lines)

    strings = {'watch_face_name': args.label}
    cfg = []

    def list_cfg(cid, label, items, default):
        strings[f'{cid}_label'] = label
        opts = []
        for oid, olabel, icon in items:
            strings[f'{cid}_{oid}'] = olabel
            ic = f' icon="{icon}"' if icon else ''
            opts.append(f'      <ListOption id="{oid}" displayName="{cid}_{oid}" screenReaderText="{cid}_{oid}"{ic}/>')
        cfg.append(f'    <ListConfiguration id="{cid}" displayName="{cid}_label" screenReaderText="{cid}_label" defaultValue="{default}">\n'
                   + '\n'.join(opts) + '\n    </ListConfiguration>')

    for v in M['variants']:
        Image.open(asset(v['id'], L[0], 'preview')).convert('RGB').resize((300, 300), Image.LANCZOS) \
            .save(draw / f'icon_{res_name(v["id"])}.png', optimize=True)
    shutil.copy(draw / f'icon_{res_name(V[0])}.png', draw / 'preview.png')
    if len(V) > 1:
        list_cfg('style', 'Dial', [(v['id'], v['label'], f'icon_{res_name(v["id"])}') for v in M['variants']], V[0])
    if len(L) > 1:
        list_cfg('layout', 'Layout', [(l['id'], l['label'], None) for l in M['layouts']], L[0])
    if len(T) > 1:
        list_cfg('aodcolor', 'Always-on colour', [(t['id'], t['label'], None) for t in M['aodTints']], T[0])
    if kinds & {'battery', 'steps'}:
        what = ' / '.join(k for k in ('battery', 'steps') if k in kinds)
        list_cfg('counters', 'Registers', [('live', f'Live: {what}', None), ('rest', 'At rest', None)], 'live')
    if 'chrono' in kinds:
        list_cfg('chrono', 'Chrono hand', [('parked', 'Parked at 12', None), ('sweep', 'Sweep seconds', None)], 'parked')
    if not cfg:  # UserConfigurations needs at least one entry
        list_cfg('style', 'Dial', [(V[0], M['variants'][0]['label'], None)], V[0])

    xml = f'''<?xml version="1.0" encoding="utf-8"?>
<WatchFace width="480" height="480">
  <Metadata key="CLOCK_TYPE" value="ANALOG"/>
  <Metadata key="PREVIEW_TIME" value="{M.get('previewTime', '10:09:30')}"/>
  <UserConfigurations>
{chr(10).join(cfg)}
  </UserConfigurations>
  <Scene backgroundColor="#ff000000">
{scene}
  </Scene>
</WatchFace>
'''
    (WFF / 'res' / 'raw' / 'watchface.xml').write_text(xml, encoding='utf-8')
    esc = lambda s: s.replace('&', '&amp;').replace('<', '&lt;').replace("'", "\\'")
    (WFF / 'res' / 'values' / 'strings.xml').write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
        + ''.join(f'  <string name="{k}">{esc(v)}</string>\n' for k, v in strings.items()) + '</resources>\n', encoding='utf-8')
    (WFF / 'res' / 'xml' / 'watch_face_info.xml').write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<WatchFaceInfo>\n  <Preview value="@drawable/preview"/>\n'
        '  <Editable value="true"/>\n  <MultipleInstancesAllowed value="true"/>\n</WatchFaceInfo>\n', encoding='utf-8')
    (WFF / 'AndroidManifest.xml').write_text(f'''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="{args.package}" android:versionCode="{args.version}" android:versionName="1.{args.version}">
  <uses-sdk android:minSdkVersion="34" android:targetSdkVersion="34"/>
  <uses-feature android:name="android.hardware.type.watch"/>
  <application android:label="@string/watch_face_name" android:hasCode="false">
    <meta-data android:name="com.google.android.wearable.standalone" android:value="true"/>
    <property android:name="com.google.wear.watchface.format.version" android:value="2"/>
    <property android:name="com.google.wear.watchface.format.publisher" android:value="watchface-studio-1.0"/>
  </application>
</manifest>
''', encoding='utf-8')

    import xmlschema
    schema = xmlschema.XMLSchema11(str(XSD))
    errors = list(schema.iter_errors(str(WFF / 'res' / 'raw' / 'watchface.xml')))
    report = {'valid': not errors, 'errors': [f'{e.reason} @ {e.path}' for e in errors[:20]]}
    have = {p.stem for p in draw.glob('*.png')}
    missing = sorted({m for m in re.findall(r'resource="([^"]+)"', xml) if m not in have})
    if missing:
        report['valid'] = False
        report['errors'].append(f'missing drawables: {missing}')
    report['drawables'] = len(have)
    report['bytes'] = sum(p.stat().st_size for p in draw.glob('*.png'))
    (JOB / 'build' / 'package_report.json').write_text(json.dumps(report, indent=1))
    print(json.dumps(report))
    if not report['valid']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
