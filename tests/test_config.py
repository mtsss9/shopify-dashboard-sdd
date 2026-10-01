"""Tests for config.py. Implements specs/001-data-source.md §2 and §7.1 (AC-23, AC-30)."""

import dataclasses
import re
from pathlib import Path

import pytest

from shopify_dashboard.config import PLACEHOLDERS, Config, load_config
from shopify_dashboard.errors import DataSourceError, ErrorCategory

FAKE_ID = "fake-sheet-id-123"
FAKE_PATH = "C:/fake/dir/service-key.json"
VALID = {"SHEET_ID": FAKE_ID, "GOOGLE_APPLICATION_CREDENTIALS": FAKE_PATH}
ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / ".env.example"
VARS = ("SHEET_ID", "GOOGLE_APPLICATION_CREDENTIALS")


def parse_template(path: Path) -> dict[str, str]:
    """KEY=VALUE lines of an env template, ignoring comments and blank lines."""
    pairs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*([^#=\s][^=]*)=(.*)$", line)
        if match:
            pairs[match[1].strip()] = match[2].strip()
    return pairs


def test_loads_both_values() -> None:
    cfg = load_config(VALID)
    assert cfg.sheet_id == FAKE_ID
    assert cfg.credentials_path == FAKE_PATH


def test_reads_os_environ_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHEET_ID", FAKE_ID)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", FAKE_PATH)
    assert load_config() == Config(FAKE_ID, FAKE_PATH)


def test_unset_sheet_id_raises_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-23."""
    monkeypatch.delenv("SHEET_ID", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", FAKE_PATH)
    with pytest.raises(DataSourceError) as info:
        load_config()
    assert info.value.category is ErrorCategory.CONFIG
    assert "SHEET_ID" in str(info.value)
    assert FAKE_PATH not in str(info.value)


def test_unset_credentials_raises_config_naming_variable_only() -> None:
    with pytest.raises(DataSourceError) as info:
        load_config({"SHEET_ID": FAKE_ID})
    assert info.value.category is ErrorCategory.CONFIG
    assert "GOOGLE_APPLICATION_CREDENTIALS" in str(info.value)
    assert FAKE_ID not in str(info.value)


@pytest.mark.parametrize("blank", ["", "   "])
@pytest.mark.parametrize("name", ["SHEET_ID", "GOOGLE_APPLICATION_CREDENTIALS"])
def test_blank_value_counts_as_unset(name: str, blank: str) -> None:
    with pytest.raises(DataSourceError, match=name) as info:
        load_config({**VALID, name: blank})
    assert info.value.category is ErrorCategory.CONFIG


def test_both_unset_names_sheet_id_first() -> None:
    with pytest.raises(DataSourceError, match="SHEET_ID"):
        load_config({})


def test_values_are_trimmed() -> None:
    cfg = load_config({"SHEET_ID": f" {FAKE_ID}\n", "GOOGLE_APPLICATION_CREDENTIALS": FAKE_PATH})
    assert cfg.sheet_id == FAKE_ID


def test_repr_and_str_hide_both_values() -> None:
    cfg = load_config(VALID)
    for text in (repr(cfg), str(cfg), f"{cfg}", repr([cfg])):
        assert FAKE_ID not in text
        assert FAKE_PATH not in text


def test_config_is_frozen() -> None:
    cfg = load_config(VALID)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.sheet_id = "other"  # type: ignore[misc]


# --- AC-30: the env template is never read; its placeholders are rejected (D26) ----------


def test_template_in_working_directory_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1. A template file next to the app never supplies configuration."""
    (tmp_path / ".env.example").write_text(
        "SHEET_ID=from-template\nGOOGLE_APPLICATION_CREDENTIALS=from-template-path\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    for name in VARS:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(DataSourceError) as info:
        load_config()
    assert info.value.category is ErrorCategory.CONFIG

    monkeypatch.setenv("SHEET_ID", FAKE_ID)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", FAKE_PATH)
    assert load_config() == Config(FAKE_ID, FAKE_PATH)


def test_committed_template_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """2. From the project root, the real template supplies nothing either."""
    assert TEMPLATE.is_file()
    monkeypatch.chdir(ROOT)
    for name in VARS:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(DataSourceError) as info:
        load_config()
    assert info.value.category is ErrorCategory.CONFIG


@pytest.mark.parametrize("name", VARS)
@pytest.mark.parametrize("pad", ["", "  "])
def test_placeholder_values_are_rejected(name: str, pad: str) -> None:
    """3. A value still equal to its template placeholder raises config (AC-30)."""
    placeholder = PLACEHOLDERS[name]
    with pytest.raises(DataSourceError) as info:
        load_config({**VALID, name: f"{pad}{placeholder}{pad}"})
    assert info.value.category is ErrorCategory.CONFIG
    assert name in str(info.value)
    assert placeholder not in str(info.value)


def test_placeholders_match_the_committed_template() -> None:
    """4. The constants in config.py can never drift from the template."""
    assert parse_template(TEMPLATE) == PLACEHOLDERS


def test_no_source_file_loads_env_files() -> None:
    """5. Configuration comes only from the environment: no dotenv, no template file."""
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+dotenv\b", text, re.M), path
        assert "env.example" not in text, path
