"""Google Sheets access. Implements specs/001-data-source.md §2, §3 and §8.

This is the only module that may import ``gspread`` or ``google.*``. The real adapter,
``GspreadSheetsClient``, is added in T10.
"""

from collections.abc import Sequence
from typing import Protocol

from shopify_dashboard.parsing import RawTabs


class SheetsClient(Protocol):
    """Reads tabs from the spreadsheet. Implements specs/001-data-source.md §2 and §8."""

    def fetch_tabs(self, tabs: Sequence[str]) -> RawTabs:
        """Return the requested tabs that exist, read in one batch with unformatted values."""
        ...
