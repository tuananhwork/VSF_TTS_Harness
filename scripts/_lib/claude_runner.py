"""Thin wrapper around headless LLM calls.

The LLM provider is selected by the ``LLM_PROVIDER`` environment variable:

- ``CCS_ONE`` (default) — route through the CCS delegation CLI (`ccs one -p`),
  using the configured "one" profile. CCS wraps task output in a formatted box
  (round header + info table + footer); the box is peeled off by
  `_strip_ccs_wrapper` so the delegated task's raw stdout can be JSON-parsed.
- ``CLAUDE`` — invoke the `claude` CLI directly in headless mode (`claude -p`),
  bypassing CCS entirely. Output is plain stdout (no wrapper box).

The value is case-insensitive and tolerates spaces/hyphens (`CCS ONE`,
`ccs-one` all resolve to ``CCS_ONE``).

Owns:
- provider selection from ``LLM_PROVIDER``
- subprocess invocation with timeout (`ccs one -p` or `claude -p`)
- non-zero exit detection
- stripping the CCS result-formatter box from stdout (no-op for plain output)
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
import threading
from pathlib import Path
from typing import Any


CCS_BIN = "ccs"
CLAUDE_BIN = "claude"


def _ccs_profile() -> str:
    val = os.environ.get("CCS_PROFILE", "").strip()
    if not val:
        raise ClaudeRunError(
            "CCS_PROFILE is not set. Pass --ccs-profile NAME when using --llm-provider=ccs-one."
        )
    return val

LLM_PROVIDER_ENV = "LLM_PROVIDER"
PROVIDER_CLAUDE = "CLAUDE"
PROVIDER_CCS_ONE = "CCS_ONE"


def _provider() -> str:
    """Resolve the LLM provider from ``LLM_PROVIDER`` (default ``CCS_ONE``).

    Case-insensitive; spaces and hyphens are normalized (`CCS ONE`, `ccs-one`).
    Raises ClaudeRunError on an unrecognized value rather than silently falling
    back, so a misconfigured switch fails loudly.
    """
    raw = os.environ.get(LLM_PROVIDER_ENV)
    if not raw or not raw.strip():
        return PROVIDER_CLAUDE
    normalized = raw.strip().upper().replace(" ", "_").replace("-", "_")
    if normalized == PROVIDER_CLAUDE:
        return PROVIDER_CLAUDE
    if normalized in (PROVIDER_CCS_ONE, "CCS", "ONE"):
        return PROVIDER_CCS_ONE
    raise ClaudeRunError(
        f"{LLM_PROVIDER_ENV}={raw!r} is invalid; expected "
        f"{PROVIDER_CLAUDE!r} or {PROVIDER_CCS_ONE!r}"
    )


def provider_label() -> str:
    """Human-readable label for the active provider command (no prompt).

    Returns ``claude -p`` or ``ccs <profile> -p``, reflecting the real
    ``LLM_PROVIDER``/``CCS_PROFILE`` so log lines don't hardcode ``ccs one -p``.
    Never raises (uses a placeholder when the profile is unset) — it's only a label.
    """
    if _provider() == PROVIDER_CLAUDE:
        return "claude -p"
    profile = os.environ.get("CCS_PROFILE", "").strip() or "<profile>"
    return f"ccs {profile} -p"


class ClaudeRunError(RuntimeError):
    """Raised when the provider command exits non-zero or output cannot be parsed."""


class ClaudeRunCancelled(Exception):
    """Raised when an in-flight (or pending) LLM call is cancelled by the user.

    Deliberately NOT a subclass of ClaudeRunError so the judge/synth retry
    `except (ClaudeRunError, ...)` blocks don't swallow it — a cancel must
    propagate all the way up and stop the pipeline.
    """


def _kill_proc(proc: "subprocess.Popen") -> None:
    """Kill a running provider process — its whole tree on Windows.

    `claude`/`ccs` spawn child node processes; killing only the direct child
    can leave the real LLM request running (and billing). On Windows we use
    `taskkill /T` to take down the tree; elsewhere `proc.kill()` plus the
    process group. Best-effort: never raises.
    """
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                **_no_window_kwargs(),
            )
        else:
            proc.kill()
    except Exception:
        pass


class CancelToken:
    """Cooperative cancel handle shared between the GUI thread and the worker(s).

    The GUI thread calls `cancel()`; worker threads running `run_claude` register
    their live `Popen` here so `cancel()` can kill it immediately — unblocking the
    in-flight `communicate()` and stopping token spend. `raise_if_cancelled()`
    lets the pipeline bail out between calls without launching anything new.
    """

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._procs: set[subprocess.Popen] = set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            procs = list(self._procs)
        for p in procs:
            _kill_proc(p)

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise ClaudeRunCancelled("cancelled by user")

    def _register(self, proc: "subprocess.Popen") -> None:
        with self._lock:
            self._procs.add(proc)
        # Race: cancel() may have fired between raise_if_cancelled and Popen.
        if self._event.is_set():
            _kill_proc(proc)

    def _unregister(self, proc: "subprocess.Popen") -> None:
        with self._lock:
            self._procs.discard(proc)


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


def _claude_command() -> list[str]:
    """Resolve how to invoke `claude` in headless mode.

    Returns the argv prefix up to (but excluding) the prompt, i.e. ``[claude,
    "-p"]``. Raises ClaudeRunError if the `claude` CLI is not on PATH.
    """
    launcher = shutil.which(CLAUDE_BIN)
    if launcher is None:
        raise ClaudeRunError(f"claude CLI not found on PATH ({CLAUDE_BIN})")
    return [launcher, "-p"]


def _no_window_kwargs() -> dict[str, Any]:
    """Extra ``subprocess`` kwargs that stop a console window flashing on Windows.

    When the GUI runs as a windowed (console-less) process, spawning the
    ``claude``/``ccs`` CLIs makes Windows allocate a fresh console for each
    child — empty black windows pop up and vanish. ``CREATE_NO_WINDOW`` keeps
    the child console-less; ``STARTUPINFO``/``SW_HIDE`` covers ``.cmd``/``.bat``
    shims (npm shims) that go through cmd.exe. No-op on non-Windows platforms.
    """
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


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


def _exec_cancellable(
    cmd: list[str], env: dict[str, str], timeout: float,
    label: str, missing_bin: str, missing_name: str, cancel: "CancelToken",
) -> str:
    """Run `cmd` via Popen so `cancel` can kill it mid-flight.

    When `cancel.cancel()` fires from another thread it kills the process; the
    blocked `communicate()` returns and we raise ClaudeRunCancelled instead of a
    bogus non-zero-exit error.
    """
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            stdin=subprocess.DEVNULL,
            **_no_window_kwargs(),
        )
    except FileNotFoundError as e:
        raise ClaudeRunError(
            f"{missing_name} CLI not found on PATH ({missing_bin})"
        ) from e

    cancel._register(proc)
    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as e:
            _kill_proc(proc)
            proc.communicate()
            raise ClaudeRunError(f"{label} timed out after {timeout}s") from e
    finally:
        cancel._unregister(proc)

    # If cancel killed the proc, communicate() returned with a non-zero code;
    # surface it as a cancel, not a command failure.
    cancel.raise_if_cancelled()
    if proc.returncode != 0:
        raise ClaudeRunError(f"{label} exited {proc.returncode}: {(stderr or '').strip()}")
    return stdout


def run_claude(
    prompt: str, *, timeout: float = 180.0, cancel: "CancelToken | None" = None,
) -> str:
    """Invoke the selected provider with `<prompt>` and return its stdout.

    Routes to `claude -p` or `ccs one -p` per the ``LLM_PROVIDER`` env var
    (see module docstring). The CCS result-formatter box is stripped before
    returning (a no-op for the plain `claude` output). Raises ClaudeRunError on
    non-zero exit, timeout, or a missing CLI.

    Pass `cancel` (a CancelToken) to make the call killable: if cancelled from
    another thread the subprocess is terminated and ClaudeRunCancelled is raised
    so no further tokens are spent.
    """
    if cancel is not None:
        cancel.raise_if_cancelled()

    if _provider() == PROVIDER_CLAUDE:
        cmd = _claude_command() + [prompt]
        env = os.environ.copy()
        label = "claude -p"
        missing_bin, missing_name = CLAUDE_BIN, "claude"
    else:
        profile = _ccs_profile()
        cmd = _ccs_command() + [profile, "-p", prompt]
        env = _subprocess_env()
        label = f"ccs {profile} -p"
        missing_bin, missing_name = CCS_BIN, "ccs"

    if cancel is not None:
        return _strip_ccs_wrapper(
            _exec_cancellable(cmd, env, timeout, label, missing_bin, missing_name, cancel)
        )

    # No cancel token → simple blocking call (keeps the original code path).
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            stdin=subprocess.DEVNULL,
            **_no_window_kwargs(),
        )
    except subprocess.TimeoutExpired as e:
        raise ClaudeRunError(f"{label} timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise ClaudeRunError(
            f"{missing_name} CLI not found on PATH ({missing_bin})"
        ) from e
    if result.returncode != 0:
        raise ClaudeRunError(
            f"{label} exited {result.returncode}: {result.stderr.strip()}"
        )
    return _strip_ccs_wrapper(result.stdout)


def run_claude_json(
    prompt: str, *, timeout: float = 180.0, cancel: "CancelToken | None" = None,
) -> Any:
    """Run prompt and parse the output as JSON. One self-heal retry on parse fail."""
    raw = run_claude(prompt, timeout=timeout, cancel=cancel)
    try:
        return json.loads(extract_json_block(raw))
    except (json.JSONDecodeError, ValueError) as first_err:
        repair_prompt = (
            "Fix the following so it is a single JSON value (array or object) "
            "with no prose. Output JSON only.\n\n"
            f"PARSE_ERROR: {first_err}\n\nORIGINAL:\n{raw}"
        )
        raw2 = run_claude(repair_prompt, timeout=min(60.0, timeout), cancel=cancel)
        return json.loads(extract_json_block(raw2))
