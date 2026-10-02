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
