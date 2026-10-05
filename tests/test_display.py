"""Tests for display.py. Implements specs/003-dashboard-ui.md §3, §5 and §6.3.

Covers T1 in specs/003-dashboard-ui.tasks.md: AC-05 (headings), AC-09, AC-17 (count
text), AC-19 to AC-24 at unit level. Rendered text comes from Streamlit's frontend, so
money and Margin % are checked through their format strings and numeric values (plan U11).
"""

import pandas as pd
import pytest

from conftest import TODAY, FakeSheetsClient
from shopify_dashboard import display, load_data
from shopify_dashboard.errors import ErrorCategory
from shopify_dashboard.schema import COLUMNS


@pytest.fixture
def frames(base_tabs) -> dict[str, pd.DataFrame]:
    """The loader's DataFrames for the valid base fixture."""
    result = load_data(FakeSheetsClient(base_tabs), today=TODAY)
    return {"Orders": result.orders, "Products": result.products, "Customers": result.customers}


# §3 error headings


def test_every_error_category_has_a_heading() -> None:
    assert set(display.ERROR_HEADINGS) == set(ErrorCategory)


@pytest.mark.parametrize(
    ("category", "heading"),
    [
        (ErrorCategory.CONFIG, "Configuration problem"),
        (ErrorCategory.AUTH, "Could not sign in to Google Sheets"),
        (ErrorCategory.UNREACHABLE, "Could not reach the Google Sheet"),
        (ErrorCategory.MISSING_TAB, "Sheet tab missing"),
        (ErrorCategory.MISSING_COLUMN, "Column missing"),
        (ErrorCategory.DUPLICATE_COLUMN, "Duplicate column"),
        (ErrorCategory.EMPTY_TAB, "Sheet tab is empty"),
    ],
)
def test_error_heading_text(category: ErrorCategory, heading: str) -> None:
    assert display.ERROR_HEADINGS[category] == heading


# §5 and §6.3 number formats (U11)


def test_format_strings() -> None:
    assert display.MONEY_FORMAT == "$%,.2f"
    assert display.PCT_FORMAT == "%.1f%%"


def test_money_columns_match_spec() -> None:
    assert display.MONEY_COLUMNS == {
        "Orders": ("unit_price_cad", "discount_cad", "line_total_cad"),
        "Products": ("price_cad", "unit_cost_cad", "revenue_cad"),
        "Customers": ("total_spent_cad",),
    }


@pytest.mark.parametrize(
    ("tab", "expected"),
    [
        (
            "Orders",
            {
                "Unit Price (CAD)": "$%,.2f",
                "Discount (CAD)": "$%,.2f",
                "Line Total (CAD)": "$%,.2f",
            },
        ),
        (
            "Products",
            {
                "Price (CAD)": "$%,.2f",
                "Unit Cost (CAD)": "$%,.2f",
                "Revenue (CAD)": "$%,.2f",
                "Margin %": "%.1f%%",
            },
        ),
        ("Customers", {"Total Spent (CAD)": "$%,.2f"}),
    ],
)
def test_number_formats_per_tab(tab: str, expected: dict[str, str]) -> None:
    assert display.number_formats(tab) == expected


@pytest.mark.parametrize("tab", ["Orders", "Products", "Customers"])
def test_number_formats_name_shown_headers(tab: str, frames: dict[str, pd.DataFrame]) -> None:
    shown = display.table_view(tab, frames[tab])
    assert set(display.number_formats(tab)) <= set(shown.columns)


def test_money_stays_numeric_and_unrounded() -> None:
    """AC-09: 1234.5 and 69.5 reach the table as numbers; Streamlit adds `$` and 2 decimals."""
    df = pd.DataFrame(
        {"customer_id": ["C-1", "C-2", "C-3"], "total_spent_cad": [1234.5, 69.5, 10.005]}
    )
    shown = display.table_view("Customers", df)
    assert pd.api.types.is_float_dtype(shown["Total Spent (CAD)"])
    assert shown["Total Spent (CAD)"].tolist() == [1234.5, 69.5, 10.005]


@pytest.mark.parametrize("tab", ["Orders", "Products", "Customers"])
def test_all_money_columns_numeric(tab: str, frames: dict[str, pd.DataFrame]) -> None:
    """AC-19 unit level: every §6.3 money column is numeric and equals the loader's value."""
    shown = display.table_view(tab, frames[tab])
    headers = {s.name: s.header for s in COLUMNS[tab]}
    for name in display.MONEY_COLUMNS[tab]:
        assert pd.api.types.is_float_dtype(shown[headers[name]])
        assert shown[headers[name]].tolist() == frames[tab][name].tolist()


def test_margin_pct_times_100() -> None:
    """AC-20: 0.75 → 75.0 and 0.6667 → 66.67, shown with `%.1f%%` as 75.0% and 66.7%."""
    df = pd.DataFrame({"sku": ["SKU-0001", "SKU-0002"], "margin_pct": [0.75, 0.6667]})
    shown = display.table_view("Products", df)
    assert pd.api.types.is_float_dtype(shown["Margin %"])
    assert shown["Margin %"].tolist() == pytest.approx([75.0, 66.67])


# §6.3 headers, order, email, dates


@pytest.mark.parametrize("tab", ["Orders", "Products", "Customers"])
def test_headers_are_sheet_headers_in_order(tab: str, frames: dict[str, pd.DataFrame]) -> None:
    """AC-21."""
    shown = display.table_view(tab, frames[tab])
    assert list(shown.columns) == [s.header for s in COLUMNS[tab]]


@pytest.mark.parametrize("tab", ["Orders", "Products", "Customers"])
def test_rows_in_loader_order(tab: str, frames: dict[str, pd.DataFrame]) -> None:
    """AC-22."""
    key = COLUMNS[tab][0]
    shown = display.table_view(tab, frames[tab])
    assert shown[key.header].tolist() == frames[tab][key.name].tolist()
    assert len(shown) == len(frames[tab])


def test_email_masked() -> None:
    """AC-23: the Customers table never shows a full email."""
    df = pd.DataFrame(
        {"customer_id": ["C-1", "C-2"], "email": ["jane.doe@example.com", ""]},
    ).astype("string")
    shown = display.table_view("Customers", df)
    assert shown["Email"].tolist() == ["j***@example.com", ""]


def test_no_full_email_from_fixture(frames: dict[str, pd.DataFrame]) -> None:
    shown = display.table_view("Customers", frames["Customers"])
    for full, masked in zip(frames["Customers"]["email"], shown["Email"], strict=True):
        assert masked != full
        assert "***" in masked


def test_dates_as_iso_text() -> None:
    """Decision U4: dates shown as YYYY-MM-DD, no time part."""
    df = pd.DataFrame({"order_id": ["#1"], "order_date": pd.to_datetime(["2026-05-31"])})
    shown = display.table_view("Orders", df)
    assert shown["Order Date"].tolist() == ["2026-05-31"]


@pytest.mark.parametrize("tab", ["Orders", "Products", "Customers"])
def test_input_unchanged(tab: str, frames: dict[str, pd.DataFrame]) -> None:
    """AC-24 and AC-09 'data unchanged': the loader's DataFrame is not modified."""
    before = frames[tab].copy(deep=True)
    shown = display.table_view(tab, frames[tab])
    pd.testing.assert_frame_equal(frames[tab], before)
    assert shown is not frames[tab]


def test_refunded_rows_kept(frames: dict[str, pd.DataFrame]) -> None:
    """Display drops no rows; Refunded orders reach the table (AC-25 is checked in the app, T6)."""
    shown = display.table_view("Orders", frames["Orders"])
    assert shown["Status"].tolist() == frames["Orders"]["status"].tolist()
    refunded = shown.loc[shown["Status"] == "Refunded", "Order ID"].tolist()
    assert refunded == ["#1004", "#1007"]


def test_empty_frame() -> None:
    """Decision U6: an empty tab still gets its headers."""
    empty = pd.DataFrame(columns=[s.name for s in COLUMNS["Products"]])
    shown = display.table_view("Products", empty)
    assert list(shown.columns) == [s.header for s in COLUMNS["Products"]]
    assert len(shown) == 0


# Row count (AC-17 text, decision U5)


@pytest.mark.parametrize(
    ("shown", "total", "text"),
    [
        (8, 8, "Showing 8 of 8 rows"),
        (0, 0, "Showing 0 of 0 rows"),
        (3, 1000, "Showing 3 of 1,000 rows"),
        (1000, 1000, "Showing 1,000 of 1,000 rows"),
    ],
)
def test_row_count_text(shown: int, total: int, text: str) -> None:
    assert display.row_count_text(shown, total) == text


# Error screen text (§3: the loader's message shown exactly as written)


def test_escape_markdown_escapes_punctuation() -> None:
    assert display.escape_markdown("SHEET_ID *x* $1 [a](b) `c` #") == (
        r"SHEET\_ID \*x\* \$1 \[a\]\(b\) \`c\` \#"
    )


def test_escape_markdown_leaves_plain_text() -> None:
    assert display.escape_markdown("Sheet tab Orders is empty") == "Sheet tab Orders is empty"


def test_error_text_heading_then_message() -> None:
    text = display.error_text("Column missing", "Tab Orders has no column Line Total (CAD).")
    assert text == r"**Column missing**" + "\n\n" + r"Tab Orders has no column Line Total \(CAD\)\."
