"""Shopify sales dashboard data source. Implements specs/001-data-source.md."""

from shopify_dashboard.errors import DataSourceError
from shopify_dashboard.loader import LoadResult, load_data

__all__ = ["DataSourceError", "LoadResult", "load_data"]
