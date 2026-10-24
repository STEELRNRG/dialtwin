"""One job end to end: fetch page -> scout -> build/critique rounds -> package -> APK.

Each stage is resumable: a job that is continued (more rounds, user feedback, or after a restart)
picks up from what already exists in its folder.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

from . import claude, config, db, notify

JOBS = Path('/app/jobs')
ENGINE = Path('/app/engine')
PASS_FIDELITY = 8.0
PASS_PLATFORM = 7.5


class Stopped(Exception):
    pass


class OverBudget(Exception):
    pass


# Added to the scout, builder and fidelity prompts unless KEEP_BRANDING is on.
NO_BRANDING = (
    'BRANDING RULE: leave out every brand name, logo, emblem, model name and trademark printed on the '
    'dial or bezel (e.g. the maker\'s name, "Swiss Made", "Automatic"). Leave that space plain, or keep '
    'generic functional text only (scale numbers, "24", "DATE"). Critics: a missing logo or brand text '
    'is correct here, never an issue and never a reason to score down.'
)


def branding_note():
    return '' if config.KEEP_BRANDING else '\n' + NO_BRANDING


def package_id(j):
    return f"{config.PACKAGE_PREFIX}.{j['slug'] or 'face'}"


def job_dir(jid):
    return JOBS / str(jid)


def sh(cmd, cwd, timeout=900):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, encoding='utf-8', errors='replace')
    return p.returncode, (p.stdout + '\n' + p.stderr).strip()


def check_stop(jid):
    if db.job(jid)['status'] == 'stopped':
        raise Stopped()


def agent(jid, name, prompt, cwd, label):
    logs = cwd / 'logs'
    logs.mkdir(exist_ok=True)
    r = claude.run(name, prompt, cwd, logs / label)
    db.add_tokens(jid, r.tokens)
    used = int(db.job(jid).get('tokens') or 0)
    if config.MAX_TOKENS_PER_JOB and used > config.MAX_TOKENS_PER_JOB:
        raise OverBudget(f'Stopped: this job has used {used:,} tokens, over the MAX_TOKENS_PER_JOB limit of '
                         f'{config.MAX_TOKENS_PER_JOB:,}. Raise MAX_TOKENS_PER_JOB and restart to continue.')
    return r


def slugify(s):
    return re.sub(r'[^a-z0-9]+', '', s.lower())[:24] or 'face'


def min_scores(path):
    try:
        d = json.loads(path.read_text())
        vals = [float(v) for v in d.get('scores', {}).values()]
        return (min(vals) if vals else 0.0), d
    except Exception:
        return 0.0, {}


# ------------------------------------------------------------------ stages
def stage_fetch(j, d):
    if (d / 'source' / 'images.json').exists():
        return
    db.update(j['id'], stage='fetching page')
    code, out = sh(['node', str(ENGINE / 'fetch_page.mjs'), j['url']], d, timeout=420)
    if code:
        raise RuntimeError(f'could not fetch the page: {out[-600:]}')
    info = json.loads(out.strip().splitlines()[-1])
    db.event(j['id'], 'stage', f'Fetched "{info["title"]}": {info["images"]} images', 'source/page.png')
    if not info['images']:
        raise RuntimeError('no product images found on that page (bot protection or JavaScript-only gallery?)')


def stage_scout(j, d):
    if (d / 'reference' / 'variants.json').exists():
        return
    db.update(j['id'], stage='scout: picking reference photos')
    (d / 'reference').mkdir(exist_ok=True)
    hint = f"\nOWNER'S CHOICE (overrides your own judgement): {j['scout_hint']}" if j.get('scout_hint') else ''
    prompt = (f"Product page: {j['url']}\nUser notes: {j['notes'] or '(none)'}{hint}\n"
              f"Do the scout job described in your instructions.{branding_note()}")
    r = agent(j['id'], 'scout', prompt, d, 'scout')
    if (d / 'reference' / 'FAILED.txt').exists():
        raise RuntimeError('scout: ' + (d / 'reference' / 'FAILED.txt').read_text()[:500])
    if not (d / 'reference' / 'variants.json').exists():
        raise RuntimeError(f'scout did not produce reference/variants.json. {r.detail}')
    v = json.loads((d / 'reference' / 'variants.json').read_text())
    name = v.get('name') or 'Watch'
    db.update(j['id'], name=name, slug=slugify(name))
    # reference strip for the page
    refs = [d / 'reference' / f"ref_{x['id']}.png" for x in v['variants']]
    code, _ = sh(['python3', '-c', (
        'import sys; from PIL import Image\n'
        'fs=sys.argv[1:]; s=Image.new("RGB",(310*len(fs)+10,320),"#111")\n'
        'for i,f in enumerate(fs): s.paste(Image.open(f).convert("RGB").resize((300,300)),(10+i*310,10))\n'
        's.save("reference/strip.png")')] + [str(p) for p in refs if p.exists()], d)
    db.event(j['id'], 'stage', f"Scout: {name}: {', '.join(x['label'] for x in v['variants'])}", 'reference/strip.png')


def run_critic(j, d, name, rnd, results):
    feedback = f"\nThe owner asked for: {j['feedback']}\nCheck that it was done." if j['feedback'] else ''
    prompt = f"Round: {rnd}\nCritique the renders in out/{rnd}/ and write critiques/{rnd}_{name}.json.{feedback}{branding_note()}"
    results[name] = agent(j['id'], name, prompt, d, f'{rnd}_{name}')


def stage_rounds(j, d):
    jid = j['id']
    (d / 'critiques').mkdir(exist_ok=True)
    rnd_no = j['round']
    while rnd_no < j['max_rounds']:
        check_stop(jid)
        j = db.job(jid)          # pick up feedback typed while the job was running
        rnd_no += 1
        rnd = f'r{rnd_no}'
        db.update(jid, round=rnd_no, stage=f'round {rnd_no}: builder')
        prev = [p.name for p in sorted((d / 'critiques').glob(f'r{rnd_no - 1}_*.json'))]
        parts = [f'Round id: {rnd}.']
        if rnd_no == 1 and not (d / 'face.js').exists():
            parts.append('Write face.js from scratch.')
        else:
            parts.append('Improve face.js. Critiques from the last round: ' + (', '.join(f'critiques/{p}' for p in prev) or '(none)'))
        if j['feedback']:
            parts.append(f"OWNER FEEDBACK (highest priority): {j['feedback']}")
        if j['notes']:
            parts.append(f"Owner notes from submission: {j['notes']}")
        if not config.KEEP_BRANDING:
            parts.append(NO_BRANDING)
        r = agent(jid, 'builder', '\n'.join(parts), d, f'{rnd}_builder')
        check_stop(jid)
        # the pipeline renders again so the critics always see the final face.js
        code, out = sh(['node', str(ENGINE / 'render.mjs'), rnd], d, timeout=600)
        if code:
            db.event(jid, 'error', f'{rnd}: render failed after builder: {out[-500:]}')
            if rnd_no >= j['max_rounds']:
                raise RuntimeError('face.js does not render')
            continue
        shutil.copy(d / 'face.js', d / 'out' / rnd / 'face.js')   # so the best round can be packaged later
        db.event(jid, 'round', f'Round {rnd_no} built. {r.text[-600:] if r.ok else r.detail}', f'out/{rnd}/sheet.png')

        db.update(jid, stage=f'round {rnd_no}: critics reviewing')
        results = {}
        ts = [threading.Thread(target=run_critic, args=(j, d, n, rnd, results)) for n in ('fidelity', 'platform')]
        [t.start() for t in ts]
        [t.join() for t in ts]
        f_min, f = min_scores(d / 'critiques' / f'{rnd}_fidelity.json')
        p_min, p = min_scores(d / 'critiques' / f'{rnd}_platform.json')
        scores = json.loads(db.job(jid)['scores'] or '{}')
        scores[rnd] = {'fidelity': f.get('scores', {}), 'platform': p.get('scores', {})}
        db.update(jid, scores=scores)
        db.event(jid, 'critique', json.dumps({'round': rnd_no, 'fidelity': f, 'platform': p}))
        if f_min >= PASS_FIDELITY and p_min >= PASS_PLATFORM:
            db.event(jid, 'stage', f'Round {rnd_no} passed (fidelity {f_min}, watch {p_min}).')
            break
        if f.get('diminishing_returns') and f_min >= 7.5 and p_min >= 7.0:
            db.event(jid, 'stage', f'Critics report diminishing returns at round {rnd_no}; stopping here.')
            break
        # stall: no fidelity gain over two rounds
        hist = [min(map(float, s['fidelity'].values() or [0])) for k, s in sorted(scores.items(), key=lambda kv: int(kv[0][1:]))]
        if len(hist) >= 3 and hist[-1] <= hist[-3]:
            db.event(jid, 'stage', f'No improvement over two rounds ({hist[-3]} → {hist[-1]}); stopping.')
            break


def pick_best_round(jid, d):
    """Restore face.js from the best-scoring round (min fidelity + min watch score; later wins ties)."""
    scores = json.loads(db.job(jid)['scores'] or '{}')
    best, best_val = None, -1.0
    for rnd, s in sorted(scores.items(), key=lambda kv: int(kv[0][1:])):
        f = min(map(float, s['fidelity'].values() or [0]))
        p = min(map(float, s['platform'].values() or [0]))
        val = f + 0.5 * p
        if val >= best_val and (d / 'out' / rnd / 'face.js').exists():
            best, best_val = rnd, val
    if best and (d / 'out' / best / 'face.js').read_bytes() != (d / 'face.js').read_bytes():
        shutil.copy(d / 'face.js', d / 'face.latest.js')
        shutil.copy(d / 'out' / best / 'face.js', d / 'face.js')
        db.event(jid, 'stage', f'Packaging round {best[1:]} (best scores); the last round is kept as face.latest.js.')
    return best


def stage_package(j, d):
    jid = j['id']
    j = db.job(jid)
    db.update(jid, stage='packaging')
    pick_best_round(jid, d)
    version = j['version']
    pkg = package_id(j)
    for attempt in range(3):
        code, out = sh(['node', str(ENGINE / 'export.mjs')], d, timeout=900)
        if not code:
            code, out = sh(['python3', str(ENGINE / 'package.py'), '--package', pkg, '--label', j['name'] or 'Watch face',
                            '--version', str(version)], d, timeout=600)
        if not code:
            code, out = sh(['sh', str(ENGINE / 'build_apk.sh'), j['slug']], d, timeout=600)
        if not code:
            break
        db.event(jid, 'error', f'Packaging failed (attempt {attempt + 1}): {out[-800:]}')
        if attempt == 2:
            raise RuntimeError('packaging failed three times')
        (d / 'build').mkdir(exist_ok=True)
        (d / 'build' / 'package_error.txt').write_text(out[-6000:])
        agent(jid, 'builder', 'Packaging failed. The error is in build/package_error.txt. Fix face.js (manifest or layers) '
              'so export.mjs + package.py succeed; re-run `node /app/engine/export.mjs` and '
              f'`python3 /app/engine/package.py --package {pkg} --label test` to confirm.', d, f'fix{attempt}')
    apk = f"build/{j['slug']}.apk"
    db.update(jid, apk=apk, version=version + 1)
    db.event(jid, 'stage', f'APK built: {pkg} v{version} (schema valid, memory check passed)')


def run(jid):
    j = db.job(jid)
    d = job_dir(jid)
    d.mkdir(parents=True, exist_ok=True)
    db.update(jid, status='running', message='')
    try:
        stage_fetch(j, d)
        check_stop(jid)
        stage_scout(db.job(jid), d)
        check_stop(jid)
        if not db.job(jid)['approved']:
            # the owner checks the reference photos before any building: a wrong reference
            # can't be caught by critics who compare against that same reference
            db.update(jid, status='review', stage='waiting for you to check the reference photos')
            db.event(jid, 'stage', 'Check the reference photos: approve them or pick a different photo.', 'reference/strip.png')
            notify.notify_review(db.job(jid))
            return
        stage_rounds(db.job(jid), d)
        check_stop(jid)
        stage_package(j, d)
        j = db.job(jid)
        db.update(jid, status='done', stage='ready to install', feedback='')
        notify.notify_done(j)
    except Stopped:
        db.update(jid, stage='stopped by you')
    except OverBudget as e:
        db.update(jid, status='stopped', stage='token limit reached', message=str(e))
        db.event(jid, 'error', str(e))
        notify.notify_failed(db.job(jid))
    except Exception as e:  # noqa: BLE001 - surface anything to the page
        db.update(jid, status='failed', message=str(e)[:1000])
        db.event(jid, 'error', str(e)[:2000])
        notify.notify_failed(db.job(jid))


def worker_loop(stop_event):
    db.init()
    while not stop_event.is_set():
        j = db.next_queued()
        if j:
            run(j['id'])
        else:
            stop_event.wait(5)
