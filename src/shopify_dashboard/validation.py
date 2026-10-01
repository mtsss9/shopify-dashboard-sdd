"""Row rule checks per tab. Implements specs/001-data-source.md §3–7.

Each validator returns the valid rows (``ParsedRow`` with typed values, keyed by sheet
header) plus report entries. A row that breaks several rules gets one entry per rule
and is dropped once (spec §7.2).
"""

import re
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

from shopify_dashboard.parsing import UNREADABLE, ParsedRow, ParsedTab, coerce_cell
from shopify_dashboard.report import (
    ReportEntry,
    Severity,
    TabSummary,
    ValidationReport,
    make_entry,
)
from shopify_dashboard.schema import COLUMNS, TABS, UNIQUE_KEYS, ColumnSpec

Rule = Callable[[Any], str | None]
"""Checks one typed, non-blank value; returns a reason when the rule is broken."""

INVALID_FORMAT = "invalid format"
NOT_ALLOWED = "not an allowed value"
NOT_POSITIVE = "must be greater than 0"
NEGATIVE = "must be 0 or more"
NO_AT = "must contain @"
BELOW_ONE = "must be 1 or more"
SKU_NOT_FOUND = "SKU not found"
CUSTOMER_NOT_FOUND = "Customer not found"
FUTURE_DATE = "must not be after today"
DISCOUNT_TOO_LARGE = "must not exceed Quantity × Unit Price"
LINE_TOTAL_DIFFERS = "differs from Quantity × Unit Price − Discount"
BEFORE_CUSTOMER_SINCE = "before the customer's Customer Since"

TOLERANCE = 0.01
"""Money comparison tolerance in CAD. Implements specs/001-data-source.md §3 (D9)."""


def _positive(value: float) -> str | None:
    return None if value > 0 else NOT_POSITIVE


def _non_negative(value: float) -> str | None:
    return None if value >= 0 else NEGATIVE


def _has_at(value: str) -> str | None:
    return None if "@" in str(value) else NO_AT


PRODUCT_RULES: dict[str, Rule] = {
    "Price (CAD)": _positive,
    "Unit Cost (CAD)": _non_negative,
    "Inventory": _non_negative,
}
"""Implements specs/001-data-source.md §5."""

CUSTOMER_RULES: dict[str, Rule] = {"Email": _has_at}
"""Implements specs/001-data-source.md §6."""


def _at_least_one(value: int) -> str | None:
    return None if value >= 1 else BELOW_ONE


ORDER_RULES: dict[str, Rule] = {
    "Quantity": _at_least_one,
    "Unit Price (CAD)": _positive,
    "Discount (CAD)": _non_negative,
}
"""Single-cell rules. Implements specs/001-data-source.md §4."""


def _column_rule(value: object, spec: ColumnSpec) -> str | None:
    """ID format and enum membership. Implements specs/001-data-source.md §3–6."""
    if spec.pattern is not None and not re.fullmatch(spec.pattern, str(value)):
        return INVALID_FORMAT
    if spec.allowed is not None and value not in spec.allowed:
        return NOT_ALLOWED
    return None


def check_row(
    tab: str, row: ParsedRow, rules: Mapping[str, Rule]
) -> tuple[dict[str, object], list[ReportEntry]]:
    """Coerce and check every spec column of one row. Implements specs/001-data-source.md §3, §7.2.

    Returns the typed cells and one entry per broken rule (empty when the row is valid).
    """
    typed: dict[str, object] = {}
    entries: list[ReportEntry] = []
    for spec in COLUMNS[tab]:
        raw = row.cells[spec.header]
        value, reason = coerce_cell(raw, spec)
        if reason is None and value is not None:
            reason = _column_rule(value, spec)
            if reason is None and spec.header in rules:
                reason = rules[spec.header](value)
        if reason is None:
            typed[spec.header] = value
        elif reason == UNREADABLE:  # D16: kept, treated as missing, recorded as a warning
            typed[spec.header] = None
            entries.append(
                make_entry(tab, row.sheet_row, spec.header, raw, reason, Severity.WARNING)
            )
        else:
            entries.append(make_entry(tab, row.sheet_row, spec.header, raw, reason))
    return typed, entries


def is_dropped(entries: list[ReportEntry]) -> bool:
    """True when any entry drops the row (warnings never do). Implements spec 001 §7.2."""
    return any(e.severity is Severity.DROPPED for e in entries)


def _validate(
    tab: ParsedTab, rules: Mapping[str, Rule]
) -> tuple[list[ParsedRow], list[ReportEntry]]:
    valid: list[ParsedRow] = []
    entries: list[ReportEntry] = []
    for row in tab.rows:
        typed, row_entries = check_row(tab.tab, row, rules)
        entries += row_entries
        if not is_dropped(row_entries):
            valid.append(ParsedRow(row.sheet_row, typed))
    return valid, entries


def validate_products(tab: ParsedTab) -> tuple[list[ParsedRow], list[ReportEntry]]:
    """Formats, Category, Price > 0, Unit Cost ≥ 0, Inventory ≥ 0. Implements spec 001 §5."""
    return _validate(tab, PRODUCT_RULES)


def validate_customers(tab: ParsedTab) -> tuple[list[ParsedRow], list[ReportEntry]]:
    """ID format, ``@`` in Email, Province, real Customer Since. Implements spec 001 §6."""
    return _validate(tab, CUSTOMER_RULES)


def _exceeds(amount: float, limit: float) -> bool:
    """True when ``amount`` is more than 1 cent above ``limit`` (spec §3)."""
    return round(amount - limit, 9) > TOLERANCE


def _check_order(
    tab: str,
    row: ParsedRow,
    skus: set[object],
    since: Mapping[object, object],
    today: date,
) -> tuple[dict[str, object], list[ReportEntry]]:
    """All checks for one order row. Implements specs/001-data-source.md §4, §7.2."""
    typed, entries = check_row(tab, row, ORDER_RULES)
    bad = {e.column for e in entries if e.severity is Severity.DROPPED}

    def entry(column: str, reason: str, severity: Severity = Severity.DROPPED) -> ReportEntry:
        return make_entry(tab, row.sheet_row, column, row.cells[column], reason, severity)

    if "SKU" not in bad and typed["SKU"] not in skus:
        entries.append(entry("SKU", SKU_NOT_FOUND))
    if "Customer ID" not in bad and typed["Customer ID"] not in since:
        entries.append(entry("Customer ID", CUSTOMER_NOT_FOUND))
    if "Order Date" not in bad and typed["Order Date"] > today:
        entries.append(entry("Order Date", FUTURE_DATE))
    amounts = ("Quantity", "Unit Price (CAD)", "Discount (CAD)")
    if not bad.intersection(amounts):
        quantity, unit_price, discount = (typed[h] for h in amounts)
        if _exceeds(discount, quantity * unit_price):
            entries.append(entry("Discount (CAD)", DISCOUNT_TOO_LARGE))

    if not is_dropped(entries):  # cross-check warnings only for rows that are kept
        sheet_total = typed["Line Total (CAD)"]  # None when blank or unreadable (D2, D16)
        expected = typed["Quantity"] * typed["Unit Price (CAD)"] - typed["Discount (CAD)"]
        if sheet_total is not None and _exceeds(abs(sheet_total - expected), 0):
            entries.append(entry("Line Total (CAD)", LINE_TOTAL_DIFFERS, Severity.WARNING))
        if typed["Order Date"] < since[typed["Customer ID"]]:
            entries.append(entry("Order Date", BEFORE_CUSTOMER_SINCE, Severity.WARNING))
    return typed, entries


def validate_orders(
    tab: ParsedTab,
    products: list[ParsedRow],
    customers: list[ParsedRow],
    today: date,
) -> tuple[list[ParsedRow], list[ReportEntry]]:
    """Cell rules, Discount limit, dates, references and warnings. Implements spec 001 §4, §7.2.

    SKU and Customer ID are checked against the **validated** Products and Customers.
    Line Total and Customer Since warnings are only recorded for rows that are kept.
    """
    skus = {r.cells["SKU"] for r in products}
    since = {r.cells["Customer ID"]: r.cells["Customer Since"] for r in customers}
    valid: list[ParsedRow] = []
    entries: list[ReportEntry] = []
    for row in tab.rows:
        typed, row_entries = _check_order(tab.tab, row, skus, since, today)
        entries += row_entries
        if not is_dropped(row_entries):
            valid.append(ParsedRow(row.sheet_row, typed))
    return valid, entries


def find_duplicate_keys(tab: ParsedTab, key: str) -> list[ReportEntry]:
    """Drop every row that shares a key. Implements specs/001-data-source.md §7.2 (D1).

    Keys are compared after trimming; blank keys are left to the ``required`` rule.
    """
    groups: dict[str, list[ParsedRow]] = {}
    for row in tab.rows:
        value = row.cells[key]
        text = "" if value is None else str(value).strip()
        if text:
            groups.setdefault(text, []).append(row)
    duplicates = sorted(
        (r for rows in groups.values() if len(rows) > 1 for r in rows),
        key=lambda r: r.sheet_row,
    )
    return [
        make_entry(tab.tab, r.sheet_row, key, r.cells[key], f"duplicate {key}") for r in duplicates
    ]


def validate_all(
    tabs: Mapping[str, ParsedTab], today: date
) -> tuple[dict[str, list[ParsedRow]], ValidationReport]:
    """Validate Products, then Customers, then Orders. Implements specs/001-data-source.md §7.

    Duplicate keys are checked first; duplicate rows get no other checks (D1). Each tab's
    entries are in sheet row order. Warnings never count towards ``rows_dropped``.
    """
    valid: dict[str, list[ParsedRow]] = {}
    report = ValidationReport()
    for name in TABS:
        tab = tabs[name]
        duplicates = find_duplicate_keys(tab, UNIQUE_KEYS[name])
        duplicate_rows = {e.row for e in duplicates}
        rest = ParsedTab(
            tab.tab, tab.headers, [r for r in tab.rows if r.sheet_row not in duplicate_rows]
        )
        if name == "Products":
            rows, entries = validate_products(rest)
        elif name == "Customers":
            rows, entries = validate_customers(rest)
        else:
            rows, entries = validate_orders(rest, valid["Products"], valid["Customers"], today)

        tab_entries = sorted(duplicates + entries, key=lambda e: e.row)
        valid[name] = rows
        report.entries += tab_entries
        dropped_rows = {e.row for e in tab_entries if e.severity is Severity.DROPPED}
        report.summaries[name] = TabSummary(rows_read=len(tab.rows), rows_dropped=len(dropped_rows))
    return valid, report
