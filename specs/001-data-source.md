# Spec 001: Data Source

**Status:** Approved
**Owner:** Tell
**Depends on:** none
**Used by:** 002-kpis, 003-dashboard-ui

## 1. Goal

Load Shopify order, product and customer data from one Google Sheet into clean, typed pandas DataFrames that the rest of the app can trust.

The loader is pure Python with no Streamlit imports (see CLAUDE.md). Displaying errors and warnings, caching, and the Refresh button belong to the UI and are specified in `specs/003-dashboard-ui.md`.

## 2. Source

| Item | Value |
|---|---|
| System | Google Sheets API v4 |
| Spreadsheet | `shopify_store_data_SDD` |
| Spreadsheet ID | env var `SHEET_ID` |
| Auth | Service account, key file path in env var `GOOGLE_APPLICATION_CREDENTIALS` |
| Access level | Viewer (read-only) |
| Tabs | `Orders`, `Products`, `Customers` |

Row 1 of each tab is the header, and data starts on row 2. The number of rows is not fixed.

- Rows that are completely blank are skipped silently. They are not reported and do not count towards any total.
- A row counts as blank when every column listed in §4–6 is blank. Values in extra columns do not count, so a row with values only in extra columns is skipped silently too.
- Data ends at the last non-blank row.

## 3. Reading values

- Numbers must be read as raw numbers, not display text. The sheet displays `$45.00` and shows zero discounts as `-`; the loader must receive `45` and `0`.
- Dates are read as raw values, not display text, so the sheet's display format does not matter. A date cell is accepted if it is either a date value or text in ISO `YYYY-MM-DD` form.
  (Implementation note: request unformatted values, with dates as serial numbers.)
- Formula columns (marked *calculated* below) are read as their computed values, but only as a cross-check. See §3.1.
- Leading and trailing whitespace is removed from all text values and headers before any rule is checked. After that, headers and enum values must match exactly, including case.
- **Required** means the column must exist and the cell must not be blank. There are two exceptions: a rule that gives blank a meaning (Discount), and *calculated* columns, where a blank cell is not a rule break because the value is recomputed (§3.1).
- Money columns are stored as `float64`. Money comparisons use a tolerance of 0.01 CAD (1 cent).
- Integer columns must hold whole numbers (`2.5` breaks the rule).
- A text value in a number or date column breaks the rule (e.g. the text `"45"` in `Quantity`).
- A number in a text column is read as text (e.g. a Product Name of `1984`). ID format rules still apply, so `1001` in `Order ID` breaks the rule.
- A date value that includes a time keeps only the date.

### 3.1 Calculated columns

The code recomputes every *calculated* column from the validated data. The sheet's values are never used in the output. Tests compare the recomputed values with the sheet's values as a cross-check.

**Unreadable calculated values.** A calculated cell is *unreadable* when it holds a Google Sheets error value (`#N/A`, `#REF!`, `#VALUE!`, `#DIV/0!`, `#NAME?`, `#NUM!`, `#NULL!`, `#ERROR!`) in any calculated column, including Product Name and Category in Orders, or, in a number calculated column, any value that is not a valid number of that type (e.g. text in `Units Sold`, or `2.5` in `Orders`). An unreadable calculated cell never drops the row. Its value is treated as missing for cross-checks, the same as a blank calculated cell, and a `warning` is recorded with reason `calculated value unreadable`. Error values in columns that are not calculated get no special treatment.

| Tab | Column | Recomputed as |
|---|---|---|
| Orders | Product Name, Category | Looked up from validated Products by SKU |
| Orders | Line Total (CAD) | Quantity × Unit Price − Discount |
| Products | Margin % | (Price − Unit Cost) ÷ Price, as a fraction. 0 when Price is 0. |
| Products | Units Sold | Sum of Quantity over non-Refunded orders for that SKU |
| Products | Revenue (CAD) | Sum of recomputed Line Total over non-Refunded orders for that SKU |
| Customers | Orders | Count of non-Refunded orders for that customer |
| Customers | Total Spent (CAD) | Sum of recomputed Line Total over non-Refunded orders for that customer |

These calculations follow the business rules in CLAUDE.md: Refunded orders are excluded, and revenue means Line Total.

## 4. Tab: Orders

One row per order, with exactly one SKU per order.

| Column | Type | Required | Rules |
|---|---|---|---|
| Order ID | string | yes | Format `#` followed by digits, e.g. `#1001`. Unique. |
| Order Date | date | yes | Must be a real calendar date, and not after today (§7.4). If it is earlier than the customer's `Customer Since`, the row is **kept** and a warning is recorded. |
| Customer ID | string | yes | Format `C-` + digits. Must exist in the **validated** Customers. |
| SKU | string | yes | Format `SKU-` + 4 digits. Must exist in the **validated** Products. |
| Product Name | string | yes | *Calculated* (§3.1). |
| Category | string | yes | *Calculated* (§3.1). |
| Quantity | integer | yes | ≥ 1 |
| Unit Price (CAD) | decimal | yes | > 0. It does not have to equal the Products `Price (CAD)`. |
| Discount (CAD) | decimal | yes | ≥ 0 and ≤ Quantity × Unit Price. Blank means 0. |
| Line Total (CAD) | decimal | yes | *Calculated* (§3.1). If the sheet value differs from the recomputed value by more than 0.01, the row is **kept** and a warning is recorded. |
| Status | enum | yes | One of `Fulfilled`, `Unfulfilled`, `Refunded`. |
| Sales Channel | enum | yes | One of `Online Store`, `Shop App`, `POS`, `Instagram`. |

## 5. Tab: Products

| Column | Type | Required | Rules |
|---|---|---|---|
| SKU | string | yes | Unique. Format `SKU-` + 4 digits. |
| Product Name | string | yes | |
| Category | enum | yes | One of `Apparel`, `Accessories`, `Home`, `Outdoor`. |
| Price (CAD) | decimal | yes | > 0 |
| Unit Cost (CAD) | decimal | yes | ≥ 0 |
| Inventory | integer | yes | ≥ 0 |
| Margin % | decimal | yes | *Calculated* (§3.1). Stored as a fraction (0.67 = 67%). |
| Units Sold | integer | yes | *Calculated* (§3.1). |
| Revenue (CAD) | decimal | yes | *Calculated* (§3.1). |

## 6. Tab: Customers

| Column | Type | Required | Rules |
|---|---|---|---|
| Customer ID | string | yes | Unique. Format `C-` + digits. |
| Name | string | yes | |
| Email | string | yes | Contains `@`. Never logged in full (§7.2). |
| City | string | yes | |
| Province | enum | yes | One of `AB`, `BC`, `MB`, `NB`, `NL`, `NS`, `NT`, `NU`, `ON`, `PE`, `QC`, `SK`, `YT`. |
| Customer Since | date | yes | Must be a real calendar date. |
| Orders | integer | yes | *Calculated* (§3.1). |
| Total Spent (CAD) | decimal | yes | *Calculated* (§3.1). |

## 7. Validation behaviour

Validation runs after every load, in this order:
1. Products
2. Customers
3. Orders, whose SKU and Customer ID checks use the validated Products and Customers from steps 1 and 2.

### 7.1 Errors (the load stops)

The loader raises a `DataSourceError` that has a category and a message. It does not return partial data.

| Category | When | Message must name |
|---|---|---|
| `config` | `SHEET_ID` or `GOOGLE_APPLICATION_CREDENTIALS` is unset | the variable **name** |
| `auth` | Authentication fails, or the service account has no access to the sheet (HTTP 401 or 403) | nothing specific |
| `unreachable` | The API call fails for any other reason (including HTTP 404, e.g. a wrong sheet ID) or times out | nothing specific |
| `missing_tab` | A tab is missing | the tab |
| `missing_column` | A required column is missing or renamed | the tab and the column |
| `duplicate_column` | A column listed in §4–6 appears more than once in a tab, after trimming. Repeated extra or blank headers are ignored. | the tab and the column |
| `empty_tab` | A tab has no data rows after the header, or is completely empty (no header row) | the tab |

Structure checks run per tab, in §7 tab order, in this order: completely empty (`empty_tab`), then `missing_column`, then `duplicate_column`, then no data rows (`empty_tab`).

Messages never contain:
- the value of `SHEET_ID`,
- the credentials file path or its contents,
- a stack trace.

### 7.2 Row problems (the load continues)

| Problem | Behaviour |
|---|---|
| A row breaks a rule in §3–6 | Drop the row and record it with severity `dropped`. |
| A unique key appears more than once | Drop **every** row that shares the key and record each one. |
| An order references a SKU or Customer ID that is missing from the validated table | Drop the order. The reason says `SKU not found` or `Customer not found`. |
| The sheet's Line Total differs from the recomputed value by more than 0.01 | Keep the row and record it with severity `warning`. |
| An Order Date is earlier than the customer's `Customer Since` | Keep the row and record it with severity `warning`. |
| A calculated cell is unreadable (§3.1) | Keep the row and record it with severity `warning` and reason `calculated value unreadable`. The value is treated as missing, so no Line Total mismatch warning is recorded for it. |
| Extra columns not listed here | Ignore them. |

A row that breaks several rules is recorded once for each rule it breaks, but it is dropped only once.

Cross-check warnings (Line Total mismatch, Order Date before `Customer Since`) are recorded only for rows that are kept; a row that is already dropped gets no cross-check warnings. Unreadable calculated cell warnings (§3.1) come from the per-cell checks and are recorded for every row, kept or dropped. Duplicate-key rows get no other checks.

### 7.3 Validation report

The report is a list of entries, each with these fields:
- `tab`
- `row`: the sheet row number, where the header is row 1
- `column`: the sheet header, not the snake_case name
- `value`
- `reason`
- `severity`: `dropped` or `warning`

The `reason` field uses exactly these texts:

| Reason | Severity | When |
|---|---|---|
| `required` | dropped | A required cell is blank (§3) |
| `must be a number` | dropped | Text or a true/false value in a number column (§3) |
| `must be a whole number` | dropped | A fraction in an integer column (§3) |
| `must be a date (YYYY-MM-DD)` | dropped | A date cell that is neither a date value nor ISO text (§3) |
| `not a real calendar date` | dropped | ISO text for a date that does not exist, e.g. `2026-02-30` (§3) |
| `invalid format` | dropped | An ID that does not match its format (§4–6) |
| `not an allowed value` | dropped | An enum value not in its list (§4–6) |
| `must be greater than 0` | dropped | Price or Unit Price ≤ 0 |
| `must be 0 or more` | dropped | Unit Cost, Inventory or Discount < 0 |
| `must be 1 or more` | dropped | Quantity < 1 |
| `must contain @` | dropped | An Email with no `@` |
| `must not exceed Quantity × Unit Price` | dropped | Discount above Quantity × Unit Price by more than 0.01 |
| `must not be after today` | dropped | An Order Date after today (§7.4) |
| `SKU not found` | dropped | The SKU is not in the validated Products |
| `Customer not found` | dropped | The Customer ID is not in the validated Customers |
| `duplicate <key column>` | dropped | A unique key shared by several rows, e.g. `duplicate Order ID` |
| `differs from Quantity × Unit Price − Discount` | warning | The sheet Line Total is more than 0.01 off |
| `before the customer's Customer Since` | warning | Order Date earlier than the customer's `Customer Since` |
| `calculated value unreadable` | warning | An unreadable calculated cell (§3.1) |

Email values are masked in the report as the first character, `***`, then `@domain` (e.g. `j***@example.com`). The same masking applies anywhere an email is logged. Edge cases:
- The value is trimmed before masking.
- With no `@`, only the first character is kept: `jane.example.com` → `j***`.
- With more than one `@`, the domain is the part after the last `@`: `a@b@c.com` → `a***@c.com`.
- An empty part before the `@` gives `***@domain`: `@example.com` → `***@example.com`.
- Non-text values are masked the same way: `12345` → `1***`.
- A blank value stays blank (there is nothing to hide; the reason says it is required).
- Masking an already-masked value changes nothing, so an entry can never be masked twice.

For each tab, the report also gives:
- the number of data rows read,
- the number of rows dropped,
- the drop rate (rows dropped ÷ data rows read).

`over_threshold` is true when a tab's drop rate is greater than 5%. Warnings do not count towards the drop rate.

### 7.4 Today

"Today" is the load date. The loader accepts it as an optional parameter, and it defaults to the current local date, so tests can pass in a fixed date.

## 8. Refresh and caching

- A single call to the loader reads all three tabs with one metadata lookup (to find which tabs exist) plus exactly one batch of value reads.
- The loader itself does not cache. The 5-minute cache and the "Refresh data" button are defined in `specs/003-dashboard-ui.md`.
- A failed load is never cached.

## 9. Output

The loader returns:
- three DataFrames, `orders`, `products` and `customers`. They use the types above and hold recomputed values in the calculated columns;
- the validation report (§7.3).

Output columns use snake_case names. One mapping, defined in a single place in the code, translates the sheet headers into these names. Validation works on the sheet headers; the rename happens only at output.

| Tab | Sheet header | Output column |
|---|---|---|
| Orders | Order ID | `order_id` |
| Orders | Order Date | `order_date` |
| Orders | Customer ID | `customer_id` |
| Orders | SKU | `sku` |
| Orders | Product Name | `product_name` |
| Orders | Category | `category` |
| Orders | Quantity | `quantity` |
| Orders | Unit Price (CAD) | `unit_price_cad` |
| Orders | Discount (CAD) | `discount_cad` |
| Orders | Line Total (CAD) | `line_total_cad` |
| Orders | Status | `status` |
| Orders | Sales Channel | `sales_channel` |
| Products | SKU | `sku` |
| Products | Product Name | `product_name` |
| Products | Category | `category` |
| Products | Price (CAD) | `price_cad` |
| Products | Unit Cost (CAD) | `unit_cost_cad` |
| Products | Inventory | `inventory` |
| Products | Margin % | `margin_pct` |
| Products | Units Sold | `units_sold` |
| Products | Revenue (CAD) | `revenue_cad` |
| Customers | Customer ID | `customer_id` |
| Customers | Name | `name` |
| Customers | Email | `email` |
| Customers | City | `city` |
| Customers | Province | `province` |
| Customers | Customer Since | `customer_since` |
| Customers | Orders | `order_count` |
| Customers | Total Spent (CAD) | `total_spent_cad` |

## 10. Acceptance criteria

All criteria except the manual check are pytest tests that use fixtures in `tests/fixtures/` and a mocked Sheets client.

**Manual check (not pytest):** with the real sheet, all 1,000 orders, 10 products and 150 customers load with zero dropped rows. These counts are a one-off check, not a runtime rule.

- [ ] `Discount (CAD)` is numeric everywhere. A `-` display and a blank cell both load as `0`.
- [ ] `Order Date` and `Customer Since` load as dates. `2026-02-30` is dropped and reported.
- [ ] A fixture with a missing `Status` column raises `missing_column`, naming `Orders` and `Status`.
- [ ] A fixture with a header of ` Status ` (extra spaces) loads normally.
- [ ] A fixture with one bad Status value (e.g. `Shipped`) drops exactly that row and reports it.
- [ ] A fixture with `fulfilled` (lowercase) drops that row.
- [ ] A fixture order with a SKU not in Products is dropped, with reason `SKU not found`.
- [ ] A fixture order with a Customer ID not in Customers is dropped, with reason `Customer not found`.
- [ ] A fixture Products row that breaks a rule is dropped, and every order with that SKU is dropped too.
- [ ] Two orders with the same Order ID are both dropped and both reported.
- [ ] Quantity `0`, Quantity `2.5` and a Discount greater than Quantity × Unit Price are each dropped.
- [ ] A Line Total that is 0.05 off is kept, reported as a `warning`, and the output holds the recomputed value.
- [ ] A Line Total that is 0.005 off is not reported.
- [ ] Recomputed Units Sold, Revenue, Orders and Total Spent exclude Refunded orders and match the fixture's sheet values.
- [ ] Extra columns are ignored and do not appear in the output.
- [ ] Output DataFrames have exactly the snake_case columns in §9, in that order.
- [ ] With today fixed at `2026-06-01`, an order dated `2026-06-02` is dropped and reported; one dated `2026-06-01` loads.
- [ ] An order dated before its customer's `Customer Since` is kept and reported as a `warning`.
- [ ] Margin % for Price 20 and Unit Cost 5 is `0.75`.
- [ ] Blank rows in the middle of a tab are skipped and not reported.
- [ ] A tab with 6 dropped rows out of 100 has `over_threshold = true`. With 5 out of 100 it is false.
- [ ] An invalid Customers email appears in the report masked, e.g. `j***@example.com`.
- [ ] Unset `SHEET_ID` raises `config`, and the message contains the text `SHEET_ID` but no sheet ID value.
- [ ] Auth and API failures raise `auth` and `unreachable`. The messages contain no sheet ID, no credentials path and no stack trace.
- [ ] A header-only tab raises `empty_tab`.
- [ ] A fixture with two `Status` columns in Orders raises `duplicate_column`, naming `Orders` and `Status`.
- [ ] A completely empty tab (no header row) raises `empty_tab`, naming the tab.
- [ ] A row with values only in extra columns is skipped and not reported, and later rows keep their real sheet row numbers.
- [ ] An unreadable calculated cell (`#N/A` in Orders `Product Name`, text in Products `Units Sold`, `#VALUE!` in Orders `Line Total (CAD)`) keeps its row and records one `warning` with reason `calculated value unreadable`. The Line Total case records no mismatch warning, and none of these count towards the drop rate.

## 11. Resolved questions

1. Line Total mismatch: keep the row and record a warning (§7.2).
2. Calculated columns: recompute in code and use the sheet values only as a cross-check in tests (§3.1).
3. Cache time: 5 minutes, specified in spec 003.
4. Future Order Dates: dropped and reported, with "today" injectable (§7.4).
5. Order Date before `Customer Since`: kept with a warning (§7.2).
6. Margin % formula: (Price − Unit Cost) ÷ Price, and 0 when Price is 0 (§3.1).
