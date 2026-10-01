"""Tests for errors.py. Implements specs/001-data-source.md §7.1."""

import pytest

from shopify_dashboard.errors import DataSourceError, ErrorCategory


def test_categories_match_spec_7_1() -> None:
    assert [c.value for c in ErrorCategory] == [
        "config",
        "auth",
        "unreachable",
        "missing_tab",
        "missing_column",
        "duplicate_column",
        "empty_tab",
    ]


def test_error_carries_category_and_message() -> None:
    err = DataSourceError(ErrorCategory.MISSING_COLUMN, "Orders is missing column Status")
    assert isinstance(err, Exception)
    assert err.category is ErrorCategory.MISSING_COLUMN
    assert err.message == "Orders is missing column Status"


def test_str_is_only_the_message() -> None:
    err = DataSourceError(ErrorCategory.AUTH, "Could not authenticate with Google.")
    assert str(err) == "Could not authenticate with Google."


def test_can_be_raised_and_caught() -> None:
    with pytest.raises(DataSourceError, match="Customers") as info:
        raise DataSourceError(ErrorCategory.EMPTY_TAB, "Customers has no data rows")
    assert info.value.category == "empty_tab"
