"""Optional notifications when a face needs you or is ready. Both channels are off unless configured.

- NOTIFY_URL: any URL that takes a plain-text POST, e.g. an ntfy topic (https://ntfy.sh/<topic>).
  The title goes in the `Title` header and the job link in `Click`, which ntfy understands.
- Home Assistant: HA_URL + HA_TOKEN (a long-lived access token) + HA_NOTIFY_TARGETS
  (comma-separated notify services, e.g. mobile_app_my_phone). HA_TOKEN_ID + HA_JWT_KEY can be
  used instead of HA_TOKEN to mint short-lived tokens from a refresh token.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.request

from . import config


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def _ha_token():
    if os.environ.get('HA_TOKEN'):
        return os.environ['HA_TOKEN']
    now = int(time.time())
    h = _b64(json.dumps({'alg': 'HS256', 'typ': 'JWT'}, separators=(',', ':')).encode())
    c = _b64(json.dumps({'iss': os.environ['HA_TOKEN_ID'], 'iat': now, 'exp': now + 300}, separators=(',', ':')).encode())
    s = hmac.new(os.environ['HA_JWT_KEY'].encode(), f'{h}.{c}'.encode(), hashlib.sha256).digest()
    return f'{h}.{c}.{_b64(s)}'


def _ha_ready():
    return bool(os.environ.get('HA_URL') and os.environ.get('HA_NOTIFY_TARGETS')
                and (os.environ.get('HA_TOKEN') or (os.environ.get('HA_TOKEN_ID') and os.environ.get('HA_JWT_KEY'))))


def _ha(title, text, url, tag):
    domain_url = os.environ['HA_URL'].rstrip('/')
    for t in [x.strip() for x in os.environ['HA_NOTIFY_TARGETS'].split(',') if x.strip()]:
        body = {'title': title, 'message': text,
                'data': {'url': url, 'clickAction': url, 'tag': tag, 'channel': config.APP_NAME}}
        req = urllib.request.Request(f'{domain_url}/api/services/notify/{t}', data=json.dumps(body).encode(), method='POST',
                                     headers={'Authorization': f'Bearer {_ha_token()}', 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                r.read()
        except Exception:
            pass


def _webhook(title, text, url):
    req = urllib.request.Request(os.environ['NOTIFY_URL'], data=text.encode(), method='POST',
                                 headers={'Title': title.encode('ascii', 'replace').decode(), 'Click': url})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
    except Exception:
        pass


def send(title, text, path='/', tag='dialtwin'):
    url = config.STUDIO_URL + path
    if os.environ.get('NOTIFY_URL'):
        _webhook(title, text, url)
    if _ha_ready():
        _ha(title, text, url, tag)


def notify_ideas(n, titles):
    text = ', '.join(titles) + (' …' if n > len(titles) else '')
    send(f'{n} new watch idea{"s" if n != 1 else ""}', text, '/ideas', 'dialtwin_ideas')


def notify_done(j):
    send('Watch face ready', f"{j['name']} is built and ready to install.", f"/job/{j['id']}", f"dialtwin_{j['id']}")


def notify_review(j):
    send('Check the reference photos', f"{j['name']}: approve the photos before building starts.", f"/job/{j['id']}", f"dialtwin_{j['id']}")


def notify_failed(j):
    send('Watch face failed', f"{j['name'] or j['url']}: {j['message'][:150]}", f"/job/{j['id']}", f"dialtwin_{j['id']}")
