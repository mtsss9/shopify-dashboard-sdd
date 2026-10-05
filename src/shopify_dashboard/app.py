"""Streamlit Data Explorer. Implements specs/003-dashboard-ui.md §1–4 and §6.

A thin presentation layer: all logic lives in cache, display, filters and quality.
From the data layer, only ``load_data`` (and its ``DataSourceError``) is used (§6.1).
Run with ``run.ps1``, which puts ``src`` on ``PYTHONPATH`` (plan 003 decision U1).
"""

from datetime import date

import pandas as pd
import streamlit as st

from shopify_dashboard import DataSourceError, filters, load_data
from shopify_dashboard.cache import LoadCache
from shopify_dashboard.display import (
    ERROR_HEADINGS,
    error_text,
    number_formats,
    row_count_text,
    table_view,
)
from shopify_dashboard.quality import banner_messages

TAB_LABELS = ["Orders", "Products", "Customers", "Data quality"]
# Wide picker bounds, so a date kept across Refresh is never outside them. (A comment,
# not a string: Streamlit "magic" would render a bare module-level string on the page.)
DATE_BOUNDS = (date(1900, 1, 1), date(2100, 12, 31))


@st.cache_resource
def _load_cache() -> LoadCache:
    """One LoadCache per server process, shared by all sessions (spec §1, plan §3)."""
    return LoadCache()


def _multiselect(label: str, df: pd.DataFrame, column: str, key: str) -> list[str]:
    """A filter multiselect whose kept selection is pruned to the current options (§6.4)."""
    opts = filters.options(df, column)
    if key in st.session_state:
        st.session_state[key] = filters.prune_selection(st.session_state[key], opts)
    return st.multiselect(label, opts, key=key)


def _date_input(label: str, default: date, key: str) -> date:
    """A date picker that starts at ``default`` and keeps the user's choice (§6.4, U2)."""
    if key not in st.session_state:
        st.session_state[key] = default
    return st.date_input(label, key=key, min_value=DATE_BOUNDS[0], max_value=DATE_BOUNDS[1])


def _show_table(tab: str, filtered: pd.DataFrame) -> None:
    """The filtered table with numeric money and Margin % columns (§5, §6.3, U11)."""
    config = {h: st.column_config.NumberColumn(format=f) for h, f in number_formats(tab).items()}
    st.dataframe(table_view(tab, filtered), hide_index=True, column_config=config)


def _orders_tab(df: pd.DataFrame) -> None:
    """Orders: count, date range and three multiselects, table. Implements §6.3 and §6.4."""
    count = st.empty()
    default = filters.default_date_range(df)
    if default is not None:
        start = _date_input("Start date", default[0], "orders_start")
        end = _date_input("End date", default[1], "orders_end")
        if start > end:
            st.warning("Start date is after end date.")
    categories = _multiselect("Category", df, "category", "orders_category")
    statuses = _multiselect("Status", df, "status", "orders_status")
    channels = _multiselect("Sales Channel", df, "sales_channel", "orders_channel")
    if default is None:
        filtered = df.copy(deep=True)  # empty tab: nothing to filter (U6)
    else:
        filtered = filters.filter_orders(df, start, end, categories, statuses, channels)
    count.markdown(row_count_text(len(filtered), len(df)))
    _show_table("Orders", filtered)


def _products_tab(df: pd.DataFrame) -> None:
    """Products: count, Category filter, table. Implements §6.3 and §6.4."""
    count = st.empty()
    filtered = filters.filter_products(
        df, _multiselect("Category", df, "category", "products_category")
    )
    count.markdown(row_count_text(len(filtered), len(df)))
    _show_table("Products", filtered)


def _customers_tab(df: pd.DataFrame) -> None:
    """Customers: count, Province filter, table. Implements §6.3 and §6.4."""
    count = st.empty()
    filtered = filters.filter_customers(
        df, _multiselect("Province", df, "province", "customers_province")
    )
    count.markdown(row_count_text(len(filtered), len(df)))
    _show_table("Customers", filtered)


st.set_page_config(page_title="Shopify Data Explorer")
st.title("Shopify Data Explorer")

cache = _load_cache()
if st.button("Refresh data"):
    cache.clear()

try:
    result = cache.get(load_data)
except DataSourceError as error:
    st.error(error_text(ERROR_HEADINGS[error.category], error.message))
    st.stop()

for message in banner_messages(result.report):
    st.warning(message)

orders_tab, products_tab, customers_tab, quality_tab = st.tabs(TAB_LABELS)
with orders_tab:
    _orders_tab(result.orders)
with products_tab:
    _products_tab(result.products)
with customers_tab:
    _customers_tab(result.customers)
