"""Raw tab clean-up and cell conversion. Implements specs/001-data-source.md §2, §3 and §7.1."""

import math
import re
from dataclasses import dataclass
from datetime import date, timedelta

from shopify_dashboard.errors import DataSourceError, ErrorCategory
from shopify_dashboard.schema import COLUMNS, TABS, ColumnSpec

RawTabs = dict[str, list[list[object]]]
"""Tab name -> rows of cells, as the Sheets API returns them with unformatted values."""

SHEETS_EPOCH = date(1899, 12, 30)
DISCOUNT_HEADER = "Discount (CAD)"  # spec §4: blank means 0
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

REQUIRED = "required"
NOT_A_NUMBER = "must be a number"
NOT_WHOLE = "must be a whole number"
NOT_A_DATE = "must be a date (YYYY-MM-DD)"
NOT_REAL_DATE = "not a real calendar date"


@dataclass(frozen=True)
class ParsedRow:
    """One non-blank data row. ``sheet_row`` counts the header as row 1 (spec §7.3)."""

    sheet_row: int
    cells: dict[str, object]


@dataclass(frozen=True)
class ParsedTab:
    """A tab with trimmed headers and only its non-blank rows. Implements spec 001 §2–3."""

    tab: str
    headers: tuple[str, ...]
    rows: list[ParsedRow]


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def parse_tabs(raw: RawTabs) -> dict[str, ParsedTab]:
    """Check structure and collect data rows. Implements specs/001-data-source.md §2, §3, §7.1.

    Raises ``missing_tab``, ``missing_column`` or ``empty_tab``. Extra columns are ignored
    and ``cells`` holds only the spec columns, keyed by trimmed sheet header.
    """
    for tab in TABS:
        if tab not in raw:
            raise DataSourceError(ErrorCategory.MISSING_TAB, f"The sheet is missing the {tab} tab.")
    return {tab: _parse_tab(tab, raw[tab]) for tab in TABS}


def _parse_tab(tab: str, rows: list[list[object]]) -> ParsedTab:
    """Check order (spec §7.1): completely empty, missing, duplicate, no data rows."""
    empty = DataSourceError(ErrorCategory.EMPTY_TAB, f"The {tab} tab has no data rows.")
    if all(_is_blank(v) for row in rows for v in row):
        raise empty

    headers = tuple("" if h is None else str(h).strip() for h in rows[0])
    positions: dict[str, list[int]] = {}
    for i, header in enumerate(headers):
        positions.setdefault(header, []).append(i)

    for spec in COLUMNS[tab]:
        if spec.header not in positions:
            raise DataSourceError(
                ErrorCategory.MISSING_COLUMN,
                f"The {tab} tab is missing the {spec.header} column.",
            )
    for spec in COLUMNS[tab]:
        if len(positions[spec.header]) > 1:
            raise DataSourceError(
                ErrorCategory.DUPLICATE_COLUMN,
                f"The {tab} tab has more than one {spec.header} column.",
            )

    index = {spec.header: positions[spec.header][0] for spec in COLUMNS[tab]}
    parsed: list[ParsedRow] = []
    for sheet_row, row in enumerate(rows[1:], start=2):
        # The API omits trailing empty cells (D10); extra columns never count (spec §2).
        cells = {h: row[i] if i < len(row) else "" for h, i in index.items()}
        if all(_is_blank(v) for v in cells.values()):
            continue
        parsed.append(ParsedRow(sheet_row, cells))

    if not parsed:
        raise empty
    return ParsedTab(tab, headers, parsed)


def coerce_cell(value: object, spec: ColumnSpec) -> tuple[object | None, str | None]:
    """Convert one raw cell to its typed value. Implements specs/001-data-source.md §3.

    Returns ``(value, None)`` on success or ``(None, reason)`` when a rule is broken.
    A blank Discount is 0; a blank calculated cell is ``(None, None)`` (decision D2).
    Enum membership and ID formats are checked in validation, not here.
    """
    if _is_blank(value):
        if spec.header == DISCOUNT_HEADER:
            return 0.0, None
        if spec.calculated or not spec.required:
            return None, None
        return None, REQUIRED

    if spec.kind in ("str", "enum"):
        return str(value).strip(), None
    if spec.kind == "decimal":
        return (float(value), None) if _is_number(value) else (None, NOT_A_NUMBER)
    if spec.kind == "int":
        if not _is_number(value):
            return None, NOT_A_NUMBER
        if not float(value).is_integer():
            return None, NOT_WHOLE
        return int(value), None
    return _coerce_date(value)


def _coerce_date(value: object) -> tuple[date | None, str | None]:
    if _is_number(value):
        try:
            return SHEETS_EPOCH + timedelta(days=math.floor(value)), None
        except (OverflowError, ValueError):
            return None, NOT_REAL_DATE
    if isinstance(value, str) and _ISO_DATE.fullmatch(value.strip()):
        try:
            return date.fromisoformat(value.strip()), None
        except ValueError:
            return None, NOT_REAL_DATE
    return None, NOT_A_DATE
