"""Talk to the watch over wireless ADB (the container runs with host networking so mDNS works).
Pairing keys persist in /root/.android (a volume), so pairing is a one-off.

Galaxy watches drop to power-save Wi-Fi (and stop advertising adb over mDNS) as soon as the screen
times out, so connect() first retries the last known address, then keeps listening for ~45 s.
Every attempt is appended to /app/data/watch.log, shown on the Watch page."""
from __future__ import annotations

import re
import socket
import subprocess
import time
from pathlib import Path

from . import db

LOG = Path('/app/data/watch.log')


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%d %b %H:%M:%S')}  {msg}\n")


def log_tail(n=40):
    try:
        return '\n'.join(LOG.read_text(encoding='utf-8').splitlines()[-n:])
    except FileNotFoundError:
        return '(no attempts yet)'


def adb(*args, timeout=60):
    try:
        p = subprocess.run(['adb', *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 1, f'adb {args[0]} timed out'
    return p.returncode, (p.stdout + p.stderr).strip()


def pair(hostport, code):
    ok = False
    for attempt in (1, 2):                 # the first attempt often reports a protocol fault
        _, out = adb('pair', hostport, code, timeout=40)
        ok = 'Successfully paired' in out
        log(f'pair {hostport} attempt {attempt}: {out[-160:]}')
        if ok:
            break
        time.sleep(2)
    if ok:
        db.set_setting('watch_ip', hostport.split(':')[0])
    return ok, out


def _connected():
    """A ready device: either ip:port or the mDNS name adb auto-connects with (adb-<serial>._adb-tls-connect._tcp)."""
    ip = db.setting('watch_ip')
    _, devs = adb('devices')
    for line in devs.splitlines()[1:]:
        parts = line.rsplit(None, 1)          # mDNS names can contain spaces: "adb-XYZ (2)._adb-tls-connect._tcp"
        if len(parts) == 2 and parts[1] == 'device' and (
                '_adb-tls-connect' in parts[0] or not ip or parts[0].startswith(ip + ':')):
            return parts[0]
    return None


def _try(hp):
    _, out = adb('connect', hp, timeout=15)
    log(f'connect {hp}: {out[-160:]}')
    return 'connected' in out and 'cannot' not in out and 'failed' not in out


def _open(hp):
    host, port = hp.rsplit(':', 1)
    try:
        with socket.create_connection((host, int(port)), timeout=2):
            return True
    except OSError:
        return False


def discover(wait_s=45):
    ip = db.setting('watch_ip')
    deadline = time.time() + wait_s
    while time.time() < deadline:
        _, out = adb('mdns', 'services')
        hits = re.findall(r'_adb-tls-connect\._tcp\s+([\d.]+:\d+)', out)
        if ip:
            hits = [h for h in hits if h.startswith(ip + ':')] or hits
        # stale entries for old ports linger after Wireless debugging is toggled: use one that is open
        live = [h for h in dict.fromkeys(reversed(hits)) if _open(h)]
        if live:
            return live[0]
        time.sleep(3)
    return None


def connect(wait_s=45):
    """Returns (serial, message)."""
    serial = _connected()
    if serial:
        return serial, f'already connected ({serial})'
    last = db.setting('watch_hostport')
    if last and _try(last):
        return last, f'connected to {last} (last known address)'
    log(f'looking for the watch on the network for up to {wait_s}s ...')
    hp = discover(wait_s)
    if not hp:
        log('watch not found')
        return None, ('Watch not found. On the watch open Settings → Developer options → Wireless debugging and keep '
                      'that screen on (tap it now and then) until the install finishes.')
    if _try(hp):
        db.set_setting('watch_hostport', hp)
        return hp, f'connected to {hp}'
    # mDNS can hand out a stale port after Wireless debugging is toggled; a fresh adb server
    # re-resolves it and usually auto-connects by the watch's mDNS name.
    log('advertised port refused; restarting adb and waiting for the watch to auto-connect')
    adb('kill-server')
    adb('start-server')
    for _ in range(10):
        time.sleep(3)
        serial = _connected()
        if serial:
            log(f'auto-connected as {serial}')
            return serial, f'connected ({serial})'
    return None, f'found the watch at {hp} but it refused the connection; toggle Wireless debugging off/on and try again'


def status():
    _, devs = adb('devices', '-l')
    return devs


def install(apk_path, package, shot_path=None):
    """Install, make it the active face, go to the home screen (so it's visible even if the
    owner is sitting on the Wireless debugging screen) and optionally grab a screenshot as proof."""
    serial, msg = connect()
    if not serial:
        return False, msg
    code, out = adb('-s', serial, 'install', '-r', str(apk_path), timeout=180)
    log(f'install {Path(apk_path).name} on {serial}: {out[-160:]}')
    if code or 'Success' not in out:
        return False, out
    _, current = adb('-s', serial, 'shell', 'dumpsys', 'activity', 'service', 'WatchFace', timeout=30)
    if f'Resource only package name {package}' not in current:      # avoid piling up favourites
        _, res = adb('-s', serial, 'shell', 'am', 'broadcast', '-a', 'com.google.android.wearable.app.DEBUG_SURFACE',
                     '--es', 'operation', 'set-watchface', '--es', 'watchFaceId', package)
        log(f'set watch face {package}: {res[-120:]}')
    adb('-s', serial, 'shell', 'input', 'keyevent', 'KEYCODE_HOME')
    if shot_path:
        time.sleep(4)
        with open(shot_path, 'wb') as fh:
            subprocess.run(['adb', '-s', serial, 'exec-out', 'screencap', '-p'], stdout=fh, timeout=30)
    return True, 'Installed, set as your watch face and shown on the watch. The screenshot below is from the watch itself.'


def screenshot(dest):
    serial, msg = connect()
    if not serial:
        return False, msg
    with open(dest, 'wb') as fh:
        p = subprocess.run(['adb', '-s', serial, 'exec-out', 'screencap', '-p'], stdout=fh, timeout=30)
    return p.returncode == 0, 'ok'
