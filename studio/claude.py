"""Runs one agent as a headless `claude -p` session. Dialtwin runs on a Claude subscription only: the CLI
signs in with CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`) or a subscription `claude login` saved in
~/.claude. API keys are removed from the agents' environment so a job can never bill per token. Agent prompts live in studio/agents/<name>.md with a small frontmatter:

---
model: opus
max_turns: 60
timeout_min: 40
tools: Read,Write,Edit,Bash,Glob,Grep
---
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Credentials that would bill per token. Dialtwin is subscription-only, so these never reach the CLI.
API_BILLING_VARS = ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN')

AGENTS = Path(__file__).resolve().parent / 'agents'
DISALLOWED = ['WebSearch', 'Task', 'Agent', 'NotebookEdit', 'TodoWrite']


@dataclass
class Result:
    ok: bool
    text: str
    tokens: int
    detail: str = ''


def _agent(name):
    raw = (AGENTS / f'{name}.md').read_text(encoding='utf-8')
    meta, body = {}, raw
    if raw.startswith('---'):
        head, body = raw[3:].split('---', 1)
        for line in head.strip().splitlines():
            k, _, v = line.partition(':')
            meta[k.strip()] = v.strip()
    return meta, body.strip()


def run(name: str, prompt: str, cwd: Path, log_prefix: Path) -> Result:
    meta, system = _agent(name)
    sys_file = log_prefix.with_suffix('.system.md')
    sys_file.write_text(system, encoding='utf-8')
    log_prefix.with_suffix('.prompt.txt').write_text(prompt, encoding='utf-8')
    cmd = [
        os.environ.get('CLAUDE_BIN', 'claude'), '-p',
        '--output-format', 'stream-json', '--verbose',   # every step is logged, for token analysis
        '--model', meta.get('model', 'opus'),
        '--max-turns', meta.get('max_turns', '60'),
        '--append-system-prompt-file', str(sys_file),
        '--setting-sources', '',
        '--allowedTools', meta.get('tools', 'Read,Write,Edit,Bash,Glob,Grep'),
        '--disallowedTools', ','.join(t for t in DISALLOWED if t not in meta.get('tools', '').split(',')),
        '--permission-mode', 'dontAsk',
        '--add-dir', '/app/engine',
        '--no-session-persistence',
    ]
    env = dict(os.environ, IS_SANDBOX='1')
    for k in API_BILLING_VARS:      # subscription only: never let the CLI fall back to per-token billing
        env.pop(k, None)
    if not env.get('CLAUDE_CODE_OAUTH_TOKEN'):   # an empty line in .env must not shadow a saved login
        env.pop('CLAUDE_CODE_OAUTH_TOKEN', None)
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd, env=env,
                           timeout=int(meta.get('timeout_min', '40')) * 60, encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        return Result(False, '', 0, f'{name} timed out after {meta.get("timeout_min", 40)} min')
    log_prefix.with_suffix('.stderr.txt').write_text(p.stderr, encoding='utf-8')
    log_prefix.with_suffix('.stream.jsonl').write_text(p.stdout, encoding='utf-8')
    res = None
    for line in reversed(p.stdout.strip().splitlines()):
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get('type') == 'result':
            res = ev
            break
    if res is None:
        return Result(False, '', 0, f'exit {p.returncode}: {p.stdout[-400:]} {p.stderr[-400:]}')
    log_prefix.with_suffix('.result.json').write_text(json.dumps(res, indent=1), encoding='utf-8')
    u = res.get('usage') or {}
    tokens = sum(int(u.get(k) or 0) for k in ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'))
    if res.get('is_error'):
        return Result(False, str(res.get('result', '')), tokens, f'{res.get("subtype")}: {str(res.get("result"))[:400]}')
    return Result(True, str(res.get('result', '')), tokens)
