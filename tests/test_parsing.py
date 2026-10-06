"""Tests for parsing.py. Implements specs/001-data-source.md §2, §3 and §7.1."""

from datetime import date

import pytest

from conftest import (
    TODAY,
    add_column,
    append_row,
    clear_data_rows,
    drop_column,
    insert_blank_row,
    rename_header,
    serial,
    set_cell,
    sheet_date,
)
from shopify_dashboard.errors import DataSourceError, ErrorCategory
from shopify_dashboard.parsing import SheetDate, coerce_cell, parse_tabs
from shopify_dashboard.schema import COLUMNS, TABS, ColumnSpec


def spec(tab: str, header: str) -> ColumnSpec:
    (s,) = [c for c in COLUMNS[tab] if c.header == header]
    return s


DISCOUNT = spec("Orders", "Discount (CAD)")
QUANTITY = spec("Orders", "Quantity")
UNIT_PRICE = spec("Orders", "Unit Price (CAD)")
ORDER_DATE = spec("Orders", "Order Date")
CUSTOMER_SINCE = spec("Customers", "Customer Since")
DATE_COLUMNS = [ORDER_DATE, CUSTOMER_SINCE]
ORDER_ID = spec("Orders", "Order ID")
STATUS = spec("Orders", "Status")
LINE_TOTAL = spec("Orders", "Line Total (CAD)")
NAME = spec("Customers", "Name")


# --- parse_tabs: structure -------------------------------------------------------------


def test_base_parses_with_sheet_row_numbers(base_tabs: dict) -> None:
    parsed = parse_tabs(base_tabs)
    assert list(parsed) == list(TABS)
    orders = parsed["Orders"]
    assert [r.sheet_row for r in orders.rows] == list(range(2, 10))
    assert orders.rows[0].cells["Order ID"] == "#1001"
    assert set(orders.rows[0].cells) == {c.header for c in COLUMNS["Orders"]}


def test_missing_tab_raises(base_tabs: dict) -> None:
    del base_tabs["Customers"]
    with pytest.raises(DataSourceError, match="Customers") as info:
        parse_tabs(base_tabs)
    assert info.value.category is ErrorCategory.MISSING_TAB


def test_missing_status_column_raises(base_tabs: dict) -> None:
    """AC-03."""
    drop_column(base_tabs, "Orders", "Status")
    with pytest.raises(DataSourceError) as info:
        parse_tabs(base_tabs)
    assert info.value.category is ErrorCategory.MISSING_COLUMN
    assert "Orders" in str(info.value)
    assert "Status" in str(info.value)


def test_renamed_column_counts_as_missing(base_tabs: dict) -> None:
    rename_header(base_tabs, "Products", "Price (CAD)", "Price")
    with pytest.raises(DataSourceError, match="Price \\(CAD\\)") as info:
        parse_tabs(base_tabs)
    assert info.value.category is ErrorCategory.MISSING_COLUMN


def test_header_with_extra_spaces_loads(base_tabs: dict) -> None:
    """AC-04."""
    rename_header(base_tabs, "Orders", "Status", " Status ")
    orders = parse_tabs(base_tabs)["Orders"]
    assert orders.rows[0].cells["Status"] == "Fulfilled"


def test_header_case_must_match(base_tabs: dict) -> None:
    rename_header(base_tabs, "Orders", "Status", "status")
    with pytest.raises(DataSourceError) as info:
        parse_tabs(base_tabs)
    assert info.value.category is ErrorCategory.MISSING_COLUMN


def test_extra_columns_are_ignored(base_tabs: dict) -> None:
    """AC-15."""
    add_column(base_tabs, "Orders", "Notes", "gift wrap")
    orders = parse_tabs(base_tabs)["Orders"]
    assert "Notes" not in orders.rows[0].cells


def test_column_order_does_not_matter(base_tabs: dict) -> None:
    for row in base_tabs["Products"]:
        row.reverse()
    products = parse_tabs(base_tabs)["Products"]
    assert products.rows[0].cells["SKU"] == "SKU-0001"


def test_blank_row_mid_tab_is_skipped(base_tabs: dict) -> None:
    """AC-20: skipped, and later rows keep their real sheet row numbers."""
    insert_blank_row(base_tabs, "Orders", 3)
    orders = parse_tabs(base_tabs)["Orders"]
    assert len(orders.rows) == 8
    assert [r.sheet_row for r in orders.rows] == [2, 4, 5, 6, 7, 8, 9, 10]
    assert orders.rows[1].cells["Order ID"] == "#1002"


@pytest.mark.parametrize("blank", [[], ["", "  ", ""], [None, ""]])
def test_whitespace_short_and_none_rows_are_blank(base_tabs: dict, blank: list) -> None:
    base_tabs["Orders"].insert(2, blank)
    assert len(parse_tabs(base_tabs)["Orders"].rows) == 8


def test_trailing_blank_rows_are_dropped(base_tabs: dict) -> None:
    base_tabs["Orders"] += [[], [""] * 12]
    assert len(parse_tabs(base_tabs)["Orders"].rows) == 8


def test_short_rows_are_padded_with_blanks(base_tabs: dict) -> None:
    """The Sheets API omits trailing empty cells, so rows can be shorter than the header."""
    base_tabs["Orders"][1] = base_tabs["Orders"][1][:3]
    cells = parse_tabs(base_tabs)["Orders"].rows[0].cells
    assert cells["Customer ID"] == "C-101"
    assert cells["Sales Channel"] == ""


def test_header_only_tab_raises_empty_tab(base_tabs: dict) -> None:
    """AC-25."""
    clear_data_rows(base_tabs, "Customers")
    with pytest.raises(DataSourceError, match="Customers") as info:
        parse_tabs(base_tabs)
    assert info.value.category is ErrorCategory.EMPTY_TAB


def test_only_blank_rows_raises_empty_tab(base_tabs: dict) -> None:
    clear_data_rows(base_tabs, "Products")
    base_tabs["Products"] += [[], [""] * 9]
    with pytest.raises(DataSourceError) as info:
        parse_tabs(base_tabs)
    assert info.value.category is ErrorCategory.EMPTY_TAB


def test_repeated_status_header_raises_duplicate_column(base_tabs: dict) -> None:
    """AC-26."""
    add_column(base_tabs, "Orders", "Status", "Fulfilled")
    with pytest.raises(DataSourceError) as info:
        parse_tabs(base_tabs)
    assert info.value.category is ErrorCategory.DUPLICATE_COLUMN
    assert "Orders" in str(info.value)
    assert "Status" in str(info.value)


def test_repeat_after_trimming_is_a_duplicate(base_tabs: dict) -> None:
    add_column(base_tabs, "Products", " SKU ", "SKU-0001")
    with pytest.raises(DataSourceError, match="SKU") as info:
        parse_tabs(base_tabs)
    assert info.value.category is ErrorCategory.DUPLICATE_COLUMN


def test_repeated_extra_or_blank_headers_are_ignored(base_tabs: dict) -> None:
    for header in ("Notes", "Notes", "", ""):
        add_column(base_tabs, "Orders", header)
    assert len(parse_tabs(base_tabs)["Orders"].rows) == 8


def test_missing_column_is_reported_before_duplicate(base_tabs: dict) -> None:
    add_column(base_tabs, "Orders", "SKU")
    drop_column(base_tabs, "Orders", "Status")
    with pytest.raises(DataSourceError) as info:
        parse_tabs(base_tabs)
    assert info.value.category is ErrorCategory.MISSING_COLUMN


@pytest.mark.parametrize("rows", [[], [[]], [[""] * 9, [], ["  "]]])
def test_completely_empty_tab_raises_empty_tab(base_tabs: dict, rows: list) -> None:
    """AC-27: no header row (or only blank rows) is empty_tab, not missing_column."""
    base_tabs["Products"] = rows
    with pytest.raises(DataSourceError, match="Products") as info:
        parse_tabs(base_tabs)
    assert info.value.category is ErrorCategory.EMPTY_TAB


def test_row_with_values_only_in_extra_columns_is_skipped(base_tabs: dict) -> None:
    """AC-28: skipped, and later rows keep their real sheet row numbers."""
    add_column(base_tabs, "Orders", "Notes")
    insert_blank_row(base_tabs, "Orders", 3)
    set_cell(base_tabs, "Orders", 3, "Notes", "call customer")
    append_row(base_tabs, "Orders", {"Notes": "end of list"})
    orders = parse_tabs(base_tabs)["Orders"]
    assert [r.sheet_row for r in orders.rows] == [2, 4, 5, 6, 7, 8, 9, 10]


def test_extra_columns_only_tab_counts_as_no_data(base_tabs: dict) -> None:
    clear_data_rows(base_tabs, "Customers")
    add_column(base_tabs, "Customers", "Notes")
    append_row(base_tabs, "Customers", {"Notes": "x"})
    with pytest.raises(DataSourceError) as info:
        parse_tabs(base_tabs)
    assert info.value.category is ErrorCategory.EMPTY_TAB


def test_parse_does_not_mutate_input(base_tabs: dict) -> None:
    rename_header(base_tabs, "Orders", "Status", " Status ")
    before = repr(base_tabs)
    parse_tabs(base_tabs)
    assert repr(base_tabs) == before


# --- coerce_cell -----------------------------------------------------------------------


def test_text_is_trimmed() -> None:
    assert coerce_cell("  Jane Doe ", NAME) == ("Jane Doe", None)
    assert coerce_cell(" Fulfilled ", STATUS) == ("Fulfilled", None)


def test_number_in_text_column_becomes_text() -> None:
    assert coerce_cell(1984, NAME) == ("1984", None)


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_required_cell(blank: object) -> None:
    assert coerce_cell(blank, ORDER_ID) == (None, "required")
    assert coerce_cell(blank, QUANTITY) == (None, "required")
    assert coerce_cell(blank, ORDER_DATE) == (None, "required")


@pytest.mark.parametrize("blank", ["", "  ", None])
def test_blank_discount_is_zero(blank: object) -> None:
    """AC-01."""
    assert coerce_cell(blank, DISCOUNT) == (0.0, None)


def test_zero_discount_stays_zero() -> None:
    """AC-01: the sheet's `-` is the number 0 in unformatted values."""
    value, reason = coerce_cell(0, DISCOUNT)
    assert (value, reason) == (0.0, None)
    assert isinstance(value, float)


def test_blank_calculated_cell_is_not_a_rule_break() -> None:
    """D2."""
    assert coerce_cell("", LINE_TOTAL) == (None, None)
    assert coerce_cell("", spec("Orders", "Product Name")) == (None, None)


UNREADABLE = "calculated value unreadable"


@pytest.mark.parametrize(
    ("column", "value"),
    [
        (spec("Products", "Units Sold"), "lots"),
        (spec("Products", "Units Sold"), 2.5),
        (spec("Customers", "Orders"), True),
        (LINE_TOTAL, "#VALUE!"),
        (LINE_TOTAL, "40"),
        (spec("Orders", "Product Name"), "#N/A"),
        (spec("Orders", "Category"), " #REF! "),
        (spec("Products", "Margin %"), "#DIV/0!"),
    ],
)
def test_unreadable_calculated_values(column: ColumnSpec, value: object) -> None:
    """D16: Sheets error values in any calculated column; wrong type in number ones."""
    assert coerce_cell(value, column) == (None, UNREADABLE)


@pytest.mark.parametrize("error", ["#N/A", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NUM!",
                                   "#NULL!", "#ERROR!"])  # fmt: skip
def test_every_sheets_error_value_is_unreadable(error: str) -> None:
    assert coerce_cell(error, spec("Orders", "Product Name")) == (None, UNREADABLE)


def test_readable_calculated_values_pass() -> None:
    assert coerce_cell(" Classic Tee ", spec("Orders", "Product Name")) == ("Classic Tee", None)
    assert coerce_cell(40, LINE_TOTAL) == (40.0, None)


def test_error_value_in_non_calculated_text_column_is_text() -> None:
    assert coerce_cell("#N/A", NAME) == ("#N/A", None)


def test_decimal_accepts_int_and_float() -> None:
    assert coerce_cell(45, UNIT_PRICE) == (45.0, None)
    assert coerce_cell(32.5, UNIT_PRICE) == (32.5, None)
    assert isinstance(coerce_cell(45, UNIT_PRICE)[0], float)


@pytest.mark.parametrize("bad", ["45", "$45.00", "-", True])
def test_decimal_rejects_text_and_bool(bad: object) -> None:
    assert coerce_cell(bad, UNIT_PRICE) == (None, "must be a number")


def test_integer_accepts_whole_numbers() -> None:
    assert coerce_cell(3, QUANTITY) == (3, None)
    value, _ = coerce_cell(2.0, QUANTITY)
    assert value == 2
    assert isinstance(value, int)


def test_integer_rejects_fraction() -> None:
    """AC-11: 2.5 is not a whole number."""
    assert coerce_cell(2.5, QUANTITY) == (None, "must be a whole number")


@pytest.mark.parametrize("bad", ["45", "3", False])
def test_integer_rejects_text_and_bool(bad: object) -> None:
    assert coerce_cell(bad, QUANTITY) == (None, "must be a number")


@pytest.mark.parametrize("column", DATE_COLUMNS, ids=lambda c: c.header)
def test_date_from_serial_number(column: ColumnSpec) -> None:
    """AC-02 and AC-34: a date-formatted cell's serial number (epoch 1899-12-30) loads."""
    assert coerce_cell(sheet_date(TODAY), column) == (TODAY, None)
    assert coerce_cell(SheetDate(46032), column) == (date(2026, 1, 10), None)


@pytest.mark.parametrize("column", DATE_COLUMNS, ids=lambda c: c.header)
def test_date_serial_with_time_keeps_the_date(column: ColumnSpec) -> None:
    """AC-34: a date-time cell keeps only the date."""
    assert coerce_cell(SheetDate(serial(TODAY) + 0.75), column) == (TODAY, None)


@pytest.mark.parametrize("column", DATE_COLUMNS, ids=lambda c: c.header)
def test_date_from_iso_text(column: ColumnSpec) -> None:
    """AC-02, and the serial <-> ISO pair from the base fixture (C-102)."""
    assert coerce_cell(" 2025-03-15 ", column) == (date(2025, 3, 15), None)
    assert coerce_cell(sheet_date(date(2025, 3, 15)), column) == (date(2025, 3, 15), None)


@pytest.mark.parametrize("column", DATE_COLUMNS, ids=lambda c: c.header)
@pytest.mark.parametrize("plain", [45, 46032, serial(TODAY) + 0.75, 0])
def test_plain_number_in_a_date_column_is_rejected(column: ColumnSpec, plain: object) -> None:
    """AC-33: a number from a cell not formatted as a date is not a date value (spec §3)."""
    assert coerce_cell(plain, column) == (None, "must be a date (YYYY-MM-DD)")


def test_date_formatted_number_outside_a_date_column_is_a_plain_number() -> None:
    """D27: the date format matters only in date columns; other columns behave as before."""
    assert coerce_cell(SheetDate(3), QUANTITY) == (3, None)
    assert coerce_cell(SheetDate(45), UNIT_PRICE) == (45.0, None)
    assert coerce_cell(SheetDate(1984), NAME) == ("1984", None)


def test_impossible_iso_date_is_rejected() -> None:
    """AC-02."""
    assert coerce_cell("2026-02-30", ORDER_DATE) == (None, "not a real calendar date")


@pytest.mark.parametrize("bad", ["2026/06/01", "20260601", "June 1, 2026", "2026-6-1", True])
def test_non_iso_date_text_is_rejected(bad: object) -> None:
    assert coerce_cell(bad, ORDER_DATE) == (None, "must be a date (YYYY-MM-DD)")


def test_set_cell_round_trip_through_parse(base_tabs: dict) -> None:
    set_cell(base_tabs, "Orders", 4, "Discount (CAD)", "")
    cells = parse_tabs(base_tabs)["Orders"].rows[2].cells
    assert cells["Discount (CAD)"] == ""
