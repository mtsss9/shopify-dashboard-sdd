"""Tests for calculations.py. Implements specs/001-data-source.md §3.1 (AC-12, AC-14, AC-19)."""

import pytest

from conftest import TODAY, append_row, load_fixture, set_cell
from shopify_dashboard.calculations import (
    CustomerStats,
    ProductStats,
    customer_stats,
    enrich_customers,
    enrich_orders,
    enrich_products,
    line_total,
    margin_pct,
    product_stats,
)
from shopify_dashboard.parsing import ParsedRow, parse_tabs
from shopify_dashboard.validation import validate_all


def validated(tabs: dict) -> dict[str, list[ParsedRow]]:
    valid, _ = validate_all(parse_tabs(tabs), TODAY)
    return valid


def sheet_values(tab: str, key: str, headers: list[str]) -> dict[str, list[object]]:
    """The sheet's own calculated values from the base fixture, keyed by ID."""
    rows = load_fixture("base_valid.json")[tab]
    header_row = rows[0]
    return {r[header_row.index(key)]: [r[header_row.index(h)] for h in headers] for r in rows[1:]}


# --- Unit functions --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("quantity", "unit_price", "discount", "expected"),
    [(2, 20.0, 0.0, 40.0), (4, 18.0, 2.5, 69.5), (1, 35.0, 5.0, 30.0), (3, 18.0, 0.0, 54.0)],
)
def test_line_total(quantity: int, unit_price: float, discount: float, expected: float) -> None:
    assert line_total(quantity, unit_price, discount) == pytest.approx(expected)


def test_margin_for_price_20_cost_5() -> None:
    """AC-19."""
    assert margin_pct(20.0, 5.0) == 0.75


def test_margin_is_a_fraction_and_unrounded() -> None:
    assert margin_pct(18.0, 6.3) == pytest.approx(0.65)
    assert margin_pct(3.0, 1.0) == pytest.approx(2 / 3)  # no rounding in the loader (D9)


def test_margin_is_zero_when_price_is_zero() -> None:
    assert margin_pct(0.0, 5.0) == 0.0


# --- Orders ----------------------------------------------------------------------------


def test_enrich_orders_recomputes_line_total(base_tabs: dict) -> None:
    """AC-12: the output holds the recomputed value, not the sheet's 40.05."""
    set_cell(base_tabs, "Orders", 2, "Line Total (CAD)", 40.05)
    valid = validated(base_tabs)
    enriched = enrich_orders(valid["Orders"], valid["Products"])
    assert enriched[0].cells["Line Total (CAD)"] == 40.0


def test_enrich_orders_uses_the_products_lookup(base_tabs: dict) -> None:
    """D3: the lookup overrides the sheet's Product Name and Category."""
    set_cell(base_tabs, "Orders", 2, "Product Name", "Something Else")
    set_cell(base_tabs, "Orders", 2, "Category", "Home")
    valid = validated(base_tabs)
    first = enrich_orders(valid["Orders"], valid["Products"])[0].cells
    assert (first["Product Name"], first["Category"]) == ("Classic Tee", "Apparel")


def test_enrich_orders_fills_blank_and_unreadable_cells(base_tabs: dict) -> None:
    set_cell(base_tabs, "Orders", 2, "Line Total (CAD)", "")
    set_cell(base_tabs, "Orders", 3, "Product Name", "#N/A")
    valid = validated(base_tabs)
    enriched = enrich_orders(valid["Orders"], valid["Products"])
    assert enriched[0].cells["Line Total (CAD)"] == 40.0
    assert enriched[1].cells["Product Name"] == "Canvas Tote"


def test_enrich_orders_matches_every_sheet_line_total(base_tabs: dict) -> None:
    valid = validated(base_tabs)
    enriched = enrich_orders(valid["Orders"], valid["Products"])
    sheet = sheet_values("Orders", "Order ID", ["Line Total (CAD)"])
    for row in enriched:
        assert row.cells["Line Total (CAD)"] == pytest.approx(sheet[row.cells["Order ID"]][0])


def test_enrich_orders_does_not_mutate_input(base_tabs: dict) -> None:
    set_cell(base_tabs, "Orders", 2, "Line Total (CAD)", 40.05)
    valid = validated(base_tabs)
    enrich_orders(valid["Orders"], valid["Products"])
    assert valid["Orders"][0].cells["Line Total (CAD)"] == 40.05


# --- Stats -----------------------------------------------------------------------------


def test_product_stats_exclude_refunded(base_tabs: dict) -> None:
    """AC-14: #1004 (SKU-0001) and #1007 (SKU-0004) are Refunded."""
    valid = validated(base_tabs)
    assert product_stats(valid["Orders"], valid["Products"]) == {
        "SKU-0001": ProductStats(2, pytest.approx(40.0)),
        "SKU-0002": ProductStats(3, pytest.approx(95.0)),
        "SKU-0003": ProductStats(7, pytest.approx(123.5)),
        "SKU-0004": ProductStats(2, pytest.approx(70.0)),
    }


def test_customer_stats_exclude_refunded(base_tabs: dict) -> None:
    """AC-14."""
    valid = validated(base_tabs)
    assert customer_stats(valid["Orders"], valid["Customers"]) == {
        "C-101": CustomerStats(2, pytest.approx(94.0)),
        "C-102": CustomerStats(2, pytest.approx(100.0)),
        "C-103": CustomerStats(2, pytest.approx(134.5)),
    }


def test_stats_use_the_recomputed_line_total(base_tabs: dict) -> None:
    """Revenue is never taken from the sheet's Line Total (spec §3.1)."""
    set_cell(base_tabs, "Orders", 2, "Line Total (CAD)", 999)  # warning only; row kept
    valid = validated(base_tabs)
    assert product_stats(valid["Orders"], valid["Products"])["SKU-0001"].revenue == 40.0


def test_items_with_no_orders_get_zero(base_tabs: dict) -> None:
    append_row(
        base_tabs,
        "Products",
        {"SKU": "SKU-0005", "Product Name": "Wool Hat", "Category": "Apparel",
         "Price (CAD)": 25, "Unit Cost (CAD)": 9, "Inventory": 10},
    )  # fmt: skip
    append_row(
        base_tabs,
        "Customers",
        {"Customer ID": "C-104", "Name": "Ana Lima", "Email": "ana@example.com",
         "City": "Halifax", "Province": "NS", "Customer Since": "2026-01-02"},
    )  # fmt: skip
    valid = validated(base_tabs)
    assert product_stats(valid["Orders"], valid["Products"])["SKU-0005"] == ProductStats(0, 0.0)
    assert customer_stats(valid["Orders"], valid["Customers"])["C-104"] == CustomerStats(0, 0.0)


def test_only_refunded_orders_give_zero(base_tabs: dict) -> None:
    for row in range(2, 10):
        set_cell(base_tabs, "Orders", row, "Status", "Refunded")
    valid = validated(base_tabs)
    stats = product_stats(valid["Orders"], valid["Products"])
    assert all(s == ProductStats(0, 0.0) for s in stats.values())


# --- Enriching Products and Customers --------------------------------------------------


def test_enriched_products_match_the_sheet(base_tabs: dict) -> None:
    """AC-14 and AC-19: recomputed values equal the fixture's sheet values."""
    valid = validated(base_tabs)
    headers = ["Margin %", "Units Sold", "Revenue (CAD)"]
    sheet = sheet_values("Products", "SKU", headers)
    for row in enrich_products(valid["Products"], valid["Orders"]):
        expected = sheet[row.cells["SKU"]]
        assert [row.cells[h] for h in headers] == pytest.approx(expected, abs=0.01)
    first = enrich_products(valid["Products"], valid["Orders"])[0].cells
    assert first["Margin %"] == 0.75 and isinstance(first["Units Sold"], int)


def test_enriched_customers_match_the_sheet(base_tabs: dict) -> None:
    """AC-14."""
    valid = validated(base_tabs)
    headers = ["Orders", "Total Spent (CAD)"]
    sheet = sheet_values("Customers", "Customer ID", headers)
    for row in enrich_customers(valid["Customers"], valid["Orders"]):
        expected = sheet[row.cells["Customer ID"]]
        assert [row.cells[h] for h in headers] == pytest.approx(expected, abs=0.01)


def test_enriched_products_replace_blank_and_unreadable_sheet_values(base_tabs: dict) -> None:
    set_cell(base_tabs, "Products", 2, "Margin %", "")
    set_cell(base_tabs, "Products", 3, "Units Sold", "#REF!")
    valid = validated(base_tabs)
    rows = enrich_products(valid["Products"], valid["Orders"])
    assert rows[0].cells["Margin %"] == 0.75
    assert rows[1].cells["Units Sold"] == 3


def test_enrich_keeps_other_cells_and_row_numbers(base_tabs: dict) -> None:
    valid = validated(base_tabs)
    rows = enrich_customers(valid["Customers"], valid["Orders"])
    assert [r.sheet_row for r in rows] == [2, 3, 4]
    assert rows[0].cells["Email"] == "jane@example.com"
