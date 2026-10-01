"""End-to-end tests through load_data(FakeSheetsClient). Implements specs/001-data-source.md §10.

Each acceptance criterion is named in its test's docstring (AC-xx, see the tasks file).
"""

from datetime import date

import pandas as pd
import pytest

from conftest import (
    TODAY,
    FakeSheetsClient,
    add_column,
    append_row,
    clear_data_rows,
    drop_column,
    insert_blank_row,
    load_fixture,
    rename_header,
    serial,
    set_cell,
)
from shopify_dashboard import DataSourceError, LoadResult, load_data
from shopify_dashboard.errors import ErrorCategory
from shopify_dashboard.report import Severity

SPEC_9_COLUMNS = {
    "orders": ["order_id", "order_date", "customer_id", "sku", "product_name", "category",
               "quantity", "unit_price_cad", "discount_cad", "line_total_cad", "status",
               "sales_channel"],
    "products": ["sku", "product_name", "category", "price_cad", "unit_cost_cad", "inventory",
                 "margin_pct", "units_sold", "revenue_cad"],
    "customers": ["customer_id", "name", "email", "city", "province", "customer_since",
                  "order_count", "total_spent_cad"],
}  # fmt: skip


def load(tabs: dict, today: date = TODAY) -> LoadResult:
    return load_data(FakeSheetsClient(tabs), today=today)


def entries(result: LoadResult) -> list[tuple[str, int, str, str, str]]:
    return [(e.tab, e.row, e.column, e.reason, e.severity) for e in result.report.entries]


def order_ids(result: LoadResult) -> list[str]:
    return list(result.orders["order_id"])


def raises(tabs: dict, category: ErrorCategory) -> DataSourceError:
    with pytest.raises(DataSourceError) as info:
        load(tabs)
    assert info.value.category is category
    return info.value


# --- The base load ---------------------------------------------------------------------


def test_base_load(base_tabs: dict) -> None:
    result = load(base_tabs)
    assert (len(result.orders), len(result.products), len(result.customers)) == (8, 4, 3)
    assert result.report.entries == []
    assert {t: s.rows_dropped for t, s in result.report.summaries.items()} == {
        "Products": 0,
        "Customers": 0,
        "Orders": 0,
    }


def test_fetch_is_called_exactly_once(base_tabs: dict) -> None:
    """Spec §8: one batch read per load."""
    fake = FakeSheetsClient(base_tabs)
    load_data(fake, today=TODAY)
    assert fake.calls == 1


def test_columns_match_spec_9_in_order(base_tabs: dict) -> None:
    """AC-16."""
    result = load(base_tabs)
    for name, columns in SPEC_9_COLUMNS.items():
        assert list(getattr(result, name).columns) == columns


def test_dtypes(base_tabs: dict) -> None:
    result = load(base_tabs)
    orders, products, customers = result.orders, result.products, result.customers
    assert orders["order_id"].dtype == "string"
    assert orders["status"].dtype == "string"
    assert orders["quantity"].dtype == "int64"
    assert orders["unit_price_cad"].dtype == "float64"
    assert orders["order_date"].dtype == "datetime64[ns]"
    assert products["margin_pct"].dtype == "float64"
    assert products["units_sold"].dtype == "int64"
    assert customers["order_count"].dtype == "int64"
    assert customers["customer_since"].dtype == "datetime64[ns]"


def test_dates_are_normalised_to_midnight(base_tabs: dict) -> None:
    set_cell(base_tabs, "Orders", 2, "Order Date", serial(date(2026, 1, 10)) + 0.75)
    first = load(base_tabs).orders["order_date"].iloc[0]
    assert first == pd.Timestamp("2026-01-10")


def test_today_defaults_to_the_current_date(base_tabs: dict) -> None:
    """Spec §7.4: an order dated tomorrow is dropped when today is not passed."""
    tomorrow = date.fromordinal(date.today().toordinal() + 1)
    set_cell(base_tabs, "Orders", 2, "Order Date", serial(tomorrow))
    result = load_data(FakeSheetsClient(base_tabs))
    assert "#1001" not in order_ids(result)


def test_all_rows_dropped_still_gives_typed_empty_frames(base_tabs: dict) -> None:
    for row in range(2, 10):
        set_cell(base_tabs, "Orders", row, "Status", "Shipped")
    orders = load(base_tabs).orders
    assert orders.empty
    assert list(orders.columns) == SPEC_9_COLUMNS["orders"]
    assert orders["quantity"].dtype == "int64"
    assert orders["order_date"].dtype == "datetime64[ns]"


# --- Load-stopping errors --------------------------------------------------------------


def test_missing_status_column(base_tabs: dict) -> None:
    """AC-03."""
    drop_column(base_tabs, "Orders", "Status")
    err = raises(base_tabs, ErrorCategory.MISSING_COLUMN)
    assert "Orders" in str(err) and "Status" in str(err)


def test_missing_tab(base_tabs: dict) -> None:
    del base_tabs["Products"]
    assert "Products" in str(raises(base_tabs, ErrorCategory.MISSING_TAB))


def test_header_only_tab(base_tabs: dict) -> None:
    """AC-25."""
    clear_data_rows(base_tabs, "Customers")
    assert "Customers" in str(raises(base_tabs, ErrorCategory.EMPTY_TAB))


def test_duplicate_status_column(base_tabs: dict) -> None:
    """AC-26."""
    add_column(base_tabs, "Orders", "Status", "Fulfilled")
    err = raises(base_tabs, ErrorCategory.DUPLICATE_COLUMN)
    assert "Orders" in str(err) and "Status" in str(err)


def test_completely_empty_tab(base_tabs: dict) -> None:
    """AC-27."""
    base_tabs["Products"] = []
    assert "Products" in str(raises(base_tabs, ErrorCategory.EMPTY_TAB))


def test_client_errors_pass_through_unchanged(base_tabs: dict) -> None:
    error = DataSourceError(ErrorCategory.UNREACHABLE, "Could not reach the sheet.")
    with pytest.raises(DataSourceError) as info:
        load_data(FakeSheetsClient(base_tabs, error=error), today=TODAY)
    assert info.value is error


# --- Reading values --------------------------------------------------------------------


def test_discount_is_numeric_and_dash_or_blank_is_zero(base_tabs: dict) -> None:
    """AC-01: #1001 has 0 (the API value of a `-` display); #1003 has a blank cell."""
    result = load(base_tabs)
    discounts = dict(zip(result.orders["order_id"], result.orders["discount_cad"], strict=True))
    assert result.orders["discount_cad"].dtype == "float64"
    assert discounts["#1001"] == 0.0 and discounts["#1003"] == 0.0
    assert result.report.entries == []


def test_dates_load_and_impossible_date_is_dropped(base_tabs: dict) -> None:
    """AC-02."""
    set_cell(base_tabs, "Orders", 3, "Order Date", "2026-02-30")
    result = load(base_tabs)
    assert result.customers["customer_since"].iloc[1] == pd.Timestamp("2025-03-15")  # ISO text
    assert "#1002" not in order_ids(result)
    assert entries(result) == [
        ("Orders", 3, "Order Date", "not a real calendar date", Severity.DROPPED)
    ]


def test_padded_status_header_loads(base_tabs: dict) -> None:
    """AC-04."""
    rename_header(base_tabs, "Orders", "Status", " Status ")
    result = load(base_tabs)
    assert result.report.entries == [] and len(result.orders) == 8


def test_extra_columns_are_ignored(base_tabs: dict) -> None:
    """AC-15."""
    add_column(base_tabs, "Orders", "Notes", "gift wrap")
    result = load(base_tabs)
    assert "notes" not in result.orders.columns and "Notes" not in result.orders.columns
    assert list(result.orders.columns) == SPEC_9_COLUMNS["orders"]


def test_blank_row_mid_tab_is_skipped(base_tabs: dict) -> None:
    """AC-20: same output, no entries, and later rows keep their real sheet row numbers."""
    baseline = load(load_fixture("base_valid.json"))
    insert_blank_row(base_tabs, "Orders", 3)
    result = load(base_tabs)
    pd.testing.assert_frame_equal(result.orders, baseline.orders)
    assert result.report.entries == []
    set_cell(base_tabs, "Orders", 10, "Status", "Shipped")  # #1008, sheet row 10 now
    assert entries(load(base_tabs))[0][1] == 10


def test_row_with_values_only_in_extra_columns_is_skipped(base_tabs: dict) -> None:
    """AC-28."""
    baseline = load(load_fixture("base_valid.json"))
    add_column(base_tabs, "Orders", "Notes")
    append_row(base_tabs, "Orders", {"Notes": "end of list"})
    result = load(base_tabs)
    pd.testing.assert_frame_equal(result.orders, baseline.orders)
    assert result.report.entries == []
    assert result.report.summaries["Orders"].rows_read == 8


# --- Row problems ----------------------------------------------------------------------


@pytest.mark.parametrize("status", ["Shipped", "fulfilled"])
def test_bad_status_drops_exactly_that_row(base_tabs: dict, status: str) -> None:
    """AC-05 (`Shipped`) and AC-06 (`fulfilled`)."""
    set_cell(base_tabs, "Orders", 4, "Status", status)
    result = load(base_tabs)
    assert order_ids(result) == ["#1001", "#1002", "#1004", "#1005", "#1006", "#1007", "#1008"]
    assert entries(result) == [("Orders", 4, "Status", "not an allowed value", Severity.DROPPED)]


def test_unknown_sku(base_tabs: dict) -> None:
    """AC-07."""
    set_cell(base_tabs, "Orders", 2, "SKU", "SKU-9999")
    assert entries(load(base_tabs)) == [("Orders", 2, "SKU", "SKU not found", Severity.DROPPED)]


def test_unknown_customer(base_tabs: dict) -> None:
    """AC-08."""
    set_cell(base_tabs, "Orders", 2, "Customer ID", "C-999")
    assert entries(load(base_tabs)) == [
        ("Orders", 2, "Customer ID", "Customer not found", Severity.DROPPED)
    ]


def test_bad_product_drops_its_orders(base_tabs: dict) -> None:
    """AC-09."""
    set_cell(base_tabs, "Products", 3, "Price (CAD)", 0)
    result = load(base_tabs)
    assert "SKU-0002" not in list(result.products["sku"])
    assert "SKU-0002" not in list(result.orders["sku"])
    assert [(t, r, reason) for t, r, _, reason, _ in entries(result)] == [
        ("Products", 3, "must be greater than 0"),
        ("Orders", 3, "SKU not found"),
        ("Orders", 7, "SKU not found"),
    ]


def test_duplicate_order_ids(base_tabs: dict) -> None:
    """AC-10."""
    set_cell(base_tabs, "Orders", 3, "Order ID", "#1001")
    result = load(base_tabs)
    assert "#1001" not in order_ids(result) and len(result.orders) == 6
    assert entries(result) == [
        ("Orders", 2, "Order ID", "duplicate Order ID", Severity.DROPPED),
        ("Orders", 3, "Order ID", "duplicate Order ID", Severity.DROPPED),
    ]


@pytest.mark.parametrize(
    ("header", "value"),
    [("Quantity", 0), ("Quantity", 2.5), ("Discount (CAD)", 40.5)],
)
def test_quantity_and_discount_breaks_are_dropped(
    base_tabs: dict, header: str, value: object
) -> None:
    """AC-11: #1001 is 2 x 20.00, so a 40.50 discount is too large."""
    set_cell(base_tabs, "Orders", 2, header, value)
    result = load(base_tabs)
    assert "#1001" not in order_ids(result)
    assert [(r, c) for _, r, c, _, _ in entries(result)] == [(2, header)]


def test_line_total_005_off(base_tabs: dict) -> None:
    """AC-12: kept, one warning, and the output holds the recomputed value."""
    set_cell(base_tabs, "Orders", 2, "Line Total (CAD)", 40.05)
    result = load(base_tabs)
    assert result.orders["line_total_cad"].iloc[0] == 40.0
    assert entries(result) == [
        (
            "Orders",
            2,
            "Line Total (CAD)",
            "differs from Quantity × Unit Price − Discount",
            Severity.WARNING,
        )
    ]
    assert result.report.summaries["Orders"].rows_dropped == 0


def test_line_total_0005_off(base_tabs: dict) -> None:
    """AC-13."""
    set_cell(base_tabs, "Orders", 2, "Line Total (CAD)", 40.005)
    assert load(base_tabs).report.entries == []


def test_recomputed_stats_match_the_sheet(base_tabs: dict) -> None:
    """AC-14: the fixture's sheet values were worked out by hand without Refunded orders."""
    result = load(base_tabs)
    products = result.products.set_index("sku")
    customers = result.customers.set_index("customer_id")
    assert dict(products["units_sold"]) == {
        "SKU-0001": 2, "SKU-0002": 3, "SKU-0003": 7, "SKU-0004": 2,
    }  # fmt: skip
    assert dict(products["revenue_cad"]) == pytest.approx(
        {"SKU-0001": 40.0, "SKU-0002": 95.0, "SKU-0003": 123.5, "SKU-0004": 70.0}
    )
    assert dict(customers["order_count"]) == {"C-101": 2, "C-102": 2, "C-103": 2}
    assert dict(customers["total_spent_cad"]) == pytest.approx(
        {"C-101": 94.0, "C-102": 100.0, "C-103": 134.5}
    )


def test_future_order_date(base_tabs: dict) -> None:
    """AC-17."""
    set_cell(base_tabs, "Orders", 2, "Order Date", serial(date(2026, 6, 2)))
    set_cell(base_tabs, "Orders", 3, "Order Date", serial(TODAY))
    result = load(base_tabs)
    assert "#1001" not in order_ids(result) and "#1002" in order_ids(result)
    assert entries(result) == [
        ("Orders", 2, "Order Date", "must not be after today", Severity.DROPPED)
    ]


def test_order_before_customer_since(base_tabs: dict) -> None:
    """AC-18."""
    set_cell(base_tabs, "Orders", 5, "Order Date", serial(date(2025, 11, 1)))
    result = load(base_tabs)
    assert "#1004" in order_ids(result)
    assert entries(result) == [
        ("Orders", 5, "Order Date", "before the customer's Customer Since", Severity.WARNING)
    ]


def test_margin_for_price_20_cost_5(base_tabs: dict) -> None:
    """AC-19: SKU-0001."""
    products = load(base_tabs).products.set_index("sku")
    assert products.loc["SKU-0001", "margin_pct"] == 0.75


@pytest.mark.parametrize(("broken", "over"), [(6, True), (5, False)])
def test_drop_threshold(broken: int, over: bool) -> None:
    """AC-21."""
    tabs = load_fixture("threshold_100_orders.json")
    for row in range(2, 2 + broken):
        set_cell(tabs, "Orders", row, "Quantity", 0)
    summary = load(tabs).report.summaries["Orders"]
    assert (summary.rows_read, summary.rows_dropped) == (100, broken)
    assert summary.over_threshold is over


def test_invalid_email_is_masked_in_the_report(base_tabs: dict) -> None:
    """AC-22."""
    set_cell(base_tabs, "Customers", 2, "Email", "jane.example.com")
    result = load(base_tabs)
    (entry,) = [e for e in result.report.entries if e.tab == "Customers"]
    assert (entry.column, entry.value, entry.reason) == ("Email", "j***", "must contain @")
    assert "jane.example.com" not in repr(result.report)
    assert "C-101" not in list(result.customers["customer_id"])


def test_unreadable_calculated_cells(base_tabs: dict) -> None:
    """AC-29."""
    set_cell(base_tabs, "Orders", 3, "Product Name", "#N/A")
    set_cell(base_tabs, "Products", 2, "Units Sold", "lots")
    set_cell(base_tabs, "Orders", 2, "Line Total (CAD)", "#VALUE!")
    result = load(base_tabs)
    assert (len(result.orders), len(result.products)) == (8, 4)
    assert sorted(entries(result)) == sorted(
        [
            ("Orders", 3, "Product Name", "calculated value unreadable", Severity.WARNING),
            ("Products", 2, "Units Sold", "calculated value unreadable", Severity.WARNING),
            ("Orders", 2, "Line Total (CAD)", "calculated value unreadable", Severity.WARNING),
        ]
    )
    assert all(s.rows_dropped == 0 for s in result.report.summaries.values())
    assert result.orders["product_name"].iloc[1] == "Canvas Tote"
    assert result.orders["line_total_cad"].iloc[0] == 40.0
    assert result.products["units_sold"].iloc[0] == 2
