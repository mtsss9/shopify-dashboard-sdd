"""Tests for filters.py. Implements specs/003-dashboard-ui.md §6.4.

Covers T2 in specs/003-dashboard-ui.tasks.md: AC-26 to AC-35 and AC-37 at unit level.
No Streamlit is used.
"""

from datetime import date

import pandas as pd
import pytest

from conftest import TODAY, FakeSheetsClient
from shopify_dashboard import filters, load_data


@pytest.fixture
def frames(base_tabs) -> dict[str, pd.DataFrame]:
    """The loader's DataFrames for the valid base fixture (8 orders, 4 products, 3 customers)."""
    result = load_data(FakeSheetsClient(base_tabs), today=TODAY)
    return {"Orders": result.orders, "Products": result.products, "Customers": result.customers}


def _orders(dates: list[str]) -> pd.DataFrame:
    """A small Orders-like frame with one order per date, in the given order."""
    return pd.DataFrame(
        {
            "order_id": [f"#{1000 + i}" for i in range(len(dates))],
            "order_date": pd.to_datetime(dates),
        }
    )


def _ids(df: pd.DataFrame) -> list[str]:
    return df["order_id"].tolist()


# Options (AC-29)


def test_options_distinct_sorted(frames: dict[str, pd.DataFrame]) -> None:
    orders = frames["Orders"]
    assert filters.options(orders, "category") == ["Accessories", "Apparel", "Home", "Outdoor"]
    assert filters.options(orders, "status") == ["Fulfilled", "Refunded", "Unfulfilled"]
    assert filters.options(orders, "sales_channel") == [
        "Instagram",
        "Online Store",
        "POS",
        "Shop App",
    ]
    assert filters.options(frames["Customers"], "province") == ["BC", "ON", "QC"]


def test_options_only_values_present() -> None:
    """An allowed value absent from the data (here Outdoor, Home) is not offered."""
    df = pd.DataFrame({"category": ["Apparel", "Accessories", "Apparel"]}, dtype="string")
    assert filters.options(df, "category") == ["Accessories", "Apparel"]


def test_options_skip_missing_and_empty_frame() -> None:
    df = pd.DataFrame({"province": ["ON", pd.NA, "BC"]}, dtype="string")
    assert filters.options(df, "province") == ["BC", "ON"]
    assert filters.options(df.iloc[0:0], "province") == []


def test_options_are_plain_str() -> None:
    df = pd.DataFrame({"status": ["Fulfilled"]}, dtype="string")
    assert all(type(v) is str for v in filters.options(df, "status"))


# Default date range (AC-30, decision U6)


def test_default_date_range(frames: dict[str, pd.DataFrame]) -> None:
    assert filters.default_date_range(frames["Orders"]) == (date(2026, 1, 10), date(2026, 5, 28))


def test_default_date_range_unsorted_input() -> None:
    df = _orders(["2026-03-01", "2026-01-15", "2026-04-30"])
    start, end = filters.default_date_range(df)
    assert (start, end) == (date(2026, 1, 15), date(2026, 4, 30))
    assert type(start) is date and type(end) is date


def test_default_date_range_empty() -> None:
    assert filters.default_date_range(_orders([])) is None


# Pruning selections after refresh (AC-32)


def test_prune_keeps_available_in_original_order() -> None:
    assert filters.prune_selection(["POS", "Instagram", "Shop App"], ["Instagram", "POS"]) == [
        "POS",
        "Instagram",
    ]


def test_prune_empty_cases() -> None:
    assert filters.prune_selection([], ["ON"]) == []
    assert filters.prune_selection(["ON"], []) == []


# Value filters (AC-27, AC-28, AC-34, AC-35)


@pytest.mark.parametrize(
    ("column", "selected", "expected"),
    [
        ("category", ["Home"], ["#1003", "#1008"]),
        ("status", ["Refunded"], ["#1004", "#1007"]),
        ("sales_channel", ["POS", "Shop App"], ["#1002", "#1003", "#1006", "#1008"]),
    ],
)
def test_filter_values_keeps_matching(
    frames: dict[str, pd.DataFrame], column: str, selected: list[str], expected: list[str]
) -> None:
    """AC-27."""
    assert _ids(filters.filter_values(frames["Orders"], column, selected)) == expected


@pytest.mark.parametrize("column", ["category", "status", "sales_channel"])
def test_empty_selection_keeps_every_row(frames: dict[str, pd.DataFrame], column: str) -> None:
    """AC-28."""
    orders = frames["Orders"]
    pd.testing.assert_frame_equal(filters.filter_values(orders, column, []), orders)


def test_selection_absent_from_data_keeps_no_rows(frames: dict[str, pd.DataFrame]) -> None:
    assert filters.filter_values(frames["Orders"], "status", ["Unknown"]).empty


def test_filter_products_by_category(frames: dict[str, pd.DataFrame]) -> None:
    """AC-34."""
    kept = filters.filter_products(frames["Products"], ["Home", "Outdoor"])
    assert kept["sku"].tolist() == ["SKU-0003", "SKU-0004"]
    pd.testing.assert_frame_equal(
        filters.filter_products(frames["Products"], []), frames["Products"]
    )


def test_filter_customers_by_province(frames: dict[str, pd.DataFrame]) -> None:
    """AC-35 (and AC-28 for Province)."""
    kept = filters.filter_customers(frames["Customers"], ["QC"])
    assert kept["customer_id"].tolist() == ["C-102"]
    pd.testing.assert_frame_equal(
        filters.filter_customers(frames["Customers"], []), frames["Customers"]
    )


# Date range (AC-26, AC-31)


def test_date_range_inclusive_both_ends() -> None:
    """AC-26: orders on the start and end dates are kept; outside dates are dropped."""
    df = _orders(["2026-02-28", "2026-03-01", "2026-03-15", "2026-03-31", "2026-04-01"])
    kept = filters.filter_date_range(df, "order_date", date(2026, 3, 1), date(2026, 3, 31))
    assert _ids(kept) == ["#1001", "#1002", "#1003"]


def test_date_range_single_day() -> None:
    df = _orders(["2026-03-01", "2026-03-02"])
    kept = filters.filter_date_range(df, "order_date", date(2026, 3, 2), date(2026, 3, 2))
    assert _ids(kept) == ["#1001"]


def test_start_after_end_keeps_no_rows() -> None:
    """AC-31 (filter side; the warning text is shown by the app in T6)."""
    df = _orders(["2026-03-01", "2026-03-02"])
    kept = filters.filter_date_range(df, "order_date", date(2026, 3, 2), date(2026, 3, 1))
    assert kept.empty
    assert list(kept.columns) == list(df.columns)


# Combined Orders filter (AC-33)


def test_filter_orders_and_combination(frames: dict[str, pd.DataFrame]) -> None:
    """AC-33: two filters keep only rows matching both."""
    kept = filters.filter_orders(
        frames["Orders"],
        start=date(2026, 1, 1),
        end=date(2026, 12, 31),
        categories=["Outdoor"],
        statuses=["Fulfilled"],
        channels=[],
    )
    assert _ids(kept) == ["#1005"]


def test_filter_orders_all_criteria(frames: dict[str, pd.DataFrame]) -> None:
    kept = filters.filter_orders(
        frames["Orders"],
        start=date(2026, 2, 5),
        end=date(2026, 4, 18),
        categories=["Accessories", "Home"],
        statuses=["Fulfilled", "Unfulfilled"],
        channels=["POS"],
    )
    assert _ids(kept) == ["#1003", "#1006"]


def test_filter_orders_defaults_keep_every_row(frames: dict[str, pd.DataFrame]) -> None:
    orders = frames["Orders"]
    start, end = filters.default_date_range(orders)
    kept = filters.filter_orders(orders, start, end, [], [], [])
    pd.testing.assert_frame_equal(kept, orders)


def test_filter_orders_start_after_end(frames: dict[str, pd.DataFrame]) -> None:
    kept = filters.filter_orders(frames["Orders"], date(2026, 5, 1), date(2026, 4, 1), [], [], [])
    assert kept.empty


# New DataFrame, input unchanged (AC-37)


def test_filters_return_new_frame_and_leave_input_unchanged(
    frames: dict[str, pd.DataFrame],
) -> None:
    calls = [
        ("Orders", lambda df: filters.filter_values(df, "status", [])),
        ("Orders", lambda df: filters.filter_values(df, "status", ["Refunded"])),
        ("Orders", lambda df: filters.filter_date_range(df, "order_date", TODAY, TODAY)),
        ("Orders", lambda df: filters.filter_orders(df, TODAY, date(2026, 1, 1), [], [], [])),
        ("Products", lambda df: filters.filter_products(df, [])),
        ("Customers", lambda df: filters.filter_customers(df, ["ON"])),
    ]
    for tab, call in calls:
        df = frames[tab]
        before = df.copy(deep=True)
        out = call(df)
        assert out is not df
        pd.testing.assert_frame_equal(df, before)


def test_result_is_independent_of_input(frames: dict[str, pd.DataFrame]) -> None:
    """Changing the result never reaches the loader's DataFrame."""
    orders = frames["Orders"]
    before = orders.copy(deep=True)
    out = filters.filter_values(orders, "status", [])
    out.loc[out.index[0], "status"] = "Changed"
    pd.testing.assert_frame_equal(orders, before)
