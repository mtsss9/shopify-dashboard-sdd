"""Tests for quality.py. Implements specs/003-dashboard-ui.md §4 and §6.5.

Covers T4 in specs/003-dashboard-ui.tasks.md: AC-07 (messages), AC-08 and AC-39 to
AC-45 at unit level. Reports are built directly with make_entry and TabSummary.
"""

from datetime import date

import pandas as pd

from conftest import TODAY, FakeSheetsClient
from shopify_dashboard import load_data, quality
from shopify_dashboard.report import Severity, TabSummary, ValidationReport, make_entry

D, W = Severity.DROPPED, Severity.WARNING


def _summaries(
    orders: tuple[int, int] = (100, 0),
    products: tuple[int, int] = (10, 0),
    customers: tuple[int, int] = (150, 0),
) -> dict[str, TabSummary]:
    """Summaries keyed in loader order (Products, Customers, Orders), not display order."""
    return {
        "Products": TabSummary(*products),
        "Customers": TabSummary(*customers),
        "Orders": TabSummary(*orders),
    }


# Banner (§4, AC-07)


def test_banner_names_over_threshold_tab() -> None:
    report = ValidationReport(summaries=_summaries(orders=(100, 6)))
    assert quality.banner_messages(report) == ["Orders: 6.0% of rows were dropped"]


def test_no_banner_at_or_below_threshold() -> None:
    report = ValidationReport(summaries=_summaries(orders=(100, 5)))
    assert quality.banner_messages(report) == []


def test_banner_in_tab_order_with_one_decimal() -> None:
    report = ValidationReport(
        summaries=_summaries(orders=(100, 6), products=(3, 1), customers=(150, 10))
    )
    assert quality.banner_messages(report) == [
        "Orders: 6.0% of rows were dropped",
        "Products: 33.3% of rows were dropped",
        "Customers: 6.7% of rows were dropped",
    ]


def test_warnings_never_trigger_banner() -> None:
    entries = [
        make_entry("Orders", r, "Line Total (CAD)", 1.0, "mismatch", W) for r in range(2, 50)
    ]
    report = ValidationReport(entries=entries, summaries=_summaries())
    assert quality.banner_messages(report) == []


# Summary table (§6.5 item 1, AC-08, AC-39, AC-40)


def test_summary_columns_and_tab_order() -> None:
    frame = quality.summary_frame(ValidationReport(summaries=_summaries()))
    assert list(frame.columns) == ["Tab", "Rows read", "Rows dropped", "Drop rate", "Warnings"]
    assert frame["Tab"].tolist() == ["Orders", "Products", "Customers"]


def test_summary_matches_report() -> None:
    """AC-08 and AC-39: rows read, rows dropped and drop rate come from TabSummary."""
    report = ValidationReport(
        summaries=_summaries(orders=(100, 6), products=(10, 0), customers=(150, 1))
    )
    frame = quality.summary_frame(report)
    assert frame["Rows read"].tolist() == [100, 10, 150]
    assert frame["Rows dropped"].tolist() == [6, 0, 1]
    assert frame["Drop rate"].tolist() == ["6.0%", "0.0%", "0.7%"]


def test_summary_warning_counts_exclude_dropped() -> None:
    """AC-40: Warnings counts only severity `warning` entries for each tab."""
    entries = [
        make_entry("Orders", 2, "Line Total (CAD)", 9.0, "mismatch", W),
        make_entry("Orders", 3, "Order Date", 1, "before Customer Since", W),
        make_entry("Orders", 4, "Status", "Shipped", "not allowed", D),
        make_entry("Products", 2, "Margin %", "#REF!", "calculated value unreadable", W),
        make_entry("Customers", 5, "Province", "XX", "not allowed", D),
    ]
    report = ValidationReport(entries=entries, summaries=_summaries())
    assert quality.summary_frame(report)["Warnings"].tolist() == [2, 1, 0]


def test_summary_zero_rows_read() -> None:
    report = ValidationReport(summaries=_summaries(products=(0, 0)))
    frame = quality.summary_frame(report)
    assert frame.loc[frame["Tab"] == "Products", "Drop rate"].tolist() == ["0.0%"]


def test_summary_from_loader(base_tabs) -> None:
    result = load_data(FakeSheetsClient(base_tabs), today=TODAY)
    frame = quality.summary_frame(result.report)
    assert frame["Rows read"].tolist() == [8, 4, 3]
    assert frame["Rows dropped"].tolist() == [0, 0, 0]
    assert frame["Warnings"].tolist() == [0, 0, 0]


# Entries table (§6.5 item 2, AC-41 to AC-45)


def test_entries_columns_and_fields() -> None:
    """AC-41: every entry appears with its six fields."""
    entries = [
        make_entry("Orders", 4, "Status", "Shipped", "not allowed", D),
        make_entry("Products", 3, "Margin %", "#REF!", "calculated value unreadable", W),
    ]
    frame = quality.entries_frame(ValidationReport(entries=entries, summaries=_summaries()))
    assert list(frame.columns) == ["tab", "row", "column", "value", "reason", "severity"]
    assert frame.to_dict("records") == [
        {
            "tab": "Orders",
            "row": 4,
            "column": "Status",
            "value": "Shipped",
            "reason": "not allowed",
            "severity": "dropped",
        },
        {
            "tab": "Products",
            "row": 3,
            "column": "Margin %",
            "value": "#REF!",
            "reason": "calculated value unreadable",
            "severity": "warning",
        },
    ]


def test_entries_sorted_by_tab_then_row_then_column() -> None:
    """AC-43."""
    entries = [
        make_entry("Customers", 2, "Email", "x", "invalid email"),
        make_entry("Products", 5, "SKU", "bad", "bad format"),
        make_entry("Orders", 10, "Status", "x", "not allowed"),
        make_entry("Orders", 3, "Status", "x", "not allowed"),
        make_entry("Orders", 3, "Discount (CAD)", "x", "not a number"),
        make_entry("Products", 2, "Price (CAD)", "x", "not a number"),
    ]
    frame = quality.entries_frame(ValidationReport(entries=entries, summaries=_summaries()))
    assert list(zip(frame["tab"], frame["row"], frame["column"], strict=True)) == [
        ("Orders", 3, "Discount (CAD)"),
        ("Orders", 3, "Status"),
        ("Orders", 10, "Status"),
        ("Products", 2, "Price (CAD)"),
        ("Products", 5, "SKU"),
        ("Customers", 2, "Email"),
    ]


def test_entries_values_as_stored() -> None:
    """AC-42 and decision U3: the raw value's text, no reformatting; blank stays empty."""
    entries = [
        make_entry("Orders", 2, "Order Date", 45812, "in the future"),
        make_entry("Orders", 3, "Quantity", 2.5, "not a whole number"),
        make_entry("Orders", 4, "Status", "Shipped", "not allowed"),
        make_entry("Orders", 5, "Status", "", "required"),
        make_entry("Orders", 6, "Order Date", "2026-02-30", "not a date"),
        make_entry("Orders", 7, "Discount (CAD)", 1234.5, "too large"),
        make_entry("Orders", 8, "Customer ID", None, "required"),
        make_entry("Orders", 9, "Order Date", date(2026, 7, 1), "in the future"),
    ]
    frame = quality.entries_frame(ValidationReport(entries=entries, summaries=_summaries()))
    assert frame["value"].tolist() == [
        "45812",
        "2.5",
        "Shipped",
        "",
        "2026-02-30",
        "1234.5",
        "",
        "2026-07-01",
    ]
    assert pd.api.types.is_object_dtype(frame["value"]) or pd.api.types.is_string_dtype(
        frame["value"]
    )


def test_entries_email_masked() -> None:
    """AC-45: an Email entry shows the masked value, never the full email."""
    entry = make_entry("Customers", 4, "Email", "jane.doe@example.com", "invalid email")
    frame = quality.entries_frame(ValidationReport(entries=[entry], summaries=_summaries()))
    assert frame["value"].tolist() == ["j***@example.com"]
    assert "jane.doe@example.com" not in frame.to_string()


def test_no_entries_returns_none() -> None:
    """AC-44: the app shows "No problems found." instead of a table."""
    assert quality.entries_frame(ValidationReport(summaries=_summaries())) is None


def test_report_unchanged() -> None:
    entries = [make_entry("Orders", 3, "Status", "x", "not allowed")]
    report = ValidationReport(entries=list(entries), summaries=_summaries(orders=(100, 6)))
    quality.banner_messages(report)
    quality.summary_frame(report)
    quality.entries_frame(report)
    assert report.entries == entries
    assert report.summaries == _summaries(orders=(100, 6))
