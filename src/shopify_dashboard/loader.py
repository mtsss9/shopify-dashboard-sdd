"""The data-source pipeline. Implements specs/001-data-source.md §7, §8 and §9."""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from shopify_dashboard.calculations import enrich_customers, enrich_orders, enrich_products
from shopify_dashboard.config import load_config
from shopify_dashboard.parsing import ParsedRow, parse_tabs
from shopify_dashboard.report import ValidationReport
from shopify_dashboard.schema import COLUMNS, TABS
from shopify_dashboard.sheets_client import GspreadSheetsClient, SheetsClient
from shopify_dashboard.validation import validate_all

DTYPES = {
    "str": "string",
    "enum": "string",
    "int": "int64",
    "decimal": "float64",
    "date": "datetime64[ns]",
}
"""Output dtype per column kind. Implements specs/001-data-source.md §3 and §9."""


@dataclass
class LoadResult:
    """Clean, typed DataFrames plus the validation report. Implements spec 001 §9."""

    orders: pd.DataFrame
    products: pd.DataFrame
    customers: pd.DataFrame
    report: ValidationReport


def load_data(client: SheetsClient | None = None, today: date | None = None) -> LoadResult:
    """Fetch, parse, validate, recompute and convert. Implements spec 001 §7, §8 and §9.

    ``client`` defaults to the real Google Sheets adapter built from the environment;
    ``today`` defaults to the current local date (§7.4). The fetch runs exactly once.
    Raises ``DataSourceError`` and never returns partial data.
    """
    if client is None:
        client = GspreadSheetsClient(load_config())
    today = date.today() if today is None else today

    tabs = parse_tabs(client.fetch_tabs(TABS))
    valid, report = validate_all(tabs, today)
    orders = enrich_orders(valid["Orders"], valid["Products"])
    products = enrich_products(valid["Products"], orders)
    customers = enrich_customers(valid["Customers"], orders)
    frames = to_frames({"Orders": orders, "Products": products, "Customers": customers})
    return LoadResult(frames["Orders"], frames["Products"], frames["Customers"], report)


def to_frames(rows: dict[str, list[ParsedRow]]) -> dict[str, pd.DataFrame]:
    """Rename to snake_case in spec §9 order and set dtypes. Implements spec 001 §9.

    Columns come only from ``schema.COLUMNS``, so extra sheet columns never appear.
    Dates are normalised to midnight.
    """
    return {tab: _to_frame(tab, rows[tab]) for tab in rows}


def _to_frame(tab: str, rows: list[ParsedRow]) -> pd.DataFrame:
    specs = COLUMNS[tab]
    frame = pd.DataFrame(
        {s.name: [r.cells[s.header] for r in rows] for s in specs},
        columns=[s.name for s in specs],
    )
    for s in specs:
        if s.kind == "date":
            frame[s.name] = pd.to_datetime(frame[s.name]).dt.normalize().astype(DTYPES["date"])
        else:
            frame[s.name] = frame[s.name].astype(DTYPES[s.kind])
    return frame
