"""Tab and column definitions. Implements specs/001-data-source.md §3.1, §4–6 and §9.

``COLUMNS`` is the single place that maps sheet headers to snake_case output names.
Tuple order is the output column order (spec §9).
"""

from dataclasses import dataclass
from typing import Literal

Kind = Literal["str", "int", "decimal", "date", "enum"]

TABS: tuple[str, ...] = ("Products", "Customers", "Orders")
"""Tabs in validation order. Implements specs/001-data-source.md §7."""

STATUSES: tuple[str, ...] = ("Fulfilled", "Unfulfilled", "Refunded")
SALES_CHANNELS: tuple[str, ...] = ("Online Store", "Shop App", "POS", "Instagram")
CATEGORIES: tuple[str, ...] = ("Apparel", "Accessories", "Home", "Outdoor")
PROVINCES: tuple[str, ...] = (
    "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT",
)  # fmt: skip

UNIQUE_KEYS: dict[str, str] = {
    "Orders": "Order ID",
    "Products": "SKU",
    "Customers": "Customer ID",
}

ORDER_ID_PATTERN = r"#\d+"
CUSTOMER_ID_PATTERN = r"C-\d+"
SKU_PATTERN = r"SKU-\d{4}"


@dataclass(frozen=True)
class ColumnSpec:
    """One sheet column. Implements specs/001-data-source.md §3–6 and §9.

    ``pattern`` is a regex the whole trimmed value must match (``re.fullmatch``).
    """

    header: str
    name: str
    kind: Kind
    required: bool = True
    calculated: bool = False
    allowed: tuple[str, ...] | None = None
    pattern: str | None = None


COLUMNS: dict[str, tuple[ColumnSpec, ...]] = {
    "Orders": (
        ColumnSpec("Order ID", "order_id", "str", pattern=ORDER_ID_PATTERN),
        ColumnSpec("Order Date", "order_date", "date"),
        ColumnSpec("Customer ID", "customer_id", "str", pattern=CUSTOMER_ID_PATTERN),
        ColumnSpec("SKU", "sku", "str", pattern=SKU_PATTERN),
        ColumnSpec("Product Name", "product_name", "str", calculated=True),
        ColumnSpec("Category", "category", "str", calculated=True),
        ColumnSpec("Quantity", "quantity", "int"),
        ColumnSpec("Unit Price (CAD)", "unit_price_cad", "decimal"),
        ColumnSpec("Discount (CAD)", "discount_cad", "decimal"),
        ColumnSpec("Line Total (CAD)", "line_total_cad", "decimal", calculated=True),
        ColumnSpec("Status", "status", "enum", allowed=STATUSES),
        ColumnSpec("Sales Channel", "sales_channel", "enum", allowed=SALES_CHANNELS),
    ),
    "Products": (
        ColumnSpec("SKU", "sku", "str", pattern=SKU_PATTERN),
        ColumnSpec("Product Name", "product_name", "str"),
        ColumnSpec("Category", "category", "enum", allowed=CATEGORIES),
        ColumnSpec("Price (CAD)", "price_cad", "decimal"),
        ColumnSpec("Unit Cost (CAD)", "unit_cost_cad", "decimal"),
        ColumnSpec("Inventory", "inventory", "int"),
        ColumnSpec("Margin %", "margin_pct", "decimal", calculated=True),
        ColumnSpec("Units Sold", "units_sold", "int", calculated=True),
        ColumnSpec("Revenue (CAD)", "revenue_cad", "decimal", calculated=True),
    ),
    "Customers": (
        ColumnSpec("Customer ID", "customer_id", "str", pattern=CUSTOMER_ID_PATTERN),
        ColumnSpec("Name", "name", "str"),
        ColumnSpec("Email", "email", "str"),
        ColumnSpec("City", "city", "str"),
        ColumnSpec("Province", "province", "enum", allowed=PROVINCES),
        ColumnSpec("Customer Since", "customer_since", "date"),
        ColumnSpec("Orders", "order_count", "int", calculated=True),
        ColumnSpec("Total Spent (CAD)", "total_spent_cad", "decimal", calculated=True),
    ),
}
