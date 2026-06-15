"""Thin wrapper around `claude -p` headless calls.

Owns:
- subprocess invocation with timeout
- non-zero exit detection
- best-effort JSON block extraction from prose-padded output
- one self-heal retry when JSON parsing fails

Does NOT own prompt content (see judge_prompts.py).
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any


CLAUDE_BIN = "claude"


class ClaudeRunError(RuntimeError):
    """Raised when `claude -p` exits non-zero or output cannot be parsed."""


_FENCED_RE = re.compile(r"```(?:json)?\s*(.+?)```", re.DOTALL)


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


def run_claude(prompt: str, *, timeout: float = 180.0) -> str:
    """Invoke `claude -p <prompt>` and return stdout. Raises on non-zero exit."""
    try:
        result = subprocess.run(
            [CLAUDE_BIN, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise ClaudeRunError(f"claude -p timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise ClaudeRunError(f"claude CLI not found on PATH ({CLAUDE_BIN})") from e
    if result.returncode != 0:
        raise ClaudeRunError(
            f"claude -p exited {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout


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
