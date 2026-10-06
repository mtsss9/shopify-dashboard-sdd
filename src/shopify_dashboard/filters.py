"""Filter logic for the Data Explorer tables. Implements specs/003-dashboard-ui.md §6.4.

Pure pandas with no Streamlit import. Every filter returns a new DataFrame and leaves
its input unchanged; ``app.py`` only builds the widgets and calls these functions.
"""

from collections.abc import Sequence
from datetime import date

import pandas as pd


def options(df: pd.DataFrame, column: str) -> list[str]:
    """Return the distinct non-missing values of ``column``, sorted A–Z.

    Implements specs/003-dashboard-ui.md §6.4 (options come from the loaded data).
    """
    return sorted(str(v) for v in df[column].dropna().unique())


def default_date_range(df: pd.DataFrame, column: str = "order_date") -> tuple[date, date] | None:
    """Return the earliest and latest date in ``column``, or None for an empty frame.

    Implements specs/003-dashboard-ui.md §6.4 (plan 003 decision U6).
    """
    dates = df[column].dropna()
    if dates.empty:
        return None
    return dates.min().date(), dates.max().date()


def prune_selection(selected: Sequence[str], available: Sequence[str]) -> list[str]:
    """Keep the selected values that are still available, in their original order.

    Implements specs/003-dashboard-ui.md §6.4 (selections kept across refresh).
    """
    allowed = set(available)
    return [v for v in selected if v in allowed]


def filter_values(df: pd.DataFrame, column: str, selected: Sequence[str]) -> pd.DataFrame:
    """Keep rows whose ``column`` is one of ``selected``; an empty selection keeps every row.

    Implements specs/003-dashboard-ui.md §6.4.
    """
    if not selected:
        return df.copy(deep=True)
    return df[df[column].isin(list(selected))].copy(deep=True)


def filter_date_range(df: pd.DataFrame, column: str, start: date, end: date) -> pd.DataFrame:
    """Keep rows whose ``column`` date is between ``start`` and ``end``, both inclusive.

    Implements specs/003-dashboard-ui.md §6.4. ``start`` after ``end`` keeps no rows.
    """
    days = pd.to_datetime(df[column]).dt.normalize()
    mask = (days >= pd.Timestamp(start)) & (days <= pd.Timestamp(end))
    return df[mask].copy(deep=True)


def filter_orders(
    df: pd.DataFrame,
    start: date,
    end: date,
    categories: Sequence[str],
    statuses: Sequence[str],
    channels: Sequence[str],
) -> pd.DataFrame:
    """Apply the Orders filters, combined with AND. Implements specs/003-dashboard-ui.md §6.4."""
    out = filter_date_range(df, "order_date", start, end)
    out = filter_values(out, "category", categories)
    out = filter_values(out, "status", statuses)
    return filter_values(out, "sales_channel", channels)


def filter_products(df: pd.DataFrame, categories: Sequence[str]) -> pd.DataFrame:
    """Apply the Products Category filter. Implements specs/003-dashboard-ui.md §6.4."""
    return filter_values(df, "category", categories)


def filter_customers(df: pd.DataFrame, provinces: Sequence[str]) -> pd.DataFrame:
    """Apply the Customers Province filter. Implements specs/003-dashboard-ui.md §6.4."""
    return filter_values(df, "province", provinces)
