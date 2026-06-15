"""Tests for scripts/_lib/claude_runner.py."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from _lib.claude_runner import (
    ClaudeRunError,
    extract_json_block,
    run_claude,
    run_claude_json,
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


@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_returns_stdout(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="hello", stderr=""
    )
    assert run_claude("prompt", timeout=10) == "hello"
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0][0] == "claude"
    assert args[0][1] == "-p"
    assert kwargs["timeout"] == 10


@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_raises_on_nonzero_exit(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="boom"
    )
    with pytest.raises(ClaudeRunError, match="boom"):
        run_claude("prompt", timeout=10)


@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_json_parses_clean_output(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout='[{"a": 1}]', stderr=""
    )
    assert run_claude_json("prompt") == [{"a": 1}]


@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_json_retries_when_first_output_is_garbage(mock_run) -> None:
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="here's the thing without json", stderr="",
        ),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout='[{"a": 1}]', stderr="",
        ),
    ]
    assert run_claude_json("prompt") == [{"a": 1}]
    assert mock_run.call_count == 2


@patch("_lib.claude_runner.subprocess.run")
def test_run_claude_json_propagates_second_failure(mock_run) -> None:
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
