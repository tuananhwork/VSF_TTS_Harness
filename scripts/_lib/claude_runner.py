"""Thin wrapper around `ccs one -p` headless calls.

LLM calls are routed through the CCS delegation CLI (`ccs one`) rather than
invoking `claude` directly, so they use the configured "one" profile. CCS wraps
task output in a formatted box (round header + info table + footer); the box is
peeled off by `_strip_ccs_wrapper` so the delegated task's raw stdout can be
JSON-parsed.

Owns:
- subprocess invocation with timeout (`ccs one -p`)
- non-zero exit detection
- stripping the CCS result-formatter box from stdout
- best-effort JSON block extraction from prose-padded output
- one self-heal retry when JSON parsing fails

Does NOT own prompt content (see judge_prompts.py).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


CCS_BIN = "ccs"
CCS_PROFILE = "one"


class ClaudeRunError(RuntimeError):
    """Raised when `ccs one -p` exits non-zero or output cannot be parsed."""


_FENCED_RE = re.compile(r"```(?:json)?\s*(.+?)```", re.DOTALL)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# Unicode "Box Drawing" block (U+2500–U+257F): the borders of the CCS round
# header box and info table. The delegated task's JSON output never uses these.
_BOX_RE = re.compile(r"[─-╿]")
# CCS status lines (header + footer), matched even if the box falls back to
# ASCII borders — these are the only wrapper lines that can carry stray `[`/`{`.
_STATUS_RE = re.compile(r"Delegated to .*\(ccs:|Delegation (?:completed|failed)")


def extract_json_block(raw: str) -> str:
    """Return the first JSON array or object embedded in `raw`.

    Tolerates fenced ```json blocks, surrounding prose, and trailing notes.
    Raises ValueError if no JSON-looking region is found.
    """
    fenced = _FENCED_RE.search(raw)
    if fenced:
        candidate = fenced.group(1).strip()
        if candidate and candidate[0] in "[{":
            return candidate
    # Fall back: find first [ or { and balance brackets.
    start = -1
    for i, ch in enumerate(raw):
        if ch in "[{":
            start = i
            break
    if start < 0:
        raise ValueError("no JSON array or object found in output")
    opener = raw[start]
    closer = "]" if opener == "[" else "}"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return raw[start : i + 1]
    raise ValueError("unbalanced JSON brackets in output")


def _ccs_command() -> list[str]:
    """Resolve how to invoke `ccs`.

    On Windows the `ccs` launcher is a `.cmd` that forwards args through cmd.exe,
    which mangles prompts containing `%`, `&`, or quotes. When the JS entrypoint
    sits next to the launcher (the npm global-install layout), call it with
    `node` directly to bypass cmd.exe. Otherwise fall back to the launcher.
    """
    launcher = shutil.which(CCS_BIN)
    if launcher is None:
        raise ClaudeRunError(f"ccs CLI not found on PATH ({CCS_BIN})")
    entry = (
        Path(launcher).parent
        / "node_modules" / "@kaitranntt" / "ccs" / "dist" / "ccs.js"
    )
    if entry.exists():
        node = shutil.which("node") or "node"
        return [node, str(entry)]
    return [launcher]


def _subprocess_env() -> dict[str, str]:
    """Environment for the ccs subprocess.

    ccs resolves the Claude binary via ``CCS_CLAUDE_PATH`` first, then falls back
    to a POSIX ``command -v claude`` that fails on Windows cmd.exe. Pre-resolve
    the binary here and inject the path so ccs finds it regardless of whether the
    parent shell exported ``CCS_CLAUDE_PATH``. (The ccs profile still swaps in its
    own account/auth — this only points ccs at the executable.)
    """
    env = os.environ.copy()
    if not env.get("CCS_CLAUDE_PATH"):
        claude = shutil.which("claude")
        if claude:
            env["CCS_CLAUDE_PATH"] = claude
    return env


def _strip_ccs_wrapper(raw: str) -> str:
    """Peel the CCS result-formatter box off `raw`, leaving the task's stdout.

    CCS prints `<round header box>\\n\\n<info table>\\n<task output>\\n\\n<footer>`
    on stdout (progress lines go to stderr). The header/table are box-drawing
    lines; the header and footer also carry `Delegated to …`/`Delegation …`
    status text. Drop those; keep everything else. A plain (unwrapped) string
    passes through unchanged.
    """
    kept: list[str] = []
    for line in raw.splitlines():
        clean = _ANSI_RE.sub("", line)
        if _BOX_RE.search(clean):
            continue
        if _STATUS_RE.search(clean):
            continue
        kept.append(clean)
    return "\n".join(kept).strip()


def run_claude(prompt: str, *, timeout: float = 180.0) -> str:
    """Invoke `ccs one -p <prompt>` and return the delegated task's stdout.

    The CCS result-formatter box is stripped before returning. Raises
    ClaudeRunError on non-zero exit, timeout, or a missing CLI.
    """
    cmd = _ccs_command() + [CCS_PROFILE, "-p", prompt]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_subprocess_env(),
        )
    except subprocess.TimeoutExpired as e:
        raise ClaudeRunError(f"ccs one -p timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise ClaudeRunError(f"ccs CLI not found on PATH ({CCS_BIN})") from e
    if result.returncode != 0:
        raise ClaudeRunError(
            f"ccs one -p exited {result.returncode}: {result.stderr.strip()}"
        )
    return _strip_ccs_wrapper(result.stdout)


def run_claude_json(prompt: str, *, timeout: float = 180.0) -> Any:
    """Run prompt and parse the output as JSON. One self-heal retry on parse fail."""
    raw = run_claude(prompt, timeout=timeout)
    try:
        return json.loads(extract_json_block(raw))
    except (json.JSONDecodeError, ValueError) as first_err:
        repair_prompt = (
            "Fix the following so it is a single JSON value (array or object) "
            "with no prose. Output JSON only.\n\n"
            f"PARSE_ERROR: {first_err}\n\nORIGINAL:\n{raw}"
        )
        raw2 = run_claude(repair_prompt, timeout=min(60.0, timeout))
        return json.loads(extract_json_block(raw2))
