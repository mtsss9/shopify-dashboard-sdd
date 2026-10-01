"""Tests for validation.py. Implements specs/001-data-source.md §3, §5, §6 and §7.2."""

from datetime import date

import pytest

from conftest import TODAY, load_fixture, serial, set_cell
from shopify_dashboard.parsing import parse_tabs
from shopify_dashboard.report import ReportEntry, Severity
from shopify_dashboard.validation import (
    find_duplicate_keys,
    validate_all,
    validate_customers,
    validate_orders,
    validate_products,
)


def products(tabs: dict) -> tuple[list, list[ReportEntry]]:
    return validate_products(parse_tabs(tabs)["Products"])


def customers(tabs: dict) -> tuple[list, list[ReportEntry]]:
    return validate_customers(parse_tabs(tabs)["Customers"])


def reasons(entries: list[ReportEntry]) -> list[tuple[int, str, str]]:
    return [(e.row, e.column, e.reason) for e in entries]


# --- Products --------------------------------------------------------------------------


def test_base_products_are_all_valid(base_tabs: dict) -> None:
    rows, entries = products(base_tabs)
    assert entries == []
    assert [r.cells["SKU"] for r in rows] == ["SKU-0001", "SKU-0002", "SKU-0003", "SKU-0004"]
    first = rows[0].cells
    assert first["Price (CAD)"] == 20.0 and isinstance(first["Price (CAD)"], float)
    assert first["Inventory"] == 120 and isinstance(first["Inventory"], int)
    assert rows[0].sheet_row == 2


def test_price_zero_drops_the_product(base_tabs: dict) -> None:
    """AC-09 (product side): SKU-0002 is sheet row 3."""
    set_cell(base_tabs, "Products", 3, "Price (CAD)", 0)
    rows, entries = products(base_tabs)
    assert "SKU-0002" not in [r.cells["SKU"] for r in rows]
    assert entries == [
        ReportEntry("Products", 3, "Price (CAD)", 0, "must be greater than 0", Severity.DROPPED)
    ]


@pytest.mark.parametrize(
    ("header", "value", "reason"),
    [
        ("SKU", "SKU-12", "invalid format"),
        ("SKU", "sku-0001", "invalid format"),
        ("Product Name", "", "required"),
        ("Category", "apparel", "not an allowed value"),
        ("Category", "Toys", "not an allowed value"),
        ("Price (CAD)", -5, "must be greater than 0"),
        ("Price (CAD)", "45", "must be a number"),
        ("Unit Cost (CAD)", -0.01, "must be 0 or more"),
        ("Inventory", -1, "must be 0 or more"),
        ("Inventory", 2.5, "must be a whole number"),
    ],
)
def test_product_rule_breaks(base_tabs: dict, header: str, value: object, reason: str) -> None:
    set_cell(base_tabs, "Products", 2, header, value)
    rows, entries = products(base_tabs)
    assert len(rows) == 3
    assert reasons(entries) == [(2, header, reason)]
    assert entries[0].value == value


@pytest.mark.parametrize(
    ("header", "value"),
    [("Unit Cost (CAD)", 0), ("Inventory", 0), ("Category", " Home "), ("Price (CAD)", 0.01)],
)
def test_product_boundaries_are_valid(base_tabs: dict, header: str, value: object) -> None:
    set_cell(base_tabs, "Products", 2, header, value)
    rows, entries = products(base_tabs)
    assert entries == []
    assert len(rows) == 4


def test_blank_calculated_product_cells_are_kept(base_tabs: dict) -> None:
    """D2: blank calculated cells are not a rule break; the value is None."""
    for header in ("Margin %", "Units Sold", "Revenue (CAD)"):
        set_cell(base_tabs, "Products", 2, header, "")
    rows, entries = products(base_tabs)
    assert entries == []
    assert rows[0].cells["Margin %"] is None


def test_several_breaks_give_one_entry_each_and_one_drop(base_tabs: dict) -> None:
    set_cell(base_tabs, "Products", 4, "Category", "Food")
    set_cell(base_tabs, "Products", 4, "Price (CAD)", 0)
    rows, entries = products(base_tabs)
    assert len(rows) == 3
    assert reasons(entries) == [
        (4, "Category", "not an allowed value"),
        (4, "Price (CAD)", "must be greater than 0"),
    ]


def test_values_are_trimmed_in_valid_rows(base_tabs: dict) -> None:
    set_cell(base_tabs, "Products", 2, "Product Name", "  Classic Tee  ")
    rows, _ = products(base_tabs)
    assert rows[0].cells["Product Name"] == "Classic Tee"


# --- Customers -------------------------------------------------------------------------


def test_base_customers_are_all_valid(base_tabs: dict) -> None:
    rows, entries = customers(base_tabs)
    assert entries == []
    assert [r.cells["Customer ID"] for r in rows] == ["C-101", "C-102", "C-103"]
    # C-102's Customer Since is ISO text in the fixture; C-101's is a serial number.
    assert rows[1].cells["Customer Since"] == date(2025, 3, 15)
    assert rows[0].cells["Customer Since"] == date(2025, 1, 15)


def test_invalid_email_is_dropped_and_masked(base_tabs: dict) -> None:
    """AC-22."""
    set_cell(base_tabs, "Customers", 2, "Email", "jane.example.com")
    rows, entries = customers(base_tabs)
    assert [r.cells["Customer ID"] for r in rows] == ["C-102", "C-103"]
    assert entries == [
        ReportEntry("Customers", 2, "Email", "j***", "must contain @", Severity.DROPPED)
    ]
    assert "jane.example.com" not in repr(entries)


@pytest.mark.parametrize(
    ("header", "value", "reason"),
    [
        ("Customer ID", "C101", "invalid format"),
        ("Customer ID", "c-101", "invalid format"),
        ("Name", "  ", "required"),
        ("Email", "", "required"),
        ("Province", "Ontario", "not an allowed value"),
        ("Province", "on", "not an allowed value"),
        ("Customer Since", "2026-02-30", "not a real calendar date"),
        ("Customer Since", "15/01/2025", "must be a date (YYYY-MM-DD)"),
    ],
)
def test_customer_rule_breaks(base_tabs: dict, header: str, value: object, reason: str) -> None:
    set_cell(base_tabs, "Customers", 3, header, value)
    rows, entries = customers(base_tabs)
    assert len(rows) == 2
    assert reasons(entries) == [(3, header, reason)]


def test_email_with_at_and_padded_province_are_valid(base_tabs: dict) -> None:
    set_cell(base_tabs, "Customers", 2, "Email", " a@b ")
    set_cell(base_tabs, "Customers", 2, "Province", " YT ")
    set_cell(base_tabs, "Customers", 2, "City", 1867)
    rows, entries = customers(base_tabs)
    assert entries == []
    assert rows[0].cells["Province"] == "YT"
    assert rows[0].cells["City"] == "1867"


def test_valid_rows_never_hold_report_masking(base_tabs: dict) -> None:
    """Masking applies to the report only; valid rows keep the real email for output."""
    rows, _ = customers(base_tabs)
    assert rows[0].cells["Email"] == "jane@example.com"


# --- Unreadable calculated cells (spec §3.1, D16, AC-29) -------------------------------


@pytest.mark.parametrize(
    ("tab", "row", "header", "value"),
    [
        ("Products", 2, "Units Sold", "lots"),
        ("Products", 3, "Margin %", "#DIV/0!"),
        ("Products", 4, "Revenue (CAD)", " #REF! "),
        ("Customers", 2, "Orders", 1.5),
        ("Customers", 3, "Total Spent (CAD)", "#N/A"),
    ],
)
def test_unreadable_calculated_cell_is_a_warning(
    base_tabs: dict, tab: str, row: int, header: str, value: object
) -> None:
    """AC-29: the row is kept, the value is treated as missing, one warning is recorded."""
    set_cell(base_tabs, tab, row, header, value)
    rows, entries = products(base_tabs) if tab == "Products" else customers(base_tabs)
    assert len(rows) == (4 if tab == "Products" else 3)
    assert entries == [
        ReportEntry(tab, row, header, value, "calculated value unreadable", Severity.WARNING)
    ]
    (kept,) = [r for r in rows if r.sheet_row == row]
    assert kept.cells[header] is None


def test_unreadable_warning_and_real_break_in_one_row(base_tabs: dict) -> None:
    set_cell(base_tabs, "Products", 2, "Units Sold", "#N/A")
    set_cell(base_tabs, "Products", 2, "Price (CAD)", 0)
    rows, entries = products(base_tabs)
    assert len(rows) == 3
    assert [(e.column, e.severity) for e in entries] == [
        ("Price (CAD)", Severity.DROPPED),
        ("Units Sold", Severity.WARNING),
    ]


def test_error_value_in_a_non_calculated_column_is_plain_text(base_tabs: dict) -> None:
    set_cell(base_tabs, "Customers", 2, "Name", "#N/A")
    rows, entries = customers(base_tabs)
    assert entries == []
    assert rows[0].cells["Name"] == "#N/A"


# --- Orders (T7) -----------------------------------------------------------------------


def orders(tabs: dict, today: date = TODAY) -> tuple[list, list[ReportEntry]]:
    parsed = parse_tabs(tabs)
    valid_products, _ = validate_products(parsed["Products"])
    valid_customers, _ = validate_customers(parsed["Customers"])
    return validate_orders(parsed["Orders"], valid_products, valid_customers, today)


def kept_ids(rows: list) -> list[str]:
    return [r.cells["Order ID"] for r in rows]


def test_base_orders_are_all_valid(base_tabs: dict) -> None:
    rows, entries = orders(base_tabs)
    assert entries == []
    assert len(rows) == 8
    first = rows[0].cells
    assert first["Order Date"] == date(2026, 1, 10)
    assert first["Quantity"] == 2 and first["Discount (CAD)"] == 0.0
    assert rows[2].cells["Discount (CAD)"] == 0.0  # blank in the fixture


@pytest.mark.parametrize("status", ["Shipped", "fulfilled"])
def test_bad_status_drops_exactly_that_row(base_tabs: dict, status: str) -> None:
    """AC-05, AC-06."""
    set_cell(base_tabs, "Orders", 4, "Status", status)
    rows, entries = orders(base_tabs)
    assert "#1003" not in kept_ids(rows) and len(rows) == 7
    assert reasons(entries) == [(4, "Status", "not an allowed value")]


def test_unknown_sku(base_tabs: dict) -> None:
    """AC-07."""
    set_cell(base_tabs, "Orders", 2, "SKU", "SKU-9999")
    rows, entries = orders(base_tabs)
    assert len(rows) == 7
    assert reasons(entries) == [(2, "SKU", "SKU not found")]


def test_unknown_customer(base_tabs: dict) -> None:
    """AC-08."""
    set_cell(base_tabs, "Orders", 3, "Customer ID", "C-999")
    rows, entries = orders(base_tabs)
    assert len(rows) == 7
    assert reasons(entries) == [(3, "Customer ID", "Customer not found")]


def test_bad_sku_format_is_not_also_reported_as_not_found(base_tabs: dict) -> None:
    set_cell(base_tabs, "Orders", 2, "SKU", "SKU-1")
    _, entries = orders(base_tabs)
    assert reasons(entries) == [(2, "SKU", "invalid format")]


@pytest.mark.parametrize(
    ("header", "value", "reason"),
    [
        ("Quantity", 0, "must be 1 or more"),  # AC-11
        ("Quantity", 2.5, "must be a whole number"),  # AC-11
        ("Unit Price (CAD)", 0, "must be greater than 0"),
        ("Discount (CAD)", -1, "must be 0 or more"),
        ("Discount (CAD)", 40.5, "must not exceed Quantity × Unit Price"),  # AC-11
        ("Order ID", "1001", "invalid format"),
        ("Sales Channel", "Amazon", "not an allowed value"),
    ],
)
def test_order_rule_breaks(base_tabs: dict, header: str, value: object, reason: str) -> None:
    set_cell(base_tabs, "Orders", 2, header, value)  # #1001: 2 x 20.00
    rows, entries = orders(base_tabs)
    assert "#1001" not in kept_ids(rows)
    assert reasons(entries) == [(2, header, reason)]


@pytest.mark.parametrize("discount", [40, 40.005])
def test_discount_up_to_the_line_value_is_allowed(base_tabs: dict, discount: float) -> None:
    """Spec §4 with the 0.01 tolerance (§3): 2 x 20.00 = 40.00."""
    set_cell(base_tabs, "Orders", 2, "Discount (CAD)", discount)
    set_cell(base_tabs, "Orders", 2, "Line Total (CAD)", 0)
    rows, entries = orders(base_tabs)
    assert entries == [] and len(rows) == 8


def test_line_total_005_off_is_a_warning(base_tabs: dict) -> None:
    """AC-12: kept, one warning."""
    set_cell(base_tabs, "Orders", 2, "Line Total (CAD)", 40.05)
    rows, entries = orders(base_tabs)
    assert len(rows) == 8
    assert entries == [
        ReportEntry(
            "Orders",
            2,
            "Line Total (CAD)",
            40.05,
            "differs from Quantity × Unit Price − Discount",
            Severity.WARNING,
        )
    ]


def test_line_total_0005_off_is_not_reported(base_tabs: dict) -> None:
    """AC-13."""
    set_cell(base_tabs, "Orders", 2, "Line Total (CAD)", 40.005)
    assert orders(base_tabs)[1] == []


def test_blank_line_total_gives_no_warning(base_tabs: dict) -> None:
    """D2."""
    set_cell(base_tabs, "Orders", 2, "Line Total (CAD)", "")
    rows, entries = orders(base_tabs)
    assert entries == [] and len(rows) == 8


def test_unreadable_line_total_gives_only_the_unreadable_warning(base_tabs: dict) -> None:
    """AC-29 (Orders side)."""
    set_cell(base_tabs, "Orders", 2, "Line Total (CAD)", "#VALUE!")
    rows, entries = orders(base_tabs)
    assert len(rows) == 8
    assert [(e.column, e.reason, e.severity) for e in entries] == [
        ("Line Total (CAD)", "calculated value unreadable", Severity.WARNING)
    ]


@pytest.mark.parametrize("header", ["Product Name", "Category"])
def test_unreadable_lookup_columns_are_warnings(base_tabs: dict, header: str) -> None:
    """AC-29: Product Name and Category in Orders are calculated too."""
    set_cell(base_tabs, "Orders", 3, header, "#N/A")
    rows, entries = orders(base_tabs)
    assert len(rows) == 8
    assert reasons(entries) == [(3, header, "calculated value unreadable")]


def test_sheet_product_name_mismatch_is_ignored(base_tabs: dict) -> None:
    """D3."""
    set_cell(base_tabs, "Orders", 2, "Product Name", "Something Else")
    set_cell(base_tabs, "Orders", 2, "Category", "Home")
    assert orders(base_tabs)[1] == []


def test_future_order_date_is_dropped_and_today_loads(base_tabs: dict) -> None:
    """AC-17: today is 2026-06-01."""
    set_cell(base_tabs, "Orders", 2, "Order Date", serial(date(2026, 6, 2)))
    set_cell(base_tabs, "Orders", 3, "Order Date", serial(TODAY))
    rows, entries = orders(base_tabs)
    assert "#1001" not in kept_ids(rows) and "#1002" in kept_ids(rows)
    assert reasons(entries) == [(2, "Order Date", "must not be after today")]


def test_order_before_customer_since_is_a_warning(base_tabs: dict) -> None:
    """AC-18: #1004 (row 5) belongs to C-103, customer since 2025-11-02."""
    set_cell(base_tabs, "Orders", 5, "Order Date", serial(date(2025, 11, 1)))
    rows, entries = orders(base_tabs)
    assert len(rows) == 8
    assert [(e.row, e.column, e.reason, e.severity) for e in entries] == [
        (5, "Order Date", "before the customer's Customer Since", Severity.WARNING)
    ]


def test_order_on_customer_since_day_is_fine(base_tabs: dict) -> None:
    set_cell(base_tabs, "Orders", 5, "Order Date", serial(date(2025, 11, 2)))
    assert orders(base_tabs)[1] == []


def test_dropped_rows_get_no_cross_check_warnings(base_tabs: dict) -> None:
    set_cell(base_tabs, "Orders", 2, "Status", "Shipped")
    set_cell(base_tabs, "Orders", 2, "Line Total (CAD)", 99)
    _, entries = orders(base_tabs)
    assert reasons(entries) == [(2, "Status", "not an allowed value")]


# --- Duplicates and validate_all (T7) --------------------------------------------------


def test_find_duplicate_keys_reports_every_row(base_tabs: dict) -> None:
    set_cell(base_tabs, "Orders", 3, "Order ID", " #1001 ")
    entries = find_duplicate_keys(parse_tabs(base_tabs)["Orders"], "Order ID")
    assert reasons(entries) == [
        (2, "Order ID", "duplicate Order ID"),
        (3, "Order ID", "duplicate Order ID"),
    ]
    assert all(e.severity is Severity.DROPPED for e in entries)


def test_blank_keys_are_not_duplicates(base_tabs: dict) -> None:
    set_cell(base_tabs, "Orders", 2, "Order ID", "")
    set_cell(base_tabs, "Orders", 3, "Order ID", "")
    assert find_duplicate_keys(parse_tabs(base_tabs)["Orders"], "Order ID") == []


def test_base_validate_all(base_tabs: dict) -> None:
    valid, report = validate_all(parse_tabs(base_tabs), TODAY)
    assert {t: len(rows) for t, rows in valid.items()} == {
        "Products": 4,
        "Customers": 3,
        "Orders": 8,
    }
    assert report.entries == []
    assert {t: (s.rows_read, s.rows_dropped) for t, s in report.summaries.items()} == {
        "Products": (4, 0),
        "Customers": (3, 0),
        "Orders": (8, 0),
    }


def test_duplicate_order_ids_are_both_dropped(base_tabs: dict) -> None:
    """AC-10."""
    set_cell(base_tabs, "Orders", 3, "Order ID", "#1001")
    valid, report = validate_all(parse_tabs(base_tabs), TODAY)
    assert len(valid["Orders"]) == 6
    assert reasons(report.entries) == [
        (2, "Order ID", "duplicate Order ID"),
        (3, "Order ID", "duplicate Order ID"),
    ]
    assert report.summaries["Orders"].rows_dropped == 2


def test_duplicates_are_checked_before_other_rules(base_tabs: dict) -> None:
    """D1: the duplicate with a bad Status is reported only as a duplicate."""
    set_cell(base_tabs, "Orders", 3, "Order ID", "#1001")
    set_cell(base_tabs, "Orders", 3, "Status", "Shipped")
    _, report = validate_all(parse_tabs(base_tabs), TODAY)
    assert [e.reason for e in report.entries] == ["duplicate Order ID"] * 2


def test_bad_product_cascades_to_its_orders(base_tabs: dict) -> None:
    """AC-09: SKU-0002 (Products row 3) is used by #1002 (row 3) and #1006 (row 7)."""
    set_cell(base_tabs, "Products", 3, "Price (CAD)", 0)
    valid, report = validate_all(parse_tabs(base_tabs), TODAY)
    assert "SKU-0002" not in [r.cells["SKU"] for r in valid["Products"]]
    assert kept_ids(valid["Orders"]) == ["#1001", "#1003", "#1004", "#1005", "#1007", "#1008"]
    assert [(e.tab, e.row, e.reason) for e in report.entries] == [
        ("Products", 3, "must be greater than 0"),
        ("Orders", 3, "SKU not found"),
        ("Orders", 7, "SKU not found"),
    ]


def test_duplicate_customer_cascades_to_orders(base_tabs: dict) -> None:
    set_cell(base_tabs, "Customers", 4, "Customer ID", "C-101")
    valid, report = validate_all(parse_tabs(base_tabs), TODAY)
    assert [r.cells["Customer ID"] for r in valid["Customers"]] == ["C-102"]
    assert {r.cells["Customer ID"] for r in valid["Orders"]} == {"C-102"}
    assert report.summaries["Customers"].rows_dropped == 2


def test_warnings_do_not_count_as_dropped(base_tabs: dict) -> None:
    set_cell(base_tabs, "Orders", 2, "Line Total (CAD)", 41)
    set_cell(base_tabs, "Orders", 3, "Product Name", "#N/A")
    _, report = validate_all(parse_tabs(base_tabs), TODAY)
    assert len(report.warnings()) == 2
    assert report.summaries["Orders"].rows_dropped == 0


def test_a_row_breaking_two_rules_counts_once(base_tabs: dict) -> None:
    set_cell(base_tabs, "Orders", 2, "Status", "Shipped")
    set_cell(base_tabs, "Orders", 2, "Quantity", 0)
    _, report = validate_all(parse_tabs(base_tabs), TODAY)
    assert len(report.dropped()) == 2
    assert report.summaries["Orders"].rows_dropped == 1


@pytest.mark.parametrize(("broken", "over"), [(6, True), (5, False)])
def test_threshold_with_100_orders(broken: int, over: bool) -> None:
    """AC-21 through validate_all: break `broken` of 100 orders."""
    tabs = load_fixture("threshold_100_orders.json")
    for row in range(2, 2 + broken):
        set_cell(tabs, "Orders", row, "Status", "Shipped")
    _, report = validate_all(parse_tabs(tabs), TODAY)
    summary = report.summaries["Orders"]
    assert (summary.rows_read, summary.rows_dropped) == (100, broken)
    assert summary.over_threshold is over
