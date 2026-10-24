"""Web UI (:8097, no login: keep it on localhost or a trusted LAN). Paste a watch product URL, watch the rounds, install."""
from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import adb, config, db, ideas, pipeline

app = FastAPI(title=config.APP_NAME)
T = Jinja2Templates(directory=str(Path(__file__).parent / 'templates'))
_stop = threading.Event()


@app.on_event('startup')
def _start():
    db.init()
    threading.Thread(target=pipeline.worker_loop, args=(_stop,), daemon=True).start()
    ideas.seed()
    if config.IDEAS_DAILY:
        threading.Thread(target=ideas.scheduler_loop, args=(_stop,), daemon=True).start()


def _fmt_age(ts):
    s = int(time.time() - (ts or 0))
    return f'{s // 60} min ago' if s < 3600 else (f'{s // 3600} h ago' if s < 86400 else time.strftime('%d %b', time.localtime(ts)))


T.env.filters['age'] = _fmt_age
T.env.filters['fromjson'] = lambda s: json.loads(s or '{}')
T.env.globals['app_name'] = config.APP_NAME
T.env.globals['claude_auth'] = config.claude_auth
T.env.globals['api_key_ignored'] = config.api_key_ignored


def _thumb(j):
    d = pipeline.job_dir(j['id'])
    for rel in sorted([p.relative_to(d).as_posix() for p in d.glob('out/r*/*_onwatch.png')], key=lambda s: int(s.split('/')[1][1:]))[-1:] + ['reference/strip.png']:
        if (d / rel).exists():
            return rel
    return ''


@app.get('/', response_class=HTMLResponse)
def index(request: Request):
    jobs = db.jobs()
    for j in jobs:
        j['thumb'] = _thumb(j)
    return T.TemplateResponse(request, 'index.html', {'jobs': jobs, 'watch': db.setting('watch_ip')})


@app.post('/jobs')
def create(url: str = Form(...), notes: str = Form(''), rounds: int = Form(5)):
    if not url.startswith(('http://', 'https://')):
        raise HTTPException(400, 'Paste a full http(s) URL')
    jid = db.create_job(url.strip(), notes.strip(), max(1, min(rounds, 10)))
    return RedirectResponse(f'/job/{jid}', 303)


@app.get('/job/{jid}', response_class=HTMLResponse)
def job_page(request: Request, jid: int, msg: str = ''):
    j = db.job(jid) or {}
    if not j:
        raise HTTPException(404)
    evs = db.events(jid)
    for e in evs:
        if e['kind'] == 'critique':
            e['data'] = json.loads(e['text'])
    d = pipeline.job_dir(jid)
    variants = []
    vf = d / 'reference' / 'variants.json'
    if vf.exists():
        variants = json.loads(vf.read_text()).get('variants', [])
    latest = f"out/r{j['round']}" if j['round'] else ''
    sources, brief = [], ''
    if j['status'] == 'review' or not j['round']:
        src = d / 'source' / 'images'
        sources = sorted(p.name for p in src.glob('*')) if src.exists() else []
    if j['status'] == 'review':
        bf = d / 'reference' / 'brief.md'
        brief = bf.read_text(encoding='utf-8')[:6000] if bf.exists() else ''
    return T.TemplateResponse(request, 'job.html', {
        'j': j, 'events': evs, 'variants': variants, 'latest': latest, 'msg': msg, 'sources': sources, 'brief': brief,
        'has_apk': bool(j['apk']) and (d / j['apk']).exists(), 'watch': db.setting('watch_ip'),
        'scores': json.loads(j['scores'] or '{}')})


@app.get('/job/{jid}/file/{rel:path}')
def job_file(jid: int, rel: str):
    base = pipeline.job_dir(jid).resolve()
    p = (base / rel).resolve()
    if not str(p).startswith(str(base)) or not p.is_file():
        raise HTTPException(404)
    headers = {'Cache-Control': 'no-cache'}
    if p.suffix == '.apk':
        return FileResponse(p, filename=p.name, media_type='application/vnd.android.package-archive')
    return FileResponse(p, headers=headers)


@app.post('/job/{jid}/continue')
def cont(jid: int, feedback: str = Form(''), rounds: int = Form(2)):
    j = db.job(jid)
    if not j or j['status'] in ('running', 'queued'):
        return RedirectResponse(f'/job/{jid}', 303)
    db.update(jid, status='queued', feedback=feedback.strip(), max_rounds=j['round'] + max(0, min(rounds, 6)), message='')
    db.event(jid, 'user', f'Continue: {rounds} more round(s).' + (f' Feedback: {feedback.strip()}' if feedback.strip() else ''))
    return RedirectResponse(f'/job/{jid}', 303)


@app.post('/job/{jid}/approve')
def approve(jid: int):
    j = db.job(jid)
    if j and j['status'] == 'review':
        db.update(jid, approved=1, status='queued', message='')
        db.event(jid, 'user', 'Reference photos approved.')
    return RedirectResponse(f'/job/{jid}', 303)


@app.post('/job/{jid}/rescout')
def rescout(jid: int, image: str = Form(''), note: str = Form('')):
    j = db.job(jid)
    if not j or j['status'] in ('running', 'queued'):
        return RedirectResponse(f'/job/{jid}', 303)
    parts = [f'Use source/images/{image} as the main reference photo.' if image else '', note.strip()]
    hint = ' '.join(x for x in parts if x)
    shutil.rmtree(pipeline.job_dir(jid) / 'reference', ignore_errors=True)
    db.update(jid, scout_hint=hint, approved=0, status='queued', message='')
    db.event(jid, 'user', 'Re-pick reference: ' + (hint or 'try again'))
    return RedirectResponse(f'/job/{jid}', 303)


@app.post('/job/{jid}/stop')
def stop(jid: int):
    j = db.job(jid)
    if j and j['status'] in ('running', 'queued'):
        db.update(jid, status='stopped')
        db.event(jid, 'user', 'Stop requested (takes effect after the current agent finishes).')
    return RedirectResponse(f'/job/{jid}', 303)


@app.post('/job/{jid}/delete')
def delete(jid: int):
    j = db.job(jid)
    if j and j['status'] not in ('running',):
        with db.conn() as c:
            c.execute('delete from jobs where id=?', (jid,))
            c.execute('delete from events where job_id=?', (jid,))
        shutil.rmtree(pipeline.job_dir(jid), ignore_errors=True)
    return RedirectResponse('/', 303)


@app.post('/job/{jid}/install')
def install(jid: int):
    j = db.job(jid)
    if not j or not j['apk']:
        return RedirectResponse(f'/job/{jid}?msg=No+APK+yet', 303)
    d = pipeline.job_dir(jid)
    (d / 'watch').mkdir(exist_ok=True)
    rel = f'watch/installed_{int(time.time())}.png'
    ok, out = adb.install(d / j['apk'], pipeline.package_id(j), d / rel)
    db.event(jid, 'install', ('✅ ' if ok else '❌ ') + out[-400:], rel if ok and (d / rel).exists() else '')
    return RedirectResponse(f'/job/{jid}', 303)


@app.post('/job/{jid}/screenshot')
def shot(jid: int):
    d = pipeline.job_dir(jid) / 'watch'
    d.mkdir(exist_ok=True)
    rel = f'watch/shot_{int(time.time())}.png'
    ok, out = adb.screenshot(pipeline.job_dir(jid) / rel)
    db.event(jid, 'install', 'Screenshot from your watch' if ok else f'Screenshot failed: {out}', rel if ok else '')
    return RedirectResponse(f'/job/{jid}', 303)


@app.get('/ideas', response_class=HTMLResponse)
def ideas_page(request: Request, msg: str = ''):
    allx = db.ideas()
    fresh = [i for i in allx if i['status'] == 'new' and i['kind'] in ('new', 'screen')]
    shortlist = [i for i in allx if i['status'] == 'new' and i['kind'] not in ('new', 'screen')]
    done = [i for i in allx if i['status'] == 'approved'][:12]
    skipped = [i for i in allx if i['status'] == 'dismissed']
    last = db.setting('ideas_last_scan')
    return T.TemplateResponse(request, 'ideas.html', {
        'fresh': fresh, 'shortlist': shortlist, 'done': done, 'skipped': skipped, 'msg': msg,
        'scanning': ideas.scanning(), 'scan_at': ideas.SCAN_AT if config.IDEAS_DAILY else None,
        'last_scan': float(last) if last else 0, 'last_result': db.setting('ideas_last_result')})


@app.post('/ideas/scan')
def ideas_scan():
    if ideas.scanning():
        return RedirectResponse('/ideas?msg=' + quote('A scan is already running.'), 303)
    ideas.scan_async('manual')
    return RedirectResponse('/ideas?msg=' + quote('Scanning for new watches. This takes a few minutes.'), 303)


@app.post('/ideas/{iid}/build')
def ideas_build(iid: int, rounds: int = Form(5)):
    i = db.idea(iid)
    if not i or i['status'] != 'new':
        return RedirectResponse('/ideas', 303)
    notes = i['brief'] or ''
    jid = db.create_job(i['url'], notes.strip(), max(1, min(rounds, 10)))
    db.event(jid, 'user', f"From idea: {i['title']}" + (f" ({i['why']})" if i['why'] else ''))
    db.update_idea(iid, status='approved', job_id=jid)
    return RedirectResponse(f'/job/{jid}', 303)


@app.post('/ideas/{iid}/skip')
def ideas_skip(iid: int):
    if db.idea(iid):
        db.update_idea(iid, status='dismissed')
    return RedirectResponse('/ideas', 303)


@app.post('/ideas/{iid}/restore')
def ideas_restore(iid: int):
    i = db.idea(iid)
    if i and i['status'] == 'dismissed':
        db.update_idea(iid, status='new')
    return RedirectResponse('/ideas', 303)


@app.get('/watch', response_class=HTMLResponse)
def watch(request: Request, msg: str = ''):
    return T.TemplateResponse(request, 'watch.html', {'status': adb.status(), 'ip': db.setting('watch_ip'),
                                                  'hostport': db.setting('watch_hostport'), 'log': adb.log_tail(), 'msg': msg})


@app.post('/watch/pair')
def watch_pair(hostport: str = Form(...), code: str = Form(...)):
    ok, out = adb.pair(hostport.strip(), code.strip())
    if ok:
        serial, m = adb.connect()
        out += '\n' + m
    return RedirectResponse('/watch?msg=' + quote(("Paired. " if ok else "Pairing failed: ") + out[-300:]), 303)


@app.post('/watch/connect')
def watch_connect():
    serial, m = adb.connect()
    return RedirectResponse('/watch?msg=' + quote(m), 303)
