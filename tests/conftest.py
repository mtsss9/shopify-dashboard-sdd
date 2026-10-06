"""Shared test helpers: fake Sheets client, fixture loading and mutation helpers.

Implements the test strategy in specs/001-data-source.plan.md §5. Tests never call the
real Google Sheet; they feed fixture data through ``FakeSheetsClient``.
"""

import copy
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest

from shopify_dashboard.parsing import SheetDate
from shopify_dashboard.schema import COLUMNS

RawTabs = dict[str, list[list[object]]]

FIXTURES = Path(__file__).parent / "fixtures"
TABS: tuple[str, ...] = ("Products", "Customers", "Orders")
TODAY = date(2026, 6, 1)
SHEETS_EPOCH = date(1899, 12, 30)


def serial(d: date) -> int:
    """Return the Google Sheets serial number for ``d``. Implements spec 001 §3."""
    return (d - SHEETS_EPOCH).days


def sheet_date(d: date) -> SheetDate:
    """``d`` as the client returns it from a date-formatted cell. Implements spec 001 §3 (D27)."""
    return SheetDate(serial(d))


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def load_fixture(name: str) -> RawTabs:
    """Load a ``RawTabs`` JSON document from ``tests/fixtures/``.

    Numbers in date columns are wrapped in ``SheetDate``, as the real client does for the
    real sheet's date-formatted cells (D27).
    """
    tabs: RawTabs = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    for tab, rows in tabs.items():
        dates = {s.header for s in COLUMNS.get(tab, ()) if s.kind == "date"}
        cols = [i for i, h in enumerate(rows[0] if rows else []) if h in dates]
        for row in rows[1:]:
            for i in cols:
                if i < len(row) and _is_number(row[i]):
                    row[i] = SheetDate(row[i])
    return tabs


def unwrap_dates(tabs: RawTabs) -> RawTabs:
    """Turn every ``SheetDate`` back into its plain number, as the values API returns it."""
    return {
        t: [[v.serial if isinstance(v, SheetDate) else v for v in row] for row in rows]
        for t, rows in tabs.items()
    }


class FakeSheetsClient:
    """In-memory stand-in for the ``SheetsClient`` protocol (plan §5.1).

    Returns values as ``GspreadSheetsClient`` does: numbers as int/float, dates from
    date-formatted cells as ``SheetDate`` serial numbers (D27) and blanks as ``""``.
    """

    def __init__(self, tabs: RawTabs, error: Exception | None = None) -> None:
        self._tabs = copy.deepcopy(tabs)
        self._error = error
        self.calls = 0

    def fetch_tabs(self, tabs: Sequence[str]) -> RawTabs:
        """Return a deep copy of the requested tabs that exist, or raise the set error."""
        self.calls += 1
        if self._error is not None:
            raise self._error
        return {t: copy.deepcopy(self._tabs[t]) for t in tabs if t in self._tabs}


@pytest.fixture
def base_tabs() -> RawTabs:
    """A fresh copy of the valid base dataset, safe to mutate."""
    return load_fixture("base_valid.json")


# Mutation helpers. Each changes ``tabs`` in place and returns it. Row numbers are
# sheet row numbers (header = row 1), matching the validation report (spec §7.3).


def _col(tabs: RawTabs, tab: str, header: str) -> int:
    return tabs[tab][0].index(header)


def set_cell(tabs: RawTabs, tab: str, row: int, header: str, value: object) -> RawTabs:
    """Set the cell at sheet ``row`` under ``header``."""
    tabs[tab][row - 1][_col(tabs, tab, header)] = value
    return tabs


def drop_column(tabs: RawTabs, tab: str, header: str) -> RawTabs:
    """Remove the column ``header`` from every row of ``tab``."""
    i = _col(tabs, tab, header)
    for r in tabs[tab]:
        del r[i]
    return tabs


def rename_header(tabs: RawTabs, tab: str, old: str, new: str) -> RawTabs:
    """Change the header text ``old`` to ``new``."""
    tabs[tab][0][_col(tabs, tab, old)] = new
    return tabs


def add_column(tabs: RawTabs, tab: str, header: str, fill: object = "") -> RawTabs:
    """Append an extra column ``header`` with ``fill`` in every data row."""
    tabs[tab][0].append(header)
    for r in tabs[tab][1:]:
        r.append(fill)
    return tabs


def append_row(tabs: RawTabs, tab: str, values: dict[str, object]) -> RawTabs:
    """Append a data row; headers missing from ``values`` are blank."""
    tabs[tab].append([values.get(h, "") for h in tabs[tab][0]])
    return tabs


def insert_blank_row(tabs: RawTabs, tab: str, row: int) -> RawTabs:
    """Insert a fully blank row so it becomes sheet ``row``."""
    tabs[tab].insert(row - 1, [""] * len(tabs[tab][0]))
    return tabs


def clear_data_rows(tabs: RawTabs, tab: str) -> RawTabs:
    """Keep only the header row of ``tab``."""
    del tabs[tab][1:]
    return tabs
