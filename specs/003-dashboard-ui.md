# 003 Dashboard UI

**Status:** Phase 1 (§1–7) **Approved** (2026-10-02). Phase 2 is not specified yet.
**Depends on:** 001-data-source, 002-kpis

> The dashboard is built in two phases. **Phase 1** (§6) is a data explorer: it shows the loaded tables and the validation report, with no KPIs. **Phase 2** adds KPIs, totals and charts from spec 002 and is not specified yet. §1–5 apply to both phases.

## 1. Loading and caching

- The dashboard gets its data by calling the spec 001 loader.
- Results are cached for **5 minutes**. Within that window, no new API call is made.
- A failed load (`DataSourceError`) is never cached. The next page interaction tries again.
- The cache and the refresh logic live in the UI layer. They may use Streamlit (e.g. `st.cache_data`), but the loader must not.

## 2. Refresh button

- The dashboard has a "Refresh data" button.
- Pressing it clears the cache and reloads immediately, even if the 5 minutes have not passed.

## 3. Load errors

When the loader raises a `DataSourceError`, the dashboard shows an error screen instead of its normal content (in Phase 1, the four tabs of §6.2). It does not crash, and it shows no stack trace.

The error screen shows two things:

1. A **fixed heading** for the error's category, from the table below.
2. Underneath, the loader's own message text (`DataSourceError.message`), exactly as the loader wrote it. The UI does not build, rewrite or add to it.

| Category | Heading |
|---|---|
| `config` | "Configuration problem" |
| `auth` | "Could not sign in to Google Sheets" |
| `unreachable` | "Could not reach the Google Sheet" |
| `missing_tab` | "Sheet tab missing" |
| `missing_column` | "Column missing" |
| `duplicate_column` | "Duplicate column" |
| `empty_tab` | "Sheet tab is empty" |

Names of variables, tabs and columns reach the user through the loader's message. `DataSourceError` is not changed, and spec 001 stays as it is.

The "Refresh data" button stays visible on the error screen.

As spec 001 §7.1 requires, the loader's messages never contain the `SHEET_ID` value or the credentials path, and the UI adds nothing that could.

## 4. Data-quality indicators

- The dashboard always shows the number of dropped rows for each tab, from the validation report.
- If any tab has `over_threshold = true`, a warning banner names that tab and its drop rate, e.g. "Orders: 6.0% of rows were dropped".
- Warnings (severity `warning`) are counted separately from dropped rows and never trigger the banner.
- The dashboard never displays full customer emails.

## 5. Money display

- Money values are shown in CAD with exactly 2 decimals (e.g. `$1,234.50`).
- Rounding to 2 decimals happens **only at display time**. The spec 001 loader does not round; it keeps full precision and compares money with a 1-cent tolerance (spec 001 §3).
- Margin % is not money. It is shown as a percentage, and this rule does not apply to it.

## 6. Phase 1: Data Explorer

### 6.1 Scope

- The app is a Streamlit script at `src/shopify_dashboard/app.py`.
- It reads only the output of the spec 001 `load_data()` (the three DataFrames and the validation report). It never calls the Sheets client, the parser or the validator directly.
- Phase 1 shows **no KPIs, totals or charts**. Those are Phase 2.

### 6.2 Layout

From top to bottom:

1. The page title **"Shopify Data Explorer"**.
2. The "Refresh data" button (§2).
3. The over-threshold warning banner (§4), only when a tab is over threshold.
4. Four tabs, in this order: **Orders**, **Products**, **Customers**, **Data quality**.

On a load error, the title, the Refresh button and the error message (§3) are shown, and the four tabs are not.

### 6.3 Table tabs (Orders, Products, Customers)

Each table tab shows, from top to bottom:

1. A row count: "Showing X of Y rows". Y is the number of rows in that tab's DataFrame from the loader. X is the number of rows left after that tab's filters.
2. That tab's filters (§6.4).
3. The filtered table.

Display rules:

- Money columns are shown in CAD with exactly 2 decimals, as §5 says. The money columns are:
  - Orders: `unit_price_cad`, `discount_cad`, `line_total_cad`
  - Products: `price_cad`, `unit_cost_cad`, `revenue_cad`
  - Customers: `total_spent_cad`
- Column headers are the sheet headers (e.g. "Line Total (CAD)"), using the spec 001 §9 mapping in reverse, not the snake_case output names.
- Rows are shown in the order the loader returns them.
- Products `margin_pct` (a fraction, e.g. `0.75`) is shown as a percentage with 1 decimal (e.g. `75.0%`, `66.7%`).
- The Customers `email` column is shown masked, using the spec 001 mask (`mask_email`), as §4 requires.
- Formatting changes only what is displayed. The DataFrames from the loader are never changed.
- Every row the loader returns is shown, including orders with Status `Refunded`. The Refunded exclusion in CLAUDE.md applies to revenue and units-sold figures, and Phase 1 has none.

### 6.4 Filters

| Tab | Filter | Matches a row when |
|---|---|---|
| Orders | Order Date range (start, end) | `order_date` is between start and end, both inclusive |
| Orders | Category | `category` is one of the selected values |
| Orders | Status | `status` is one of the selected values |
| Orders | Sales Channel | `sales_channel` is one of the selected values |
| Products | Category | `category` is one of the selected values |
| Customers | Province | `province` is one of the selected values |

- The options of a Category, Status, Sales Channel or Province filter are the distinct values present in that tab's loaded DataFrame, sorted A–Z. Values that spec 001 allows but that do not appear in the data are not offered.
- A Category, Status, Sales Channel or Province filter with nothing selected is no filter: it keeps every row.
- The Order Date range defaults to the earliest and latest `order_date` in the loaded Orders DataFrame. If the user picks a start date after the end date, the filter keeps no rows and the tab shows a warning: "Start date is after end date."
- Filter selections are kept when "Refresh data" is pressed. A selected value that no longer appears in the reloaded data is removed from the selection.
- Within a tab, filters combine with AND: a row is shown only if it matches every filter.
- Each tab's filters are independent. A filter on one tab never changes the rows of another tab.
- The filter logic is pure Python in its own module, `src/shopify_dashboard/filters.py`, with no Streamlit import. It takes a DataFrame and the filter values, and returns the filtered DataFrame without changing its input. `app.py` only builds the widgets and calls it.

### 6.5 Data quality tab

1. A summary table with one row per tab (Orders, Products, Customers, in that order) and these columns: tab, rows read, rows dropped, drop rate, warnings. Rows read, rows dropped and drop rate come from the report's `TabSummary`. Warnings is the number of report entries with severity `warning` for that tab.
2. A table of all report entries with the columns `tab`, `row`, `column`, `value`, `reason`, `severity`, sorted by tab (Orders, Products, Customers), then row, then column. When the report has no entries, the text "No problems found." is shown instead of the table.

The `value` column shows each entry's value exactly as stored in the report (the raw sheet value), with no formatting or conversion.

Email values in the entries are always masked. (Spec 001 masks them when an entry is created; the UI never unmasks them.)

### 6.6 Launcher

- A PowerShell script `run.ps1` in the project root starts the app.
- It reads `.env` from the project root, sets each `KEY=VALUE` line as an environment variable for the process it starts, and runs `streamlit run src/shopify_dashboard/app.py`.
- **`.env` always wins.** A value in `.env` replaces any value of the same variable already set in the PowerShell session.
- If `.env` does not exist, the script does not start the app. It prints a clear message saying `.env` is missing and should be created from `.env.example`, and exits with a non-zero code.
- It never prints the values it reads.
- The app never reads `.env` or any other file for configuration. It gets `SHEET_ID` and `GOOGLE_APPLICATION_CREDENTIALS` only from the environment (spec 001 §7.1). No file under `src/` imports a dotenv library.

## 7. Acceptance criteria

### 7.1 Loading, errors and data quality (§1–5)

All criteria use a mocked loader and a controllable clock.

- [x] Two loads within 5 minutes call the loader once.
- [x] A load 5 minutes or more after the last one calls the loader again.
- [x] Pressing "Refresh data" calls the loader again within the 5 minutes.
- [x] A load that fails is not cached. The next load calls the loader again.
- [x] Each `DataSourceError` category shows its heading from §3 with the loader's message text underneath, unchanged, and no stack trace.
- [x] The Refresh button is visible on the error screen.
- [x] A report with a tab where `over_threshold = true` shows the banner. With none, no banner is shown.
- [x] Dropped-row counts per tab match the report.
- [x] A money value of `1234.5` is displayed as `$1,234.50` and `69.5` as `$69.50`, while the underlying data is unchanged.
- [x] A `config` error for an unset variable and one for a placeholder value both show the "Configuration problem" heading; the message names the variable and never its value.

### 7.2 Phase 1: Data Explorer (§6)

Filter criteria are pytest tests on `filters.py` with fixture DataFrames and no Streamlit. The other criteria use a mocked loader.

Layout and scope
- [x] The page title is "Shopify Data Explorer".
- [x] The Refresh button is shown above the tabs.
- [x] The four tabs appear in the order Orders, Products, Customers, Data quality.
- [x] On a load error, the four tabs are not shown; the title, Refresh button and error message are.
- [x] No KPI, total or chart is shown.
- [x] `app.py` calls only `load_data()` from the data layer.

Table tabs
- [x] With no filters set, each table tab shows "Showing Y of Y rows", where Y is the loader's row count for that tab.
- [x] With filters set, the count shows the filtered row count as X.
- [x] Every money column listed in §6.3 is shown with `$` and exactly 2 decimals.
- [x] A `margin_pct` of `0.75` is shown as `75.0%` and `0.6667` as `66.7%`.
- [x] Table headers are the sheet headers (e.g. "Line Total (CAD)"), not snake_case names.
- [x] Table rows are in the loader's order.
- [x] The Customers table never shows a full email; `jane.doe@example.com` is shown masked.
- [x] Displaying a table leaves the loader's DataFrame unchanged.
- [x] Orders with Status `Refunded` are listed in the Orders table.

Filters
- [x] An Order Date range keeps orders on the start date and on the end date (both inclusive) and drops orders outside it.
- [x] A Category, Status or Sales Channel selection on Orders keeps only matching rows.
- [x] A Category, Status, Sales Channel or Province filter with nothing selected keeps every row.
- [x] Filter options are the distinct values present in the loaded data, sorted A–Z; an allowed value absent from the data is not offered.
- [x] The Order Date range defaults to the earliest and latest `order_date` in the data.
- [x] A start date after the end date keeps no rows and shows "Start date is after end date."
- [x] After "Refresh data", selections are kept, and a selected value missing from the new data is removed from the selection.
- [x] Two Orders filters together keep only rows that match both.
- [x] A Category selection on Products keeps only matching rows.
- [x] A Province selection on Customers keeps only matching rows.
- [x] Filtering one tab does not change the rows shown on any other tab.
- [x] The filter functions return a new DataFrame and leave their input unchanged.
- [x] `filters.py` does not import Streamlit.

Data quality tab
- [x] The summary shows rows read, rows dropped, drop rate and warnings per tab, matching the report.
- [x] Warning counts per tab match the number of `warning` entries for that tab.
- [x] Every report entry appears in the entries table with its six fields.
- [x] The `value` column shows each entry's value exactly as stored in the report.
- [x] Entries are sorted by tab (Orders, Products, Customers), then row, then column.
- [x] A report with no entries shows "No problems found." instead of the entries table.
- [x] An entry whose column is `Email` shows the masked value, never the full email.

Launcher
- [x] No file under `src/` imports a dotenv library or opens `.env` (static test).
- [x] Manual check: with a filled-in `.env`, `run.ps1` starts the app and the real sheet loads; no configuration value is printed to the terminal.
- [x] Manual check: with `.env` left as a copy of `.env.example`, the app shows the `config` heading from §3 with the loader's placeholder message.
- [x] Manual check: with `SHEET_ID` set in the session to a value different from the one in `.env`, `run.ps1` uses the `.env` value.
- [x] Manual check: with no `.env`, `run.ps1` prints the missing-file message, does not start the app, and exits non-zero.

## 8. Open questions

Resolved (2026-10-02) and written into the spec: empty selection is no filter (§6.4); sheet headers (§6.3); Margin % with 1 decimal (§6.3); loader order for tables and tab/row/column order for entries (§6.3, §6.5); "No problems found." (§6.5); a fixed heading per category with the loader's message, and no change to spec 001 (§3); `.env` always wins and a missing `.env` stops `run.ps1` (§6.6); filter options from the loaded data, the default date range and start-after-end handling, and selections kept across refresh (§6.4); report values shown as stored (§6.5).

No open questions remain for Phase 1.
