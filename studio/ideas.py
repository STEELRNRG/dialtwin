"""Ideas: a shortlist of watches worth building, plus a daily scout that finds new releases and
watches seen on screen. Each idea carries the page URL the pipeline will fetch and the notes the
builder gets; approving an idea just creates a normal job.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from pathlib import Path

from . import claude, config, db, notify

SEED = Path(__file__).resolve().parent / 'ideas_seed.json'
WORK = Path('/app/data/ideas')
SCAN_AT = (6, 30)          # local time (container TZ) for the daily scan, when IDEAS_DAILY=1
_lock = threading.Lock()


def seed():
    try:
        items = json.loads(SEED.read_text(encoding='utf-8'))
    except Exception:
        return
    for it in items:
        db.add_idea(**it)


def og_image(url, timeout=12):
    """Best-effort og:image of a page, for the idea card. The pipeline fetches real images later."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            html = r.read(400_000).decode('utf-8', 'replace')
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html, re.I) \
            or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html, re.I)
        return m.group(1) if m else ''
    except Exception:
        return ''


def scanning():
    return db.setting('ideas_scanning') == '1'


def scan(trigger='daily'):
    """Run the ideas scout once. Returns (new_count, detail)."""
    if not _lock.acquire(blocking=False):
        return 0, 'a scan is already running'
    db.set_setting('ideas_scanning', '1')
    try:
        WORK.mkdir(parents=True, exist_ok=True)
        (WORK / 'logs').mkdir(exist_ok=True)
        out = WORK / 'ideas.json'
        if out.exists():
            out.unlink()
        known = [i['title'] for i in db.ideas()]
        (WORK / 'existing.txt').write_text('\n'.join(known), encoding='utf-8')
        today = time.strftime('%A %d %B %Y')
        prompt = (f"Today is {today}. Find new watch ideas as described in your instructions and write ideas.json "
                  f"in the current directory. existing.txt lists titles already known: skip those.")
        ts = time.strftime('%Y%m%d_%H%M')
        r = claude.run('ideascout', prompt, WORK, WORK / 'logs' / ts)
        if not out.exists():
            detail = f'scout wrote nothing: {r.detail or r.text[-300:]}'
            db.set_setting('ideas_last_result', detail)
            return 0, detail
        try:
            items = json.loads(out.read_text(encoding='utf-8'))
            if isinstance(items, dict):
                items = items.get('ideas', [])
        except Exception as e:
            detail = f'ideas.json unreadable: {e}'
            db.set_setting('ideas_last_result', detail)
            return 0, detail
        new = []
        for it in items:
            if not isinstance(it, dict) or not it.get('title') or not str(it.get('url', '')).startswith('http'):
                continue
            kind = it.get('kind') if it.get('kind') in ('new', 'screen') else 'new'
            img = it.get('image') or ''
            if not img.startswith('http'):
                img = og_image(it['url'])
            iid = db.add_idea(title=str(it['title'])[:120], maker=str(it.get('maker', ''))[:60], kind=kind, url=it['url'],
                              image=img, why=str(it.get('why', ''))[:600], brief=str(it.get('brief', ''))[:1500],
                              source=str(it.get('source', ''))[:300])
            if iid:
                new.append(it['title'])
        detail = f'{len(new)} new idea(s) from {len(items)} found ({trigger}, {r.tokens:,} tokens)'
        db.set_setting('ideas_last_result', detail)
        db.set_setting('ideas_last_scan', str(int(time.time())))
        if new:
            notify.notify_ideas(len(new), new[:3])
        return len(new), detail
    finally:
        db.set_setting('ideas_scanning', '0')
        _lock.release()


def scan_async(trigger='manual'):
    threading.Thread(target=scan, args=(trigger,), daemon=True).start()


def scheduler_loop(stop_event):
    """Once a day at SCAN_AT local time (and on the first start of a day after that time)."""
    while not stop_event.is_set():
        lt = time.localtime()
        day = time.strftime('%Y-%m-%d', lt)
        due = (lt.tm_hour, lt.tm_min) >= SCAN_AT
        if due and db.setting('ideas_last_day') != day:
            db.set_setting('ideas_last_day', day)
            try:
                scan('daily')
            except Exception as e:
                db.set_setting('ideas_last_result', f'daily scan failed: {e}')
        stop_event.wait(60)
