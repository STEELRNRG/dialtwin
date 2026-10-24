"""SQLite store for jobs and their timeline events."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

DATA = Path('/app/data')
DB = DATA / 'studio.db'


def conn():
    DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init():
    with conn() as c:
        c.executescript('''
        create table if not exists jobs (
          id integer primary key autoincrement,
          url text not null, notes text default '', name text default '', slug text default '',
          status text default 'queued',      -- queued | running | done | failed | stopped
          stage text default '', round integer default 0, max_rounds integer default 5,
          scores text default '{}', message text default '', apk text default '',
          version integer default 1, feedback text default '',
          tokens integer default 0, created real, updated real);
        create table if not exists events (
          id integer primary key autoincrement, job_id integer, ts real,
          kind text, text text, image text default '');
        create table if not exists settings (key text primary key, value text);
        create table if not exists ideas (
          id integer primary key autoincrement,
          title text not null, maker text default '', kind text default 'new',   -- spec | archive | genre | new | screen
          url text not null, image text default '', why text default '', brief text default '',
          source text default '', status text default 'new',                     -- new | approved | dismissed
          job_id integer default 0, created real, updated real);
        create unique index if not exists ideas_title on ideas(lower(title));
        ''')
        cols = {r['name'] for r in c.execute('pragma table_info(jobs)')}
        if 'approved' not in cols:
            c.execute('alter table jobs add column approved integer default 0')
        if 'scout_hint' not in cols:
            c.execute("alter table jobs add column scout_hint text default ''")
        # a restart kills in-flight work: surface it instead of leaving it "running"
        c.execute("update jobs set status='failed', message='interrupted by restart: press Continue' where status='running'")


def now():
    return time.time()


def create_job(url, notes, max_rounds):
    with conn() as c:
        cur = c.execute('insert into jobs(url, notes, max_rounds, created, updated) values (?,?,?,?,?)',
                        (url, notes, max_rounds, now(), now()))
        return cur.lastrowid


def job(jid):
    with conn() as c:
        r = c.execute('select * from jobs where id=?', (jid,)).fetchone()
        return dict(r) if r else None


def jobs():
    with conn() as c:
        return [dict(r) for r in c.execute('select * from jobs order by id desc')]


def update(jid, **kw):
    kw['updated'] = now()
    if 'scores' in kw and not isinstance(kw['scores'], str):
        kw['scores'] = json.dumps(kw['scores'])
    with conn() as c:
        c.execute(f'update jobs set {", ".join(f"{k}=?" for k in kw)} where id=?', (*kw.values(), jid))


def add_tokens(jid, n):
    with conn() as c:
        c.execute('update jobs set tokens = tokens + ? where id=?', (int(n or 0), jid))


def event(jid, kind, text, image=''):
    with conn() as c:
        c.execute('insert into events(job_id, ts, kind, text, image) values (?,?,?,?,?)', (jid, now(), kind, text, image))


def events(jid):
    with conn() as c:
        return [dict(r) for r in c.execute('select * from events where job_id=? order by id', (jid,))]


def add_idea(title, url, maker='', kind='new', image='', why='', brief='', source='', **_):
    """Insert an idea; returns its id, or None if the title is already known."""
    with conn() as c:
        cur = c.execute('insert or ignore into ideas(title, maker, kind, url, image, why, brief, source, created, updated) values (?,?,?,?,?,?,?,?,?,?)',
                        (title.strip(), maker, kind, url, image, why, brief, source, now(), now()))
        return cur.lastrowid if cur.rowcount else None


def ideas():
    with conn() as c:
        return [dict(r) for r in c.execute('select * from ideas order by id desc')]


def idea(iid):
    with conn() as c:
        r = c.execute('select * from ideas where id=?', (iid,)).fetchone()
        return dict(r) if r else None


def update_idea(iid, **kw):
    kw['updated'] = now()
    with conn() as c:
        c.execute(f'update ideas set {", ".join(f"{k}=?" for k in kw)} where id=?', (*kw.values(), iid))


def next_queued():
    with conn() as c:
        r = c.execute("select * from jobs where status='queued' order by id limit 1").fetchone()
        return dict(r) if r else None


def setting(key, default=''):
    with conn() as c:
        r = c.execute('select value from settings where key=?', (key,)).fetchone()
        return r['value'] if r else default


def set_setting(key, value):
    with conn() as c:
        c.execute('insert into settings(key, value) values (?,?) on conflict(key) do update set value=excluded.value', (key, value))
