"""AppTest runs of app.py. Implements specs/003-dashboard-ui.md §1–4 and §6.2.

Covers T5 in specs/003-dashboard-ui.tasks.md: AC-03 (button), AC-05, AC-06, AC-07,
AC-10, AC-11 to AC-14. ``load_data`` is patched, so the real sheet is never called.
"""

import dataclasses
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from conftest import TODAY, FakeSheetsClient
from shopify_dashboard import DataSourceError, LoadResult, display, load_data
from shopify_dashboard.config import CREDENTIALS_VAR, PLACEHOLDERS, SHEET_ID_VAR, load_config
from shopify_dashboard.errors import ErrorCategory
from shopify_dashboard.report import TabSummary

APP = str(Path(__file__).parents[1] / "src" / "shopify_dashboard" / "app.py")
TIMEOUT = 30
TAB_LABELS = ["Orders", "Products", "Customers", "Data quality"]


@pytest.fixture(autouse=True)
def _fresh_cache() -> Iterator[None]:
    """The app's LoadCache lives in st.cache_resource; never share it between tests."""
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


@pytest.fixture
def result(base_tabs) -> LoadResult:
    """A clean LoadResult from the valid base fixture (no tab over threshold)."""
    return load_data(FakeSheetsClient(base_tabs), today=TODAY)


def _over_threshold(result: LoadResult) -> LoadResult:
    summaries = {**result.report.summaries, "Orders": TabSummary(100, 6)}
    report = dataclasses.replace(result.report, summaries=summaries)
    return dataclasses.replace(result, report=report)


def _run(loader: MagicMock) -> AppTest:
    """Run the app once with ``shopify_dashboard.load_data`` replaced by ``loader``."""
    at = AppTest.from_file(APP)
    with patch("shopify_dashboard.load_data", loader):
        return at.run(timeout=TIMEOUT)


def _rerun(at: AppTest, loader: MagicMock) -> AppTest:
    with patch("shopify_dashboard.load_data", loader):
        return at.run(timeout=TIMEOUT)


def _click_refresh(at: AppTest, loader: MagicMock) -> AppTest:
    with patch("shopify_dashboard.load_data", loader):
        return at.button[0].click().run(timeout=TIMEOUT)


def _layout(at: AppTest) -> list[str]:
    """Top-level element types, top to bottom."""
    return [node.type for node in at.main.children.values()]


# Layout (§6.2)


def test_title(result: LoadResult) -> None:
    """AC-11."""
    at = _run(MagicMock(return_value=result))
    assert [t.value for t in at.title] == ["Shopify Data Explorer"]


def test_layout_title_refresh_tabs(result: LoadResult) -> None:
    """AC-12, AC-13: title, then Refresh, then the four tabs in order; no banner."""
    at = _run(MagicMock(return_value=result))
    assert _layout(at) == ["title", "button", "tab_container"]
    assert [b.label for b in at.button] == ["Refresh data"]
    assert [t.label for t in at.tabs] == TAB_LABELS
    assert not at.exception


# Banner (§4, AC-07)


def test_banner_shown_when_over_threshold(result: LoadResult) -> None:
    at = _run(MagicMock(return_value=_over_threshold(result)))
    assert [w.value for w in at.warning] == ["Orders: 6.0% of rows were dropped"]
    assert _layout(at) == ["title", "button", "warning", "tab_container"]


def test_no_banner_when_none_over_threshold(result: LoadResult) -> None:
    at = _run(MagicMock(return_value=result))
    assert len(at.warning) == 0


# Error screen (§3, AC-05, AC-06, AC-14)


@pytest.mark.parametrize("category", list(ErrorCategory))
def test_error_screen_per_category(category: ErrorCategory) -> None:
    message = f"Problem in tab Orders, column Line Total (CAD) [{category}]."
    at = _run(MagicMock(side_effect=DataSourceError(category, message)))
    assert [e.value for e in at.error] == [
        display.error_text(display.ERROR_HEADINGS[category], message)
    ]
    assert _layout(at) == ["title", "button", "error"]
    assert [b.label for b in at.button] == ["Refresh data"]
    assert len(at.tabs) == 0
    assert not at.exception


@pytest.mark.parametrize(
    "env",
    [
        {},
        {SHEET_ID_VAR: "  "},
        {SHEET_ID_VAR: PLACEHOLDERS[SHEET_ID_VAR]},
        {SHEET_ID_VAR: "real-sheet-id-123", CREDENTIALS_VAR: PLACEHOLDERS[CREDENTIALS_VAR]},
    ],
)
def test_config_errors_share_heading_and_hide_values(env: dict[str, str]) -> None:
    """AC-10: unset and placeholder both show "Configuration problem"; no value shown."""
    with pytest.raises(DataSourceError) as raised:
        load_config(env)
    error = raised.value
    at = _run(MagicMock(side_effect=error))
    text = at.error[0].value
    assert text == display.error_text("Configuration problem", error.message)
    assert SHEET_ID_VAR in error.message or CREDENTIALS_VAR in error.message
    for value in env.values():
        if value.strip():
            assert value not in text
            assert display.escape_markdown(value) not in text


# Loading, caching and Refresh (§1, §2, AC-03)


def test_reruns_within_ttl_load_once(result: LoadResult) -> None:
    loader = MagicMock(return_value=result)
    at = _run(loader)
    _rerun(at, loader)
    assert loader.call_count == 1


def test_refresh_calls_loader_again(result: LoadResult) -> None:
    """AC-03: pressing Refresh reloads within the 5 minutes."""
    loader = MagicMock(return_value=result)
    at = _run(loader)
    _click_refresh(at, loader)
    assert loader.call_count == 2
    assert [t.label for t in at.tabs] == TAB_LABELS


def test_failed_load_retried_on_next_interaction(result: LoadResult) -> None:
    """§1: a failure is not cached; the next rerun loads again and shows the tabs."""
    error = DataSourceError(ErrorCategory.UNREACHABLE, "Could not reach the sheet.")
    loader = MagicMock(side_effect=[error, result])
    at = _run(loader)
    assert len(at.error) == 1
    _rerun(at, loader)
    assert loader.call_count == 2
    assert len(at.error) == 0
    assert [t.label for t in at.tabs] == TAB_LABELS


def test_refresh_from_error_screen(result: LoadResult) -> None:
    """AC-06: Refresh is on the error screen and pressing it tries again."""
    error = DataSourceError(ErrorCategory.AUTH, "Could not sign in.")
    loader = MagicMock(side_effect=[error, result])
    at = _run(loader)
    _click_refresh(at, loader)
    assert loader.call_count == 2
    assert _layout(at) == ["title", "button", "tab_container"]


def test_refresh_to_error_shows_error_screen(result: LoadResult) -> None:
    error = DataSourceError(ErrorCategory.UNREACHABLE, "Could not reach the sheet.")
    loader = MagicMock(side_effect=[result, error])
    at = _run(loader)
    _click_refresh(at, loader)
    assert _layout(at) == ["title", "button", "error"]
