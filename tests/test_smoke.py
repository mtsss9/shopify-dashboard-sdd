"""Smoke tests for the T1 groundwork: fixtures, FakeSheetsClient and mutation helpers."""

from datetime import date

import pytest

from conftest import (
    TABS,
    TODAY,
    FakeSheetsClient,
    add_column,
    append_row,
    clear_data_rows,
    drop_column,
    insert_blank_row,
    load_fixture,
    rename_header,
    serial,
    set_cell,
)


def test_base_fixture_loads_into_fake(base_tabs: dict) -> None:
    fake = FakeSheetsClient(base_tabs)
    raw = fake.fetch_tabs(TABS)
    assert set(raw) == set(TABS)
    assert {tab: len(rows) - 1 for tab, rows in raw.items()} == {
        "Orders": 8,
        "Products": 4,
        "Customers": 3,
    }
    assert raw["Orders"][0][0] == "Order ID"
    assert fake.calls == 1


def test_threshold_fixture_has_100_orders() -> None:
    assert len(load_fixture("threshold_100_orders.json")["Orders"]) == 101


def test_fake_returns_deep_copy(base_tabs: dict) -> None:
    fake = FakeSheetsClient(base_tabs)
    fake.fetch_tabs(TABS)["Orders"][1][0] = "#9999"
    assert fake.fetch_tabs(TABS)["Orders"][1][0] == "#1001"
    assert fake.calls == 2


def test_fake_returns_only_requested_existing_tabs(base_tabs: dict) -> None:
    del base_tabs["Customers"]
    raw = FakeSheetsClient(base_tabs).fetch_tabs(TABS)
    assert set(raw) == {"Orders", "Products"}


def test_fake_raises_configured_error(base_tabs: dict) -> None:
    fake = FakeSheetsClient(base_tabs, error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        fake.fetch_tabs(TABS)
    assert fake.calls == 1


def test_serial_uses_sheets_epoch() -> None:
    assert date(2026, 6, 1) == TODAY
    assert serial(TODAY) == 46174
    assert serial(date(1899, 12, 30)) == 0


def test_base_tabs_is_a_fresh_copy_each_time(base_tabs: dict) -> None:
    assert base_tabs == load_fixture("base_valid.json")
    base_tabs["Orders"].clear()
    assert load_fixture("base_valid.json")["Orders"]


def test_set_cell_uses_sheet_row_numbers(base_tabs: dict) -> None:
    set_cell(base_tabs, "Orders", 2, "Status", "Shipped")
    assert base_tabs["Orders"][1][10] == "Shipped"


def test_column_helpers(base_tabs: dict) -> None:
    drop_column(base_tabs, "Orders", "Status")
    assert "Status" not in base_tabs["Orders"][0]
    assert all(len(r) == 11 for r in base_tabs["Orders"])

    rename_header(base_tabs, "Products", "SKU", " SKU ")
    assert base_tabs["Products"][0][0] == " SKU "

    add_column(base_tabs, "Customers", "Notes", "x")
    assert base_tabs["Customers"][0][-1] == "Notes"
    assert all(r[-1] == "x" for r in base_tabs["Customers"][1:])


def test_row_helpers(base_tabs: dict) -> None:
    append_row(base_tabs, "Products", {"SKU": "SKU-0005", "Price (CAD)": 9})
    new = base_tabs["Products"][-1]
    assert new[0] == "SKU-0005" and new[3] == 9 and new[1] == ""

    insert_blank_row(base_tabs, "Orders", 3)
    assert base_tabs["Orders"][2] == [""] * 12
    assert base_tabs["Orders"][3][0] == "#1002"

    clear_data_rows(base_tabs, "Customers")
    assert len(base_tabs["Customers"]) == 1
