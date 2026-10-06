"""Data-quality views of the validation report. Implements specs/003-dashboard-ui.md §4 and §6.5.

No Streamlit import. The report is read, never changed. Email values arrive already
masked from spec 001 (``ReportEntry``) and are shown as they are.
"""

import pandas as pd

from shopify_dashboard.report import ReportEntry, Severity, ValidationReport

TAB_ORDER: tuple[str, ...] = ("Orders", "Products", "Customers")
"""Display order of tabs. Implements specs/003-dashboard-ui.md §6.2 and §6.5."""

ENTRY_COLUMNS: tuple[str, ...] = ("tab", "row", "column", "value", "reason", "severity")


def _pct(rate: float) -> str:
    """A drop rate as a percentage with 1 decimal, e.g. 0.06 → "6.0%" (plan 003 U7)."""
    return f"{rate * 100:.1f}%"


def banner_messages(report: ValidationReport) -> list[str]:
    """Return one "<Tab>: 6.0% of rows were dropped" per over-threshold tab, in tab order.

    Implements specs/003-dashboard-ui.md §4. Warnings never trigger the banner.
    """
    return [
        f"{tab}: {_pct(report.summaries[tab].drop_rate)} of rows were dropped"
        for tab in TAB_ORDER
        if tab in report.summaries and report.summaries[tab].over_threshold
    ]


def summary_frame(report: ValidationReport) -> pd.DataFrame:
    """Return rows read, rows dropped, drop rate and warnings per tab, in tab order.

    Implements specs/003-dashboard-ui.md §6.5 item 1.
    """
    warnings = [e.tab for e in report.entries if e.severity is Severity.WARNING]
    rows = [
        {
            "Tab": tab,
            "Rows read": report.summaries[tab].rows_read,
            "Rows dropped": report.summaries[tab].rows_dropped,
            "Drop rate": _pct(report.summaries[tab].drop_rate),
            "Warnings": warnings.count(tab),
        }
        for tab in TAB_ORDER
        if tab in report.summaries
    ]
    return pd.DataFrame(rows, columns=["Tab", "Rows read", "Rows dropped", "Drop rate", "Warnings"])


def _raw_text(value: object) -> str:
    """The stored value's own text; a missing value is blank (plan 003 decision U3)."""
    return "" if value is None else str(value)


def _sort_key(entry: ReportEntry) -> tuple[int, int, str]:
    rank = TAB_ORDER.index(entry.tab) if entry.tab in TAB_ORDER else len(TAB_ORDER)
    return rank, entry.row, entry.column


def entries_frame(report: ValidationReport) -> pd.DataFrame | None:
    """Return all report entries sorted by tab, row, column; None when there are none.

    Implements specs/003-dashboard-ui.md §6.5 item 2. Values are shown as stored.
    """
    if not report.entries:
        return None
    rows = [
        {
            "tab": e.tab,
            "row": e.row,
            "column": e.column,
            "value": _raw_text(e.value),
            "reason": e.reason,
            "severity": str(e.severity),
        }
        for e in sorted(report.entries, key=_sort_key)
    ]
    return pd.DataFrame(rows, columns=list(ENTRY_COLUMNS))
