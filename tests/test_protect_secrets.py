"""Tests for the protect_secrets PreToolUse hook (CLAUDE.md security rules)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

HOOK_PATH = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "protect_secrets.py"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("protect_secrets", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _event(tool_name: str, **tool_input: Any) -> dict[str, Any]:
    return {"tool_name": tool_name, "tool_input": tool_input}


@pytest.mark.parametrize(
    "event",
    [
        _event("Read", file_path=r"D:\project\.env"),
        _event("Edit", file_path="credentials.json", old_string="a", new_string="b"),
        _event("Bash", command="cat .env"),
        _event("PowerShell", command="Get-Content credentials.json"),
        _event("Grep", pattern="SHEET_ID", path=".env"),
        _event("Glob", pattern="**/.env"),
    ],
    ids=["read-env", "edit-credentials", "bash-cat-env", "powershell", "grep-path", "glob"],
)
def test_secret_targets_are_blocked(event: dict[str, Any]) -> None:
    assert hook.is_blocked(event)


@pytest.mark.parametrize(
    "event",
    [
        _event(
            "Write",
            file_path="run.ps1",
            content="Get-Content (Join-Path $PSScriptRoot '.env')",
        ),
        _event(
            "Edit",
            file_path="specs/003-dashboard-ui.md",
            old_string="It reads `.env` from the project root",
            new_string="It reads `.env` and credentials.json is never read",
        ),
        _event("Read", file_path=".env.example"),
        _event("Read", file_path="specs/001-data-source.md"),
        _event("Bash", command="git status"),
    ],
    ids=["write-run-ps1", "edit-spec", "read-env-example", "read-spec", "bash-other"],
)
def test_other_targets_are_allowed(event: dict[str, Any]) -> None:
    assert not hook.is_blocked(event)


@pytest.mark.parametrize(
    ("event", "exit_code"),
    [
        (_event("Read", file_path=".env"), 2),
        (_event("Read", file_path=".env.example"), 0),
    ],
)
def test_exit_code(event: dict[str, Any], exit_code: int) -> None:
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == exit_code


# --- git commit messages are not targets ---


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "T9: run.ps1 launcher loads .env (spec 003 §6.6)"',
        "git commit -m 'loads .env, never credentials.json'",
        'git commit -m "T9: launcher" -m "reads .env" -m "Co-Authored-By: X <x@y.z>"',
        'git commit --message "reads .env"',
        'git commit --message=".env loader"',
        'git commit -am "reads .env"',
        'git commit -m".env"',
        'git -C "D:/my repo" commit -m "reads .env"',
        'git add run.ps1 && git commit -m "reads .env" && git push',
        'git commit -q -m "a" -m "b .env" -- run.ps1 tests/test_run_ps1.py',
    ],
)
def test_commit_message_naming_secret_is_allowed(command: str) -> None:
    for tool in ("Bash", "PowerShell"):
        assert not hook.is_blocked(_event(tool, command=command)), (tool, command)


@pytest.mark.parametrize(
    "command",
    [
        # Staging, reading, printing or copying the files stays blocked.
        "git add .env",
        "git add credentials.json",
        "git add -f .env",
        "cat .env",
        "type credentials.json",
        "cp .env backup.txt",
        "Copy-Item credentials.json $env:TEMP",
        "Get-Content .env | Set-Clipboard",
        # A secret named outside the message of the same git commit.
        'git commit -m "x" .env',
        'git commit -m "x" -- credentials.json',
        'git commit -m "x" --include .env',
        "git commit -F .env",
        "git commit --file=.env",
        'git commit --template=.env -m "x"',
        # Another command after or before the commit.
        'git commit -m "x" && cat .env',
        'git commit -m "x"; type .env',
        'git commit -m "x" | Get-Content credentials.json',
        'git commit -m "x" || cp .env out.txt',
        'git commit -m "x"\ncat .env',
        'cat .env && git commit -m "x"',
        # Messages that could run a command are still checked.
        'git commit -m "$(cat .env)"',
        'git commit -m "`cat .env`"',
        'git commit -m "$(Get-Content credentials.json)"',
        'git commit -m "$HOME/.env"',
        'git commit -m "a\\" ; cat .env ; \\"b"',
        # A message flag outside git commit is not exempt.
        'git log -m ".env"',
        'echo -m ".env"',
        'git commit-tree -m ".env"',
    ],
)
def test_secret_outside_plain_commit_message_is_blocked(command: str) -> None:
    for tool in ("Bash", "PowerShell"):
        assert hook.is_blocked(_event(tool, command=command)), (tool, command)


def test_non_shell_tools_are_unchanged() -> None:
    assert hook.is_blocked(_event("Grep", pattern='git commit -m ".env"'))


def test_strip_keeps_everything_but_the_message() -> None:
    command = 'git commit -q -m "loads .env" -- run.ps1 && git push'
    assert hook.strip_commit_messages(command) == 'git commit -q -m "" -- run.ps1 && git push'
