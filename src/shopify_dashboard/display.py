"""Display helpers for the Data Explorer. Implements specs/003-dashboard-ui.md §3, §5 and §6.3.

No Streamlit import: ``app.py`` turns the plain format strings here into
``st.column_config.NumberColumn`` objects (plan 003 decision U11).
"""

import re

import pandas as pd

from shopify_dashboard.errors import ErrorCategory
from shopify_dashboard.report import mask_email
from shopify_dashboard.schema import COLUMNS

ERROR_HEADINGS: dict[ErrorCategory, str] = {
    ErrorCategory.CONFIG: "Configuration problem",
    ErrorCategory.AUTH: "Could not sign in to Google Sheets",
    ErrorCategory.UNREACHABLE: "Could not reach the Google Sheet",
    ErrorCategory.MISSING_TAB: "Sheet tab missing",
    ErrorCategory.MISSING_COLUMN: "Column missing",
    ErrorCategory.DUPLICATE_COLUMN: "Duplicate column",
    ErrorCategory.EMPTY_TAB: "Sheet tab is empty",
}
"""Fixed heading per error category. Implements specs/003-dashboard-ui.md §3."""

MONEY_FORMAT = "$%,.2f"
"""sprintf format for money columns: 1234.5 shows as $1,234.50. Implements spec 003 §5."""

PCT_FORMAT = "%.1f%%"
"""sprintf format for Margin %, applied to the value × 100. Implements spec 003 §6.3."""

MONEY_COLUMNS: dict[str, tuple[str, ...]] = {
    "Orders": ("unit_price_cad", "discount_cad", "line_total_cad"),
    "Products": ("price_cad", "unit_cost_cad", "revenue_cad"),
    "Customers": ("total_spent_cad",),
}
"""Money columns per table tab. Implements specs/003-dashboard-ui.md §6.3."""

_PCT_COLUMNS: dict[str, tuple[str, ...]] = {"Products": ("margin_pct",)}
_EMAIL_COLUMNS: dict[str, tuple[str, ...]] = {"Customers": ("email",)}


def _headers(tab: str) -> dict[str, str]:
    """Map snake_case output names to sheet headers (spec 001 §9 in reverse)."""
    return {s.name: s.header for s in COLUMNS[tab]}


def number_formats(tab: str) -> dict[str, str]:
    """Return sheet header → sprintf format for a tab's number columns.

    Implements specs/003-dashboard-ui.md §5 and §6.3 (plan 003 decision U11).
    """
    headers = _headers(tab)
    formats = {headers[name]: MONEY_FORMAT for name in MONEY_COLUMNS[tab]}
    formats.update({headers[name]: PCT_FORMAT for name in _PCT_COLUMNS.get(tab, ())})
    return formats


def table_view(tab: str, df: pd.DataFrame) -> pd.DataFrame:
    """Return a new DataFrame for display; ``df`` is never changed.

    Implements specs/003-dashboard-ui.md §5 and §6.3: money stays numeric and unrounded,
    Margin % is multiplied by 100, emails are masked, dates become YYYY-MM-DD text and
    columns are renamed to sheet headers. Row order is kept.
    """
    view = df.copy(deep=True)
    for name in _PCT_COLUMNS.get(tab, ()):
        if name in view.columns:
            view[name] = view[name].astype("float64") * 100
    for name in _EMAIL_COLUMNS.get(tab, ()):
        if name in view.columns:
            view[name] = view[name].map(mask_email, na_action="ignore")
    for s in COLUMNS[tab]:
        if s.kind == "date" and s.name in view.columns:
            view[s.name] = pd.to_datetime(view[s.name]).dt.strftime("%Y-%m-%d")
    return view.rename(columns=_headers(tab))


_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()<>#+\-.!|$~])")


def escape_markdown(text: str) -> str:
    """Backslash-escape Markdown punctuation so ``text`` renders exactly as written.

    Implements specs/003-dashboard-ui.md §3 (the loader's message is shown unchanged).
    """
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def error_text(heading: str, message: str) -> str:
    """Return the error-screen text: bold heading, then the message on its own line.

    Implements specs/003-dashboard-ui.md §3.
    """
    return f"**{heading}**\n\n{escape_markdown(message)}"


def row_count_text(shown: int, total: int) -> str:
    """Return "Showing X of Y rows" with thousands separators.

    Implements specs/003-dashboard-ui.md §6.3 (plan 003 decision U5).
    """
    return f"Showing {shown:,} of {total:,} rows"
