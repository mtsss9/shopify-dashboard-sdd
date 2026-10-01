"""Tests for validation.py. Implements specs/001-data-source.md §3, §5, §6 and §7.2."""

from datetime import date

import pytest

from conftest import set_cell
from shopify_dashboard.parsing import parse_tabs
from shopify_dashboard.report import ReportEntry, Severity
from shopify_dashboard.validation import validate_customers, validate_products


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
