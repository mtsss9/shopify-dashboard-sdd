"""Tests for schema.py. Implements specs/001-data-source.md §3.1, §4–6 and §9 (AC-16, unit)."""

import dataclasses
import re

import pytest

from conftest import load_fixture
from shopify_dashboard.schema import (
    CATEGORIES,
    COLUMNS,
    PROVINCES,
    SALES_CHANNELS,
    STATUSES,
    TABS,
    UNIQUE_KEYS,
)

# Copied from the spec §9 table, in order: (sheet header, output column).
SPEC_9 = {
    "Orders": [
        ("Order ID", "order_id"),
        ("Order Date", "order_date"),
        ("Customer ID", "customer_id"),
        ("SKU", "sku"),
        ("Product Name", "product_name"),
        ("Category", "category"),
        ("Quantity", "quantity"),
        ("Unit Price (CAD)", "unit_price_cad"),
        ("Discount (CAD)", "discount_cad"),
        ("Line Total (CAD)", "line_total_cad"),
        ("Status", "status"),
        ("Sales Channel", "sales_channel"),
    ],
    "Products": [
        ("SKU", "sku"),
        ("Product Name", "product_name"),
        ("Category", "category"),
        ("Price (CAD)", "price_cad"),
        ("Unit Cost (CAD)", "unit_cost_cad"),
        ("Inventory", "inventory"),
        ("Margin %", "margin_pct"),
        ("Units Sold", "units_sold"),
        ("Revenue (CAD)", "revenue_cad"),
    ],
    "Customers": [
        ("Customer ID", "customer_id"),
        ("Name", "name"),
        ("Email", "email"),
        ("City", "city"),
        ("Province", "province"),
        ("Customer Since", "customer_since"),
        ("Orders", "order_count"),
        ("Total Spent (CAD)", "total_spent_cad"),
    ],
}

# Spec §3.1: calculated columns per tab.
SPEC_CALCULATED = {
    "Orders": {"Product Name", "Category", "Line Total (CAD)"},
    "Products": {"Margin %", "Units Sold", "Revenue (CAD)"},
    "Customers": {"Orders", "Total Spent (CAD)"},
}

# Spec §4–6 "Type" column, with integer/decimal as the schema kinds int/decimal.
SPEC_KINDS = {
    "Orders": ["str", "date", "str", "str", "str", "str", "int", "decimal", "decimal",
               "decimal", "enum", "enum"],
    "Products": ["str", "str", "enum", "decimal", "decimal", "int", "decimal", "int", "decimal"],
    "Customers": ["str", "str", "str", "str", "enum", "date", "int", "decimal"],
}  # fmt: skip


def test_tabs_in_validation_order() -> None:
    assert TABS == ("Products", "Customers", "Orders")
    assert set(COLUMNS) == set(TABS)


@pytest.mark.parametrize("tab", SPEC_9)
def test_mapping_and_order_match_spec_9(tab: str) -> None:
    assert [(c.header, c.name) for c in COLUMNS[tab]] == SPEC_9[tab]


@pytest.mark.parametrize("tab", SPEC_9)
def test_calculated_flags_match_spec_3_1(tab: str) -> None:
    assert {c.header for c in COLUMNS[tab] if c.calculated} == SPEC_CALCULATED[tab]


@pytest.mark.parametrize("tab", SPEC_9)
def test_kinds_match_spec_types(tab: str) -> None:
    assert [c.kind for c in COLUMNS[tab]] == SPEC_KINDS[tab]


def test_every_column_is_required() -> None:
    assert all(c.required for cols in COLUMNS.values() for c in cols)


def test_enum_columns_carry_allowed_values() -> None:
    allowed = {(tab, c.header): c.allowed for tab, cols in COLUMNS.items() for c in cols}
    assert allowed[("Orders", "Status")] == STATUSES
    assert allowed[("Orders", "Sales Channel")] == SALES_CHANNELS
    assert allowed[("Products", "Category")] == CATEGORIES
    assert allowed[("Customers", "Province")] == PROVINCES
    for cols in COLUMNS.values():
        for c in cols:
            assert (c.kind == "enum") == (c.allowed is not None), c.header


def test_enum_values_match_spec() -> None:
    assert STATUSES == ("Fulfilled", "Unfulfilled", "Refunded")
    assert SALES_CHANNELS == ("Online Store", "Shop App", "POS", "Instagram")
    assert CATEGORIES == ("Apparel", "Accessories", "Home", "Outdoor")
    assert PROVINCES == (
        "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT",
    )  # fmt: skip


def test_unique_keys() -> None:
    assert UNIQUE_KEYS == {"Orders": "Order ID", "Products": "SKU", "Customers": "Customer ID"}


def _pattern(tab: str, header: str) -> str:
    (spec,) = [c for c in COLUMNS[tab] if c.header == header]
    assert spec.pattern is not None
    return spec.pattern


@pytest.mark.parametrize(
    ("tab", "header", "good", "bad"),
    [
        ("Orders", "Order ID", ["#1001", "#1"], ["1001", "#", "#10a", " #1001", "#1001 "]),
        ("Orders", "Customer ID", ["C-101", "C-1"], ["C101", "c-101", "C-", "C-1a"]),
        ("Orders", "SKU", ["SKU-0001"], ["SKU-001", "SKU-00001", "sku-0001", "SKU0001"]),
        ("Products", "SKU", ["SKU-9999"], ["SKU-12a4"]),
        ("Customers", "Customer ID", ["C-150"], ["C-"]),
    ],
)
def test_id_patterns(tab: str, header: str, good: list[str], bad: list[str]) -> None:
    pattern = _pattern(tab, header)
    assert all(re.fullmatch(pattern, v) for v in good)
    assert not any(re.fullmatch(pattern, v) for v in bad)


def test_only_id_columns_have_patterns() -> None:
    with_pattern = {(t, c.header) for t, cols in COLUMNS.items() for c in cols if c.pattern}
    assert with_pattern == {
        ("Orders", "Order ID"),
        ("Orders", "Customer ID"),
        ("Orders", "SKU"),
        ("Products", "SKU"),
        ("Customers", "Customer ID"),
    }


def test_column_spec_is_frozen() -> None:
    spec = COLUMNS["Orders"][0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.name = "changed"  # type: ignore[misc]


def test_base_fixture_headers_match_schema() -> None:
    tabs = load_fixture("base_valid.json")
    for tab in TABS:
        assert tabs[tab][0] == [c.header for c in COLUMNS[tab]]
