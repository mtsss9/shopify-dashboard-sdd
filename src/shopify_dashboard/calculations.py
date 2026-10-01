"""Recomputed calculated columns. Implements specs/001-data-source.md §3.1.

The sheet's calculated values are never used in the output. Refunded orders are left
out of every revenue and units figure (CLAUDE.md business rules). Nothing is rounded
here; display rounding belongs to the UI (spec 003 §5, plan D9).
"""

from typing import NamedTuple

from shopify_dashboard.parsing import ParsedRow

REFUNDED = "Refunded"


class ProductStats(NamedTuple):
    """Units sold and revenue for one SKU. Implements specs/001-data-source.md §3.1."""

    units_sold: int
    revenue: float


class CustomerStats(NamedTuple):
    """Order count and total spent for one customer. Implements specs/001-data-source.md §3.1."""

    order_count: int
    total_spent: float


def line_total(quantity: int, unit_price: float, discount: float) -> float:
    """Quantity × Unit Price − Discount. Implements specs/001-data-source.md §3.1."""
    return quantity * unit_price - discount


def margin_pct(price: float, unit_cost: float) -> float:
    """(Price − Unit Cost) ÷ Price as a fraction; 0 when Price is 0. Implements spec 001 §3.1."""
    return 0.0 if price == 0 else (price - unit_cost) / price


def _order_total(order: ParsedRow) -> float:
    c = order.cells
    return line_total(c["Quantity"], c["Unit Price (CAD)"], c["Discount (CAD)"])  # type: ignore[arg-type]


def _counted(orders: list[ParsedRow]) -> list[ParsedRow]:
    return [o for o in orders if o.cells["Status"] != REFUNDED]


def enrich_orders(orders: list[ParsedRow], products: list[ParsedRow]) -> list[ParsedRow]:
    """Set Product Name and Category from Products, and the recomputed Line Total.

    Implements specs/001-data-source.md §3.1 and decision D3. Returns new rows.
    """
    lookup = {p.cells["SKU"]: p.cells for p in products}
    enriched = []
    for order in orders:
        product = lookup[order.cells["SKU"]]
        cells = {
            **order.cells,
            "Product Name": product["Product Name"],
            "Category": product["Category"],
            "Line Total (CAD)": _order_total(order),
        }
        enriched.append(ParsedRow(order.sheet_row, cells))
    return enriched


def product_stats(orders: list[ParsedRow], products: list[ParsedRow]) -> dict[object, ProductStats]:
    """Units sold and revenue per SKU from non-Refunded orders. Implements spec 001 §3.1.

    Every product is present; SKUs with no counted orders get 0.
    """
    units = {p.cells["SKU"]: 0 for p in products}
    revenue = {sku: 0.0 for sku in units}
    for order in _counted(orders):
        sku = order.cells["SKU"]
        units[sku] += order.cells["Quantity"]  # type: ignore[operator]
        revenue[sku] += _order_total(order)
    return {sku: ProductStats(units[sku], revenue[sku]) for sku in units}


def customer_stats(
    orders: list[ParsedRow], customers: list[ParsedRow]
) -> dict[object, CustomerStats]:
    """Order count and total spent per customer from non-Refunded orders. Implements §3.1.

    Every customer is present; customers with no counted orders get 0.
    """
    counts = {c.cells["Customer ID"]: 0 for c in customers}
    spent = {cid: 0.0 for cid in counts}
    for order in _counted(orders):
        cid = order.cells["Customer ID"]
        counts[cid] += 1
        spent[cid] += _order_total(order)
    return {cid: CustomerStats(counts[cid], spent[cid]) for cid in counts}


def enrich_products(products: list[ParsedRow], orders: list[ParsedRow]) -> list[ParsedRow]:
    """Set Margin %, Units Sold and Revenue (CAD). Implements specs/001-data-source.md §3.1."""
    stats = product_stats(orders, products)
    enriched = []
    for product in products:
        c = product.cells
        s = stats[c["SKU"]]
        cells = {
            **c,
            "Margin %": margin_pct(c["Price (CAD)"], c["Unit Cost (CAD)"]),  # type: ignore[arg-type]
            "Units Sold": s.units_sold,
            "Revenue (CAD)": s.revenue,
        }
        enriched.append(ParsedRow(product.sheet_row, cells))
    return enriched


def enrich_customers(customers: list[ParsedRow], orders: list[ParsedRow]) -> list[ParsedRow]:
    """Set Orders and Total Spent (CAD). Implements specs/001-data-source.md §3.1."""
    stats = customer_stats(orders, customers)
    enriched = []
    for customer in customers:
        s = stats[customer.cells["Customer ID"]]
        cells = {**customer.cells, "Orders": s.order_count, "Total Spent (CAD)": s.total_spent}
        enriched.append(ParsedRow(customer.sheet_row, cells))
    return enriched
