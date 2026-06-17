"""Tests for scripts/_lib/claude_runner.py."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from _lib.claude_runner import (
    ClaudeRunError,
    _provider,
    _strip_ccs_wrapper,
    extract_json_block,
    run_claude,
    run_claude_json,
)


def _ccs_box(body: str, *, success: bool = True) -> str:
    """A representative `ccs <profile>` result-formatter box wrapping `body`."""
    footer = "[OK] Delegation completed" if success else "[X] Delegation failed"
    return (
        "╭──────────────────────────────╮\n"
        "│[i] Delegated to ONE (ccs:one)│\n"
        "╰──────────────────────────────╯\n"
        "\n"
        "┌─────────────┬────────────────┐\n"
        "│ Working Dir │ /tmp/x         │\n"
        "│ Model       │ ONE            │\n"
        "└─────────────┴────────────────┘\n"
        f"{body}\n"
        "\n"
        f"{footer}\n"
    )


def test_extract_json_block_finds_array_in_prose() -> None:
    raw = "Here is the result:\n```json\n[{\"name\": \"x\"}]\n```\nDone."
    assert extract_json_block(raw) == '[{"name": "x"}]'


def test_extract_json_block_finds_bare_object() -> None:
    raw = "{\"key\": 1}"
    assert extract_json_block(raw) == '{"key": 1}'


def test_extract_json_block_raises_when_no_json() -> None:
    with pytest.raises(ValueError):
        extract_json_block("no json here at all")


def test_strip_ccs_wrapper_removes_box_and_footer() -> None:
    assert _strip_ccs_wrapper(_ccs_box('{"x": 1}')) == '{"x": 1}'


def test_strip_ccs_wrapper_drops_ascii_status_lines() -> None:
    # If the box falls back to ASCII borders, the `[i]`/`[OK]` status lines must
    # still be removed so they don't shadow the real JSON.
    raw = (
        "[i] Delegated to ONE (ccs:one)\n"
        '[{"a": 1}]\n'
        "[OK] Delegation completed\n"
    )
    assert _strip_ccs_wrapper(raw) == '[{"a": 1}]'


def test_strip_ccs_wrapper_passthrough_plain() -> None:
    assert _strip_ccs_wrapper("just text\nmore") == "just text\nmore"


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, "CLAUDE"),       # unset → default CLAUDE
        ("", "CLAUDE"),
        ("   ", "CLAUDE"),
        ("CCS", "CCS"),
        ("ccs", "CCS"),
        ("CCS_ONE", "CCS"),     # legacy alias → CCS
        ("ccs one", "CCS"),     # legacy alias → CCS
        ("CCS-ONE", "CCS"),     # legacy alias → CCS
        ("CLAUDE", "CLAUDE"),
        ("claude", "CLAUDE"),
    ],
)
def test_provider_resolution(value, expected) -> None:
    env = {} if value is None else {"LLM_PROVIDER": value}
    with patch.dict("os.environ", env, clear=True):
        assert _provider() == expected


@patch.dict("os.environ", {"LLM_PROVIDER": "bogus"}, clear=True)
def test_provider_rejects_unknown_value() -> None:
    with pytest.raises(ClaudeRunError, match="LLM_PROVIDER"):
        _provider()


@patch.dict("os.environ", {"LLM_PROVIDER": "CLAUDE"}, clear=True)
@patch("_lib.claude_runner.shutil.which", return_value="/fake/claude")
@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_uses_claude_cli_when_provider_is_claude(
    mock_run, _mock_which
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="hello", stderr=""
    )
    assert run_claude("prompt", timeout=10) == "hello"
    cmd = mock_run.call_args[0][0]
    assert cmd == ["/fake/claude", "-p", "prompt"]


@patch.dict("os.environ", {"LLM_PROVIDER": "CLAUDE"}, clear=True)
@patch("_lib.claude_runner._fixed_candidates", return_value=[])
@patch("_lib.claude_runner.shutil.which", return_value=None)
@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_raises_when_claude_cli_missing(
    mock_run, _mock_which, _mock_cands
) -> None:
    # Not on PATH, no env override, and no fixed-location fallback → must raise.
    from _lib.claude_runner import ProviderNotFoundError
    with pytest.raises(ProviderNotFoundError):
        run_claude("prompt", timeout=10)
    mock_run.assert_not_called()


@patch.dict("os.environ", {"LLM_PROVIDER": "CCS", "CCS_PROFILE": "one"}, clear=True)
@patch("_lib.claude_runner._ccs_command", return_value=["ccs"])
@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_returns_stripped_stdout(mock_run, _mock_cmd) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=_ccs_box("hello"), stderr=""
    )
    assert run_claude("prompt", timeout=10) == "hello"
    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    # ccs <profile> -p <prompt>; profile comes from CCS_PROFILE (here "one").
    assert cmd == ["ccs", "one", "-p", "prompt"]
    assert mock_run.call_args[1]["timeout"] == 10


@patch.dict("os.environ", {"LLM_PROVIDER": "CCS", "CCS_PROFILE": "one"}, clear=True)
@patch("_lib.claude_runner.shutil.which", return_value="/fake/claude")
@patch("_lib.claude_runner._ccs_command", return_value=["ccs"])
@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_injects_ccs_claude_path(mock_run, _mock_cmd, _mock_which) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=_ccs_box("ok"), stderr=""
    )
    run_claude("prompt", timeout=5)
    env = mock_run.call_args[1]["env"]
    assert env["CCS_CLAUDE_PATH"] == "/fake/claude"


@patch.dict("os.environ", {"LLM_PROVIDER": "CCS", "CCS_PROFILE": "one",
                           "CCS_CLAUDE_PATH": "/already/set"}, clear=True)
@patch("_lib.claude_runner._ccs_command", return_value=["ccs"])
@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_respects_existing_ccs_claude_path(mock_run, _mock_cmd) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=_ccs_box("ok"), stderr=""
    )
    run_claude("prompt", timeout=5)
    assert mock_run.call_args[1]["env"]["CCS_CLAUDE_PATH"] == "/already/set"


@patch.dict("os.environ", {"LLM_PROVIDER": "CCS", "CCS_PROFILE": "one"}, clear=True)
@patch("_lib.claude_runner._ccs_command", return_value=["ccs"])
@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_raises_on_nonzero_exit(mock_run, _mock_cmd) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="boom"
    )
    with pytest.raises(ClaudeRunError, match="boom"):
        run_claude("prompt", timeout=10)


@patch.dict("os.environ", {"LLM_PROVIDER": "CCS", "CCS_PROFILE": "one"}, clear=True)
@patch("_lib.claude_runner._ccs_command", return_value=["ccs"])
@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_json_parses_wrapped_output(mock_run, _mock_cmd) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=_ccs_box('[{"a": 1}]'), stderr=""
    )
    assert run_claude_json("prompt") == [{"a": 1}]


@patch.dict("os.environ", {"LLM_PROVIDER": "CCS", "CCS_PROFILE": "one"}, clear=True)
@patch("_lib.claude_runner._ccs_command", return_value=["ccs"])
@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_json_retries_when_first_output_is_garbage(mock_run, _mock_cmd) -> None:
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_ccs_box("here's the thing without json"), stderr="",
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout=_ccs_box('[{"a": 1}]'), stderr="",
        ),
    ]
    assert run_claude_json("prompt") == [{"a": 1}]
    assert mock_run.call_count == 2


@patch.dict("os.environ", {"LLM_PROVIDER": "CCS", "CCS_PROFILE": "one"}, clear=True)
@patch("_lib.claude_runner._ccs_command", return_value=["ccs"])
@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_json_propagates_second_failure(mock_run, _mock_cmd) -> None:
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="garbage 1", stderr=""
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout="garbage 2", stderr=""
        ),
    ]
    with pytest.raises((json.JSONDecodeError, ValueError)):
        run_claude_json("prompt")
