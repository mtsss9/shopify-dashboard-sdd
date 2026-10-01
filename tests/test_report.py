"""Tests for report.py. Implements specs/001-data-source.md §7.3 (AC-21, AC-22 unit)."""

import dataclasses

import pytest

from shopify_dashboard.report import (
    ReportEntry,
    Severity,
    TabSummary,
    ValidationReport,
    make_entry,
    mask_email,
)


def test_severity_values() -> None:
    assert [s.value for s in Severity] == ["dropped", "warning"]


@pytest.mark.parametrize(
    ("raw", "masked"),
    [
        ("jane@example.com", "j***@example.com"),  # spec §7.3 example
        ("jane.example.com", "j***"),  # no @: first character only
        ("  jane@example.com ", "j***@example.com"),  # trimmed first
        ("@example.com", "***@example.com"),  # empty local part
        ("a@b@c.com", "a***@c.com"),  # domain is after the last @
        ("j", "j***"),
        (12345, "1***"),  # non-text values are masked too
        ("", ""),  # blank: nothing to hide
        ("   ", ""),
    ],
)
def test_mask_email(raw: object, masked: str) -> None:
    assert mask_email(raw) == masked


@pytest.mark.parametrize("raw", ["jane@example.com", "jane.example.com", "@x.com", ""])
def test_mask_email_is_idempotent(raw: str) -> None:
    once = mask_email(raw)
    assert mask_email(once) == once


def test_make_entry_masks_email() -> None:
    """AC-22 (unit): an invalid email is stored masked."""
    entry = make_entry("Customers", 4, "Email", "jane.example.com", "must contain @")
    assert entry.value == "j***"
    assert entry.severity is Severity.DROPPED


def test_make_entry_keeps_other_values_and_severity() -> None:
    entry = make_entry("Orders", 7, "Line Total (CAD)", 40.05, "differs", Severity.WARNING)
    assert entry == ReportEntry("Orders", 7, "Line Total (CAD)", 40.05, "differs", "warning")


def test_direct_construction_also_masks_email() -> None:
    entry = ReportEntry("Customers", 2, "Email", "jane@example.com", "x", Severity.DROPPED)
    assert entry.value == "j***@example.com"


def test_replacing_an_entry_does_not_remask() -> None:
    entry = make_entry("Customers", 2, "Email", "@example.com", "x")
    assert dataclasses.replace(entry, reason="y").value == "***@example.com"


def test_entry_is_frozen() -> None:
    entry = make_entry("Orders", 2, "Status", "Shipped", "not allowed")
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.value = "jane@example.com"  # type: ignore[misc]


def test_report_repr_holds_no_full_email() -> None:
    """AC-22 (unit)."""
    report = ValidationReport(
        entries=[
            make_entry("Customers", 2, "Email", "jane.doe@example.com", "duplicate"),
            make_entry("Customers", 3, "Email", "luc.example.ca", "must contain @"),
        ],
        summaries={"Customers": TabSummary(rows_read=3, rows_dropped=2)},
    )
    text = repr(report) + str(report)
    assert "jane.doe@example.com" not in text
    assert "luc.example.ca" not in text
    assert "j***@example.com" in text


@pytest.mark.parametrize(("dropped", "over"), [(6, True), (5, False), (0, False)])
def test_over_threshold_at_5_percent(dropped: int, over: bool) -> None:
    """AC-21 (unit): 6 of 100 is over; 5 of 100 is not."""
    summary = TabSummary(rows_read=100, rows_dropped=dropped)
    assert summary.drop_rate == dropped / 100
    assert summary.over_threshold is over


def test_drop_rate_with_no_rows_read_is_zero() -> None:
    summary = TabSummary(rows_read=0, rows_dropped=0)
    assert summary.drop_rate == 0.0
    assert summary.over_threshold is False


def test_dropped_and_warnings_helpers() -> None:
    d1 = make_entry("Orders", 2, "Status", "Shipped", "not allowed")
    w1 = make_entry("Orders", 3, "Line Total (CAD)", 40.05, "differs", Severity.WARNING)
    d2 = make_entry("Orders", 4, "Quantity", 0, "must be >= 1")
    report = ValidationReport(entries=[d1, w1, d2])
    assert report.dropped() == [d1, d2]
    assert report.warnings() == [w1]
    assert report.summaries == {}
