"""AppTest runs of app.py. Implements specs/003-dashboard-ui.md §1–4, §6.2 and §6.3–6.4.

Covers T5 in specs/003-dashboard-ui.tasks.md: AC-03 (button), AC-05, AC-06, AC-07,
AC-10, AC-11 to AC-14; and T6: AC-09, AC-17 to AC-21, AC-23, AC-25, AC-29 to AC-32,
AC-36. ``load_data`` is patched, so the real sheet is never called.
"""

import dataclasses
import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from conftest import TODAY, FakeSheetsClient, set_cell
from shopify_dashboard import DataSourceError, LoadResult, display, load_data
from shopify_dashboard.config import CREDENTIALS_VAR, PLACEHOLDERS, SHEET_ID_VAR, load_config
from shopify_dashboard.errors import ErrorCategory
from shopify_dashboard.report import TabSummary, mask_email

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


# Table tabs (§6.3, §6.4, T6)

TABLE_TABS = {"Orders": 0, "Products": 1, "Customers": 2}
ROWS = {"Orders": 8, "Products": 4, "Customers": 3}


def _table(at: AppTest, tab: str) -> pd.DataFrame:
    return at.tabs[TABLE_TABS[tab]].dataframe[0].value


def _count(at: AppTest, tab: str) -> str:
    return at.tabs[TABLE_TABS[tab]].markdown[0].value


def _column_config(at: AppTest, tab: str) -> dict[str, dict]:
    return json.loads(at.tabs[TABLE_TABS[tab]].dataframe[0].proto.columns)


@pytest.mark.parametrize("tab", list(TABLE_TABS))
def test_unfiltered_count(result: LoadResult, tab: str) -> None:
    """AC-17: "Showing Y of Y rows" with the loader's row count."""
    at = _run(MagicMock(return_value=result))
    assert _count(at, tab) == f"Showing {ROWS[tab]} of {ROWS[tab]} rows"
    assert len(_table(at, tab)) == ROWS[tab]


@pytest.mark.parametrize(
    ("tab", "layout"),
    [
        ("Orders", ["markdown", "date_input", "date_input"] + ["multiselect"] * 3),
        ("Products", ["markdown", "multiselect"]),
        ("Customers", ["markdown", "multiselect"]),
    ],
)
def test_tab_layout_count_filters_table(result: LoadResult, tab: str, layout: list[str]) -> None:
    """§6.3: row count, then the filters, then the table."""
    at = _run(MagicMock(return_value=result))
    types = [node.type for node in at.tabs[TABLE_TABS[tab]].children.values()]
    assert types == [*layout, "dataframe"]


@pytest.mark.parametrize("tab", list(TABLE_TABS))
def test_number_column_config(result: LoadResult, tab: str) -> None:
    """AC-09, AC-19, AC-20: money and Margin % are number columns with their formats."""
    at = _run(MagicMock(return_value=result))
    config = _column_config(at, tab)
    expected = display.number_formats(tab)
    assert expected
    for header, fmt in expected.items():
        assert config[header]["type_config"] == {"type": "number", "format": fmt}
        assert pd.api.types.is_float_dtype(_table(at, tab)[header])


def test_money_and_margin_values_reach_table(result: LoadResult) -> None:
    """Values stay numeric; Margin % is the fraction × 100."""
    at = _run(MagicMock(return_value=result))
    products = _table(at, "Products")
    assert products["Price (CAD)"].tolist() == result.products["price_cad"].tolist()
    assert products["Margin %"].tolist() == pytest.approx(
        (result.products["margin_pct"] * 100).tolist()
    )
    assert _column_config(at, "Products")["Margin %"]["type_config"]["format"] == "%.1f%%"
    assert _column_config(at, "Orders")["Line Total (CAD)"]["type_config"]["format"] == "$%,.2f"


@pytest.mark.parametrize("tab", list(TABLE_TABS))
def test_sheet_headers_and_index_hidden(result: LoadResult, tab: str) -> None:
    """AC-21."""
    at = _run(MagicMock(return_value=result))
    assert list(_table(at, tab).columns) == list(
        display.table_view(tab, getattr(result, tab.lower())).columns
    )
    assert not any("_" in c for c in _table(at, tab).columns)
    assert _column_config(at, tab)["_index"] == {"hidden": True}


def test_customers_email_masked(result: LoadResult) -> None:
    """AC-23."""
    at = _run(MagicMock(return_value=result))
    emails = _table(at, "Customers")["Email"].tolist()
    assert emails == [mask_email(e) for e in result.customers["email"]]
    for full in result.customers["email"]:
        assert full not in emails


def test_refunded_orders_listed(result: LoadResult) -> None:
    """AC-25."""
    at = _run(MagicMock(return_value=result))
    orders = _table(at, "Orders")
    assert orders.loc[orders["Status"] == "Refunded", "Order ID"].tolist() == ["#1004", "#1007"]


def test_filter_options_from_data(result: LoadResult) -> None:
    """AC-29 in the app: options are the values present, sorted A–Z."""
    at = _run(MagicMock(return_value=result))
    assert at.multiselect(key="orders_status").options == ["Fulfilled", "Refunded", "Unfulfilled"]
    assert at.multiselect(key="customers_province").options == ["BC", "ON", "QC"]


def test_default_date_range_in_app(result: LoadResult) -> None:
    """AC-30."""
    at = _run(MagicMock(return_value=result))
    assert at.date_input(key="orders_start").value == date(2026, 1, 10)
    assert at.date_input(key="orders_end").value == date(2026, 5, 28)


def test_filtered_count_and_rows(result: LoadResult) -> None:
    """AC-18: X is the filtered row count."""
    loader = MagicMock(return_value=result)
    at = _run(loader)
    at.multiselect(key="orders_status").set_value(["Refunded"])
    _rerun(at, loader)
    assert _count(at, "Orders") == "Showing 2 of 8 rows"
    assert _table(at, "Orders")["Order ID"].tolist() == ["#1004", "#1007"]


def test_start_after_end_warning(result: LoadResult) -> None:
    """AC-31: no rows and the warning text."""
    loader = MagicMock(return_value=result)
    at = _run(loader)
    at.date_input(key="orders_start").set_value(date(2026, 5, 1))
    at.date_input(key="orders_end").set_value(date(2026, 4, 1))
    _rerun(at, loader)
    orders_tab = at.tabs[TABLE_TABS["Orders"]]
    assert [w.value for w in orders_tab.warning] == ["Start date is after end date."]
    assert _count(at, "Orders") == "Showing 0 of 8 rows"
    assert _table(at, "Orders").empty


def test_no_date_warning_by_default(result: LoadResult) -> None:
    at = _run(MagicMock(return_value=result))
    assert len(at.tabs[TABLE_TABS["Orders"]].warning) == 0


def test_filtering_one_tab_leaves_others(result: LoadResult) -> None:
    """AC-36."""
    loader = MagicMock(return_value=result)
    at = _run(loader)
    at.multiselect(key="products_category").set_value(["Home"])
    at.multiselect(key="customers_province").set_value(["QC"])
    _rerun(at, loader)
    assert _count(at, "Products") == "Showing 1 of 4 rows"
    assert _count(at, "Customers") == "Showing 1 of 3 rows"
    assert _count(at, "Orders") == "Showing 8 of 8 rows"
    assert sorted(_table(at, "Orders")["Category"].unique()) == [
        "Accessories",
        "Apparel",
        "Home",
        "Outdoor",
    ]


def test_refresh_keeps_selections_and_prunes_vanished(base_tabs, result: LoadResult) -> None:
    """AC-32: after Refresh, selections are kept; a value no longer in the data is removed."""
    for row in (5, 8):  # sheet rows of #1004 and #1007, the two Refunded orders
        set_cell(base_tabs, "Orders", row, "Status", "Fulfilled")
    reloaded = load_data(FakeSheetsClient(base_tabs), today=TODAY)
    loader = MagicMock(side_effect=[result, reloaded])
    at = _run(loader)
    at.multiselect(key="orders_status").set_value(["Refunded", "Fulfilled"])
    at.multiselect(key="customers_province").set_value(["QC"])
    at.date_input(key="orders_start").set_value(date(2026, 2, 1))
    _rerun(at, loader)
    _click_refresh(at, loader)
    assert loader.call_count == 2
    assert at.multiselect(key="orders_status").value == ["Fulfilled"]
    assert at.multiselect(key="orders_status").options == ["Fulfilled", "Unfulfilled"]
    assert at.multiselect(key="customers_province").value == ["QC"]
    assert at.date_input(key="orders_start").value == date(2026, 2, 1)
    assert _count(at, "Orders") == "Showing 6 of 8 rows"
    assert not at.exception


def test_empty_orders_tab(result: LoadResult) -> None:
    """Decision U6: 0 of 0, no options and no date pickers."""
    empty = dataclasses.replace(result, orders=result.orders.iloc[0:0])
    at = _run(MagicMock(return_value=empty))
    assert _count(at, "Orders") == "Showing 0 of 0 rows"
    assert len(at.tabs[TABLE_TABS["Orders"]].date_input) == 0
    assert at.multiselect(key="orders_status").options == []
    assert list(_table(at, "Orders").columns)[0] == "Order ID"
    assert not at.exception


def test_loader_frames_unchanged_by_app(result: LoadResult) -> None:
    """AC-24 in the app: displaying and filtering never change the loader's DataFrames."""
    before = {n: getattr(result, n).copy(deep=True) for n in ("orders", "products", "customers")}
    loader = MagicMock(return_value=result)
    at = _run(loader)
    at.multiselect(key="orders_status").set_value(["Refunded"])
    _rerun(at, loader)
    for name, frame in before.items():
        pd.testing.assert_frame_equal(getattr(result, name), frame)
