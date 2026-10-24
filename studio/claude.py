"""Runs one agent as a headless `claude -p` session. The CLI signs in with ANTHROPIC_API_KEY, or
CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`), or a `claude login` saved in ~/.claude. Agent prompts live in studio/agents/<name>.md with a small frontmatter:

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
        '--output-format', 'json',
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
    for k in ('ANTHROPIC_API_KEY', 'CLAUDE_CODE_OAUTH_TOKEN'):
        if not env.get(k):          # an empty line in .env must not shadow the other sign-in method
            env.pop(k, None)
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd, env=env,
                           timeout=int(meta.get('timeout_min', '40')) * 60, encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        return Result(False, '', 0, f'{name} timed out after {meta.get("timeout_min", 40)} min')
    log_prefix.with_suffix('.stderr.txt').write_text(p.stderr, encoding='utf-8')
    try:
        res = json.loads(p.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return Result(False, '', 0, f'exit {p.returncode}: {p.stdout[-400:]} {p.stderr[-400:]}')
    log_prefix.with_suffix('.result.json').write_text(json.dumps(res, indent=1), encoding='utf-8')
    u = res.get('usage') or {}
    tokens = sum(int(u.get(k) or 0) for k in ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'))
    if res.get('is_error'):
        return Result(False, str(res.get('result', '')), tokens, f'{res.get("subtype")}: {str(res.get("result"))[:400]}')
    return Result(True, str(res.get('result', '')), tokens)
