"""Google Sheets access. Implements specs/001-data-source.md §2, §3, §7.1 and §8.

This is the only module that imports ``gspread`` or ``google.*``.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import google.auth.exceptions as gauth
import gspread
import requests

from shopify_dashboard.config import Config
from shopify_dashboard.errors import DataSourceError, ErrorCategory
from shopify_dashboard.parsing import RawTabs, SheetDate

TIMEOUT_SECONDS = 30
"""API timeout, with no retries; the dashboard's Refresh button is the retry (D4)."""

RENDER_PARAMS = {
    "valueRenderOption": "UNFORMATTED_VALUE",
    "dateTimeRenderOption": "SERIAL_NUMBER",
    "majorDimension": "ROWS",
}
"""Raw numbers and serial-number dates, never display text. Implements spec 001 §3."""

METADATA_PARAMS = {
    "includeGridData": "true",
    "fields": "sheets(properties.title,data.rowData.values.effectiveFormat.numberFormat.type)",
}
"""Tab titles plus each cell's number-format type, nothing else (spec §3, §8, D27)."""

DATE_FORMATS = frozenset({"DATE", "DATE_TIME"})
"""Number-format types whose numbers are date values (spec §3)."""

AUTH_STATUSES = frozenset({401, 403})
"""HTTP statuses reported as ``auth``: bad sign-in or no access to the sheet (spec §7.1, D25)."""

AUTH_MESSAGE = "Could not sign in to Google Sheets."
UNREACHABLE_MESSAGE = "Could not reach the Google Sheet."


class SheetsClient(Protocol):
    """Reads tabs from the spreadsheet. Implements specs/001-data-source.md §2 and §8."""

    def fetch_tabs(self, tabs: Sequence[str]) -> RawTabs:
        """Return the requested tabs that exist, read in one batch with unformatted values.

        Numbers from date-formatted cells are wrapped in ``SheetDate`` (D27).
        """
        ...


def _a1(tab: str) -> str:
    """Quote a tab name as an A1 range covering the whole tab."""
    return "'" + tab.replace("'", "''") + "'"


def _date_cells(sheet: Mapping[str, Any]) -> set[tuple[int, int]]:
    """Zero-based (row, column) positions of date-formatted cells. Implements spec 001 §3."""
    cells: set[tuple[int, int]] = set()
    for grid in sheet.get("data", []):
        top, left = grid.get("startRow", 0), grid.get("startColumn", 0)
        for i, row in enumerate(grid.get("rowData", [])):
            for j, cell in enumerate(row.get("values", [])):
                kind = cell.get("effectiveFormat", {}).get("numberFormat", {}).get("type")
                if kind in DATE_FORMATS:
                    cells.add((top + i, left + j))
    return cells


def _mark_dates(rows: list[list[object]], date_cells: set[tuple[int, int]]) -> list[list[object]]:
    """Wrap numbers in date-formatted cells in ``SheetDate``. Implements spec 001 §3 (D27)."""
    return [
        [
            SheetDate(v)
            if (i, j) in date_cells and isinstance(v, int | float) and not isinstance(v, bool)
            else v
            for j, v in enumerate(row)
        ]
        for i, row in enumerate(rows)
    ]


class GspreadSheetsClient:
    """The real Google Sheets adapter. Implements specs/001-data-source.md §2, §3, §7.1, §8.

    Error messages are fixed texts and the original exception is dropped (``from None``),
    so no sheet ID, credentials path or stack trace can reach them.
    """

    def __init__(self, config: Config) -> None:
        self._config = config

    def __repr__(self) -> str:
        return "GspreadSheetsClient(config=<hidden>)"

    def fetch_tabs(self, tabs: Sequence[str]) -> RawTabs:
        """One lookup for tab names and cell formats, then one batch read of the tabs that exist."""
        try:
            client = gspread.service_account(
                filename=self._config.credentials_path,
                scopes=gspread.auth.READONLY_SCOPES,
                http_client=gspread.http_client.HTTPClient,  # no back-off: no retries (D4)
            )
        except (OSError, ValueError, gauth.GoogleAuthError):
            raise DataSourceError(ErrorCategory.AUTH, AUTH_MESSAGE) from None
        client.set_timeout(TIMEOUT_SECONDS)

        sheet_id = self._config.sheet_id
        try:
            metadata = client.http_client.fetch_sheet_metadata(
                sheet_id, params=dict(METADATA_PARAMS)
            )
            sheets = {s["properties"]["title"]: s for s in metadata.get("sheets", [])}
            present = [t for t in tabs if t in sheets]
            if not present:
                return {}
            response = client.http_client.values_batch_get(
                sheet_id, [_a1(t) for t in present], params=dict(RENDER_PARAMS)
            )
        except gspread.exceptions.APIError as e:
            if e.response.status_code in AUTH_STATUSES:
                raise DataSourceError(ErrorCategory.AUTH, AUTH_MESSAGE) from None
            raise DataSourceError(ErrorCategory.UNREACHABLE, UNREACHABLE_MESSAGE) from None
        except (gauth.TransportError, requests.RequestException):
            raise DataSourceError(ErrorCategory.UNREACHABLE, UNREACHABLE_MESSAGE) from None
        except gauth.GoogleAuthError:
            raise DataSourceError(ErrorCategory.AUTH, AUTH_MESSAGE) from None

        value_ranges = response.get("valueRanges", [])
        return {
            t: _mark_dates(vr.get("values", []), _date_cells(sheets[t]))
            for t, vr in zip(present, value_ranges, strict=True)
        }
