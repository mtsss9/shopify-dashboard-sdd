"""Row rule checks per tab. Implements specs/001-data-source.md §3–7.

Each validator returns the valid rows (``ParsedRow`` with typed values, keyed by sheet
header) plus report entries. A row that breaks several rules gets one entry per rule
and is dropped once (spec §7.2).
"""

import re
from collections.abc import Callable, Mapping
from typing import Any

from shopify_dashboard.parsing import UNREADABLE, ParsedRow, ParsedTab, coerce_cell
from shopify_dashboard.report import ReportEntry, Severity, make_entry
from shopify_dashboard.schema import COLUMNS, ColumnSpec

Rule = Callable[[Any], str | None]
"""Checks one typed, non-blank value; returns a reason when the rule is broken."""

INVALID_FORMAT = "invalid format"
NOT_ALLOWED = "not an allowed value"
NOT_POSITIVE = "must be greater than 0"
NEGATIVE = "must be 0 or more"
NO_AT = "must contain @"


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
