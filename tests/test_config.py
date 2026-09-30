"""Tests for config.py. Implements specs/001-data-source.md §2 and §7.1 (AC-23)."""

import dataclasses

import pytest

from shopify_dashboard.config import Config, load_config
from shopify_dashboard.errors import DataSourceError, ErrorCategory

FAKE_ID = "fake-sheet-id-123"
FAKE_PATH = "C:/fake/dir/service-key.json"
VALID = {"SHEET_ID": FAKE_ID, "GOOGLE_APPLICATION_CREDENTIALS": FAKE_PATH}


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
