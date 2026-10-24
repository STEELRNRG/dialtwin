"""All settings come from environment variables (see .env.example)."""
from __future__ import annotations

import json
import os
from pathlib import Path


def _flag(name, default='0'):
    return os.environ.get(name, default).strip().lower() in ('1', 'true', 'yes', 'on')


APP_NAME = os.environ.get('APP_NAME', 'Dialtwin')
STUDIO_URL = os.environ.get('STUDIO_URL', 'http://localhost:8097').rstrip('/')

# Android package id of every face is f'{PACKAGE_PREFIX}.{slug}'. Changing it later installs
# rebuilt faces as new apps instead of updating the old ones.
PACKAGE_PREFIX = os.environ.get('PACKAGE_PREFIX', 'com.dialtwin.face').strip('.')

# Off by default: faces leave out brand names, logos and model names printed on the dial.
KEEP_BRANDING = _flag('KEEP_BRANDING')

# The ideas scout searches the web once a day. It costs ~3M tokens a run, so it is opt-in.
IDEAS_DAILY = _flag('IDEAS_DAILY')

# Stop a job once its agents have used this many tokens (0 = no limit). A round takes
# about 1M tokens (most of them cache reads); 15M leaves room for ~10 rounds plus the scout.
MAX_TOKENS_PER_JOB = int(os.environ.get('MAX_TOKENS_PER_JOB', '15000000') or 0)


def claude_auth():
    """How the Claude CLI will sign in, or '' if there is no subscription to use. API keys don't count:
    Dialtwin runs on a Claude Pro/Max subscription only and never bills per token."""
    if os.environ.get('CLAUDE_CODE_OAUTH_TOKEN'):
        return 'Claude subscription token'
    creds = Path.home() / '.claude' / '.credentials.json'
    try:
        if 'claudeAiOauth' in json.loads(creds.read_text(encoding='utf-8')):
            return 'Claude login'
    except (OSError, ValueError):
        pass
    return ''


def api_key_ignored():
    """True when an API key is set in .env. It is ignored; the UI says so."""
    return bool(os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_AUTH_TOKEN'))
