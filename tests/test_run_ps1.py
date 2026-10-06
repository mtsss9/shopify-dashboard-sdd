"""Tests for the run.ps1 launcher (specs/003-dashboard-ui.md §6.6, plan §3, decision U8).

Every test works on a fake .env in a temp folder; the project's own .env is never
touched. Functions are tested by dot-sourcing run.ps1, which only defines them.
The full script is run only from a temp copy, where it stops before Streamlit.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RUN_PS1 = Path(__file__).resolve().parent.parent / "run.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")

pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not installed")

SECRET = "s3cret-value-never-printed"


def _quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _powershell(*args: str) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _write_env(folder: Path, content: str) -> Path:
    path = folder / ".env"
    path.write_text(content, encoding="utf-8")
    return path


def _parse(tmp_path: Path, content: str) -> dict[str, str]:
    env_file = _write_env(tmp_path, content)
    result = _powershell(
        "-Command",
        f". {_quote(RUN_PS1)}; Read-DotEnv -Path {_quote(env_file)} | ConvertTo-Json -Compress",
    )
    assert result.returncode == 0, result.stderr
    output = result.stdout.strip()
    return json.loads(output) if output else {}


def _run_copy(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    script = tmp_path / "run.ps1"
    shutil.copy(RUN_PS1, script)
    return _powershell("-File", str(script))


# --- Read-DotEnv: parsing (decision U8) ---


def test_parses_key_value_pairs(tmp_path: Path) -> None:
    pairs = _parse(tmp_path, "SHEET_ID=abc123\nGOOGLE_APPLICATION_CREDENTIALS=C:\\keys\\sa.json\n")
    assert pairs == {"SHEET_ID": "abc123", "GOOGLE_APPLICATION_CREDENTIALS": "C:\\keys\\sa.json"}


def test_skips_blank_and_comment_lines(tmp_path: Path) -> None:
    content = "# a comment\n\n   \n  # indented comment\nSHEET_ID=abc\n"
    assert _parse(tmp_path, content) == {"SHEET_ID": "abc"}


def test_splits_on_first_equals_only(tmp_path: Path) -> None:
    assert _parse(tmp_path, "SHEET_ID=a=b==c\n") == {"SHEET_ID": "a=b==c"}


def test_trims_key_and_value(tmp_path: Path) -> None:
    assert _parse(tmp_path, "  SHEET_ID  =   abc  \n") == {"SHEET_ID": "abc"}


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('SHEET_ID="abc def"', "abc def"),
        ("SHEET_ID='abc def'", "abc def"),
        ('SHEET_ID=""', ""),
        ("SHEET_ID=\"abc'", "\"abc'"),  # mismatched quotes are kept
        ('SHEET_ID=""abc""', '"abc"'),  # only one pair is removed
        ('SHEET_ID="', '"'),
        ("SHEET_ID=a # not a comment", "a # not a comment"),
    ],
)
def test_strips_one_pair_of_matching_quotes(tmp_path: Path, line: str, expected: str) -> None:
    assert _parse(tmp_path, line + "\n") == {"SHEET_ID": expected}


def test_later_duplicate_key_wins(tmp_path: Path) -> None:
    assert _parse(tmp_path, "SHEET_ID=first\nSHEET_ID=second\n") == {"SHEET_ID": "second"}


def test_empty_file_gives_no_pairs(tmp_path: Path) -> None:
    assert _parse(tmp_path, "") == {}


def test_utf8_bom_is_ignored(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SHEET_ID=abc\n", encoding="utf-8-sig")
    result = _powershell(
        "-Command",
        f". {_quote(RUN_PS1)}; Read-DotEnv -Path {_quote(env_file)} | ConvertTo-Json -Compress",
    )
    assert json.loads(result.stdout) == {"SHEET_ID": "abc"}


@pytest.mark.parametrize("bad_line", [SECRET, f"={SECRET}"])
def test_line_without_key_value_names_line_number_only(tmp_path: Path, bad_line: str) -> None:
    env_file = _write_env(tmp_path, f"# comment\nSHEET_ID=abc\n{bad_line}\n")
    result = _powershell("-Command", f". {_quote(RUN_PS1)}; Read-DotEnv -Path {_quote(env_file)}")
    assert result.returncode != 0
    assert "Line 3 of .env is not a KEY=VALUE line." in result.stderr
    assert SECRET not in result.stdout + result.stderr


# --- Set-DotEnv: .env always wins (§6.6) ---


def test_env_value_replaces_session_value(tmp_path: Path) -> None:
    env_file = _write_env(tmp_path, "SHEET_ID=from-dotenv\n")
    result = _powershell(
        "-Command",
        "$env:SHEET_ID = 'from-session'; "
        f". {_quote(RUN_PS1)}; "
        f"Set-DotEnv -Pairs (Read-DotEnv -Path {_quote(env_file)}); "
        "$env:SHEET_ID",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "from-dotenv"


def test_dot_sourcing_does_not_read_env_or_start_app(tmp_path: Path) -> None:
    result = _powershell("-Command", f". {_quote(RUN_PS1)}; 'loaded'")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "loaded"


# --- Whole script, from a temp copy (never reaches Streamlit) ---


def test_missing_env_stops_with_message_and_nonzero_exit(tmp_path: Path) -> None:
    result = _run_copy(tmp_path)
    assert result.returncode == 1
    assert ".env is missing" in result.stdout
    assert ".env.example" in result.stdout


def test_bad_line_stops_without_printing_value(tmp_path: Path) -> None:
    _write_env(tmp_path, f"SHEET_ID={SECRET}\nGOOGLE_APPLICATION_CREDENTIALS {SECRET}\n")
    result = _run_copy(tmp_path)
    assert result.returncode == 1
    assert "Line 2 of .env is not a KEY=VALUE line." in result.stdout
    assert SECRET not in result.stdout + result.stderr


def test_missing_venv_stops_without_printing_values(tmp_path: Path) -> None:
    _write_env(tmp_path, f"SHEET_ID={SECRET}\nGOOGLE_APPLICATION_CREDENTIALS={SECRET}\n")
    result = _run_copy(tmp_path)
    assert result.returncode == 1
    assert ".venv is missing" in result.stdout
    assert SECRET not in result.stdout + result.stderr
