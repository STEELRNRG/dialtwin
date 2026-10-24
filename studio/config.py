"""All settings come from environment variables (see .env.example)."""
from __future__ import annotations

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

# Stop a job once its agents have used this many tokens (0 = no limit). A typical face takes
# 15-30M tokens, most of them cheap cache reads.
MAX_TOKENS_PER_JOB = int(os.environ.get('MAX_TOKENS_PER_JOB', '40000000') or 0)


def claude_auth():
    """How the Claude CLI will sign in, or '' if it has nothing to use."""
    if os.environ.get('ANTHROPIC_API_KEY'):
        return 'API key'
    if os.environ.get('CLAUDE_CODE_OAUTH_TOKEN'):
        return 'Claude subscription token'
    if (Path.home() / '.claude' / '.credentials.json').exists():
        return 'Claude login'
    return ''
