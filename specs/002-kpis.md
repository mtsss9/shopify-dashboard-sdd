# Spec 002: KPIs

**Status:** Draft
**Owner:** Tell
**Depends on:** 001-data-source
**Used by:** 003-dashboard-ui (Phase 2)

> Draft. The §9 questions were resolved on 2026-10-06; the spec is awaiting approval.

## 1. Goal

Define the sales KPIs and breakdowns that the dashboard shows in Phase 2, precisely enough that each one has one correct value for a given input and a worked example to test against.

The KPI logic is pure Python with no Streamlit imports (CLAUDE.md). Displaying, formatting and choosing which rows to pass in belong to spec 003.

## 2. Inputs

- KPI functions take the DataFrames returned by the spec 001 loader (spec 001 §9), using the snake_case output columns.
- The `orders` DataFrame passed in may be a subset, e.g. filtered by date range in the UI. A KPI is computed over exactly the rows it is given; the KPI functions do no date filtering of their own. Which rows the UI passes in is specified in spec 003 Phase 2. Decided intent (§9 Q8): the KPI view has its own date range, defaulting to all data, independent of each tab's filters.
- `products` is always the full loaded Products DataFrame. It is used only to look up `unit_cost_cad` by `sku`.
- KPI functions never change their inputs.

## 3. General rules

- **Currency:** all money values are CAD (CLAUDE.md).
- **Counted orders:** an order is *counted* when its `status` is not `Refunded`. `Fulfilled` and `Unfulfilled` orders are both counted. Refunded orders are left out of every revenue, units, discount, profit, order-count and customer figure (CLAUDE.md), and appear only in the refund rate (§4.6).
- **Revenue** of an order is its `line_total_cad`, which spec 001 has already recomputed as Quantity × Unit Price − Discount (CLAUDE.md, spec 001 §3.1).
- **One order, one line:** each order row has exactly one SKU (spec 001 §4), so an order count is a row count.
- **Precision:** money and ratios are returned unrounded as `float`. Rounding to 2 decimals for money happens only at display time (spec 003 §5). Ratios are fractions (0.25 = 25%); how they are displayed is for spec 003.
- **Counts** are returned as `int`.
- **Empty input:** with no counted orders, sums are `0.0`, counts are `0`, ratios are `None` (never a division by zero), and breakdowns are empty.
- **Module:** `src/shopify_dashboard/kpis.py`, with no Streamlit import.

## 4. Headline KPIs

| § | KPI | Formula (over counted orders unless stated) | Returns |
|---|---|---|---|
| 4.1 | Net revenue | Σ `line_total_cad` | CAD `float` |
| 4.2 | Orders | Number of counted orders | `int` |
| 4.3 | Units sold | Σ `quantity` | `int` |
| 4.4 | Average order value (AOV) | Net revenue ÷ Orders; `None` when Orders is 0 | CAD `float` or `None` |
| 4.5 | Discounts given | Σ `discount_cad` | CAD `float` |
| 4.6 | Refund rate | Refunded orders ÷ **all** orders passed in; `None` when no orders are passed in | fraction or `None` |
| 4.7 | Gross profit | Σ (`line_total_cad` − `quantity` × the product's `unit_cost_cad`) | CAD `float` |
| 4.8 | Gross margin | Gross profit ÷ Net revenue; `None` when Net revenue is 0 | fraction or `None` |
| 4.9 | Active customers | Number of distinct `customer_id` with at least one counted order | `int` |
| 4.10 | Repeat customer rate | Active customers with 2 or more counted orders ÷ Active customers; `None` when there are no active customers | fraction or `None` |

Notes:
- 4.7 uses the product's **current** `unit_cost_cad` from Products, since the sheet holds no cost per order (§9 Q4). Known limitation: if a product's cost changes, gross profit for its past orders changes too. Every counted order's SKU exists in Products, because spec 001 drops orders with an unknown SKU.
- 4.7 can be negative for an order sold below cost; that is reported as is.

## 5. Breakdowns

All breakdowns use counted orders only. A group appears only if it has at least one counted order.

| § | Breakdown | Group by | Columns returned | Sort |
|---|---|---|---|---|
| 5.1 | Revenue by sales channel | `sales_channel` | `sales_channel`, `revenue_cad`, `orders` | `revenue_cad` descending, then `sales_channel` A–Z |
| 5.2 | Revenue by category | `category` | `category`, `revenue_cad`, `units_sold` | `revenue_cad` descending, then `category` A–Z |
| 5.3 | Revenue by month | calendar month of `order_date`, as text `YYYY-MM` | `month`, `revenue_cad`, `orders` | `month` ascending |
| 5.4 | Top products | `sku` | `sku`, `product_name`, `revenue_cad`, `units_sold` | `revenue_cad` descending, then `sku` A–Z; first *N* rows |
| 5.5 | Top customers | `customer_id` | `customer_id`, `name`, `revenue_cad`, `orders` | `revenue_cad` descending, then `customer_id` A–Z; first *N* rows |

- Each breakdown is returned as a new pandas DataFrame with exactly the columns listed, in that order, and a fresh 0-based index.
- *N* is a parameter with default **5**. With fewer groups than *N*, all groups are returned.
- 5.3 lists every calendar month from the first to the last month that has a counted order, including months in between with no counted orders, which show `0.0` and `0`.
- 5.5 takes `name` from the Customers DataFrame. It never returns `email` (CLAUDE.md: never log full customer emails).

## 6. Worked example

All criteria in §8 use this fixture (as loader output, so calculated columns are already recomputed).

**Products**

| sku | product_name | category | unit_cost_cad |
|---|---|---|---|
| SKU-0001 | Classic Tee | Apparel | 5 |
| SKU-0002 | Canvas Tote | Accessories | 12 |
| SKU-0003 | Ceramic Mug | Home | 6 |

**Customers**

| customer_id | name |
|---|---|
| C-1 | Ana |
| C-2 | Ben |
| C-3 | Cy |
| C-4 | Dee |

**Orders**

| order_id | order_date | customer_id | sku | quantity | unit_price_cad | discount_cad | line_total_cad | status | sales_channel |
|---|---|---|---|---|---|---|---|---|---|
| #1 | 2026-01-10 | C-1 | SKU-0001 | 2 | 20 | 0 | 40 | Fulfilled | Online Store |
| #2 | 2026-01-15 | C-2 | SKU-0002 | 1 | 35 | 5 | 30 | Fulfilled | Shop App |
| #3 | 2026-02-03 | C-1 | SKU-0003 | 3 | 18 | 4 | 50 | Unfulfilled | Online Store |
| #4 | 2026-02-20 | C-3 | SKU-0001 | 1 | 20 | 0 | 20 | Refunded | POS |
| #5 | 2026-03-01 | C-4 | SKU-0002 | 2 | 35 | 0 | 70 | Fulfilled | Online Store |

Counted orders: #1, #2, #3, #5. #4 is Refunded.

### 6.1 Headline KPIs

| KPI | Working | Expected |
|---|---|---|
| Net revenue | 40 + 30 + 50 + 70 | **190.0** |
| Orders | #1, #2, #3, #5 | **4** |
| Units sold | 2 + 1 + 3 + 2 | **8** |
| AOV | 190 ÷ 4 | **47.5** |
| Discounts given | 0 + 5 + 4 + 0 | **9.0** |
| Refund rate | 1 refunded ÷ 5 orders | **0.2** |
| Gross profit | (40 − 2×5) + (30 − 1×12) + (50 − 3×6) + (70 − 2×12) = 30 + 18 + 32 + 46 | **126.0** |
| Gross margin | 126 ÷ 190 | **0.663157…** (63/95) |
| Active customers | C-1, C-2, C-4 (C-3's only order is Refunded) | **3** |
| Repeat customer rate | C-1 has 2 counted orders; C-2 and C-4 have 1 each: 1 ÷ 3 | **0.333…** (1/3) |

### 6.2 Breakdowns

**5.1 Revenue by sales channel** (POS has no counted order, so it is absent)

| sales_channel | revenue_cad | orders |
|---|---|---|
| Online Store | 160.0 | 3 |
| Shop App | 30.0 | 1 |

**5.2 Revenue by category**

| category | revenue_cad | units_sold |
|---|---|---|
| Accessories | 100.0 | 3 |
| Home | 50.0 | 3 |
| Apparel | 40.0 | 2 |

**5.3 Revenue by month**

| month | revenue_cad | orders |
|---|---|---|
| 2026-01 | 70.0 | 2 |
| 2026-02 | 50.0 | 1 |
| 2026-03 | 70.0 | 1 |

**5.4 Top products** (N = 5; only 3 exist)

| sku | product_name | revenue_cad | units_sold |
|---|---|---|---|
| SKU-0002 | Canvas Tote | 100.0 | 3 |
| SKU-0003 | Ceramic Mug | 50.0 | 3 |
| SKU-0001 | Classic Tee | 40.0 | 2 |

**5.5 Top customers** (N = 5)

| customer_id | name | revenue_cad | orders |
|---|---|---|---|
| C-1 | Ana | 90.0 | 2 |
| C-4 | Dee | 70.0 | 1 |
| C-2 | Ben | 30.0 | 1 |

### 6.3 Subset of orders

Passing in only #3, #4 and #5 (e.g. a UI date range of 2026-02-01 to 2026-03-01):

| KPI | Working | Expected |
|---|---|---|
| Net revenue | 50 + 70 | **120.0** |
| Orders | #3, #5 | **2** |
| AOV | 120 ÷ 2 | **60.0** |
| Refund rate | 1 ÷ 3 | **0.333…** (1/3) |
| Active customers | C-1, C-4 | **2** |
| Repeat customer rate | 0 ÷ 2 | **0.0** |

### 6.4 Only refunded orders

Passing in only #4: Net revenue `0.0`, Orders `0`, Units sold `0`, AOV `None`, Discounts `0.0`, Refund rate `1.0`, Gross profit `0.0`, Gross margin `None`, Active customers `0`, Repeat customer rate `None`, and every breakdown is empty (with its columns).

## 7. Out of scope

- Comparisons with a previous period (e.g. "+12% vs last month").
- Targets, forecasts and currency conversion.
- Inventory KPIs (stock on hand, sell-through).
- How KPIs are displayed, charted or filtered: spec 003 Phase 2.

## 8. Acceptance criteria

All criteria are pytest tests on `kpis.py` using the §6 fixture in `tests/fixtures/`, with no Streamlit and no Google Sheet. Values are compared with `pytest.approx` where they are fractions.

- [ ] Each headline KPI in §4 returns the §6.1 value for the full fixture.
- [ ] Each breakdown in §5 returns exactly the §6.2 table: same columns, same order of columns, same rows in the same order.
- [ ] The §6.3 subset gives the §6.3 values.
- [ ] The §6.4 refunded-only input gives the §6.4 values, with no exception and no division by zero.
- [ ] An empty `orders` DataFrame (with its columns) gives `0.0` / `0` / `None` as in §3, and empty breakdowns.
- [ ] Top products with N = 2 returns SKU-0002 and SKU-0003 only.
- [ ] A revenue tie is broken by the A–Z rule in §5: two channels with equal revenue are listed A–Z.
- [ ] Revenue by month includes a zero row for a month with no counted orders between two months that have them.
- [ ] Top customers never includes an `email` column.
- [ ] For the full fixture, each product's revenue and units from 5.4 equal that product's `revenue_cad` and `units_sold` as recomputed by spec 001 §3.1, and each customer's revenue and orders from 5.5 equal `total_spent_cad` and `order_count`.
- [ ] KPI functions leave their input DataFrames unchanged.
- [ ] `kpis.py` does not import Streamlit.

## 9. Resolved questions (2026-10-06)

1. **KPI set:** keep all ten headline KPIs (§4.1–4.10) and all five breakdowns (§5.1–5.5).
2. **Unfulfilled orders** count towards revenue, orders, units and customer KPIs (§3), matching CLAUDE.md and spec 001 §3.1.
3. **Refund rate** is by order count only (§4.6).
4. **Gross profit** uses the product's current Unit Cost, with the limitation stated in §4 (§4.7).
5. **Active customers** are customers with a counted order in the rows passed in, not every row of the Customers tab (§4.9).
6. **Top N** is fixed at 5 (§5.4–5.5).
7. **Revenue over time** is by calendar month only (§5.3).
8. **Date range:** the KPI view has its own date range, defaulting to all data and independent of each tab's filters. The UI details belong in spec 003 Phase 2 (§2).
9. **Period comparison** stays out of scope (§7).
