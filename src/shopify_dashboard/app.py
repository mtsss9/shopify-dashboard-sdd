"""Streamlit Data Explorer. Implements specs/003-dashboard-ui.md §1–4 and §6.

A thin presentation layer: all logic lives in cache, display, filters and quality.
From the data layer, only ``load_data`` (and its ``DataSourceError``) is used (§6.1).
Run with ``run.ps1``, which puts ``src`` on ``PYTHONPATH`` (plan 003 decision U1).
"""

import streamlit as st

from shopify_dashboard import DataSourceError, load_data
from shopify_dashboard.cache import LoadCache
from shopify_dashboard.display import ERROR_HEADINGS, error_text
from shopify_dashboard.quality import banner_messages

TAB_LABELS = ["Orders", "Products", "Customers", "Data quality"]


@st.cache_resource
def _load_cache() -> LoadCache:
    """One LoadCache per server process, shared by all sessions (spec §1, plan §3)."""
    return LoadCache()


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
