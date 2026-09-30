# Plan 001: Data Source

**Spec:** `specs/001-data-source.md` (Approved)
**Status:** Approved

This plan says *how* spec 001 will be built. Where the plan and the spec disagree, the spec wins. The decisions in §8 were approved on 2026-09-30.

## 1. Approach

The loader is split into small pure-Python modules with one job each. The only module that touches Google is `sheets_client.py`. Everything else works on plain Python lists, so the tests can feed the loader fixture data through a fake client.

Data flows like this:

```
env vars ──► config ──► GspreadSheetsClient.fetch_tabs()      (one batch read, §8)
                              │  raw rows: dict[tab, list[list[cell]]]
                              ▼
                        parsing: trim headers, skip blank rows, keep sheet row numbers,
                                 check tabs/required columns/empty tabs  → DataSourceError
                              ▼
                        validation: Products → Customers → Orders   (§7 order)
                                 coerce cells, apply rules, unique keys, references,
                                 dates vs today, warnings            → ValidationReport
                              ▼
                        calculations: recompute every calculated column (§3.1)
                              ▼
                        output: rename to snake_case (§9), set dtypes → LoadResult
```

## 2. Files

### src/

All code goes in the package `src/shopify_dashboard/`. No module imports Streamlit.

| File | Responsibility | Spec |
|---|---|---|
| `__init__.py` | Re-exports `load_data`, `LoadResult`, `DataSourceError` | — |
| `schema.py` | Tab and column definitions: header, snake_case name, type, required, rules, calculated flag. Also holds the enums, the province list and the **single** header → snake_case mapping. | §4–6, §9 |
| `errors.py` | `ErrorCategory` enum and `DataSourceError` | §7.1 |
| `config.py` | Reads `SHEET_ID` and `GOOGLE_APPLICATION_CREDENTIALS` from the environment | §2, §7.1 |
| `sheets_client.py` | `SheetsClient` protocol and `GspreadSheetsClient`, the real adapter. Converts gspread and google-auth exceptions into `DataSourceError`. | §2, §3, §7.1, §8 |
| `parsing.py` | Cleans up the raw tab data. Checks the tab and header structure, and converts single cells to typed values. | §2, §3 |
| `report.py` | `ReportEntry`, `TabSummary`, `ValidationReport`, `mask_email` | §7.3 |
| `validation.py` | Rule checks for each tab, unique keys, references between tabs, date checks and warnings | §4–7 |
| `calculations.py` | Recomputes the calculated columns | §3.1 |
| `loader.py` | `load_data()`, which runs the pipeline, and `LoadResult` | §7, §8, §9 |

### tests/

| File | What it covers |
|---|---|
| `conftest.py` | `FakeSheetsClient`, the `base_tabs` fixture, mutation helpers and the fixed `TODAY` |
| `fixtures/base_valid.json` | Small, fully valid dataset (§5.1) |
| `fixtures/threshold_100_orders.json` | 100 valid orders for the 5% threshold criterion (§5.2) |
| `test_schema.py` | The mapping is complete and matches the spec §9 table |
| `test_errors.py` | Error categories match spec §7.1; `DataSourceError` carries category and message |
| `test_config.py` | Environment variable handling |
| `test_sheets_client.py` | Adapter render options, one batch read, exception mapping (gspread is mocked) |
| `test_parsing.py` | Headers, blank rows, cell conversion |
| `test_report.py` | Masking, summaries, threshold |
| `test_validation.py` | Rule checks for each tab, uniqueness, references, dates, warnings |
| `test_calculations.py` | Each calculated column, Refunded exclusion, margin |
| `test_loader.py` | End-to-end acceptance criteria through `load_data(FakeSheetsClient, today=TODAY)` |

### Project root

| File | Purpose |
|---|---|
| `requirements.txt` | Runtime dependencies (§4) |
| `requirements-dev.txt` | `-r requirements.txt` plus test and lint tools (§4) |
| `pyproject.toml` | pytest settings (`pythonpath = ["src"]`, `testpaths = ["tests"]`) and ruff settings (`target-version = "py311"`, line length, rule set) |

## 3. Functions and responsibilities

Every function has type hints and a docstring naming the spec section, as CLAUDE.md requires.

### schema.py
- `TABS: tuple[str, ...]`: `("Products", "Customers", "Orders")`, in validation order.
- `ColumnSpec` (frozen dataclass): `header`, `name` (snake_case), `kind` (`str | int | decimal | date | enum`; `decimal` follows the spec's type name and covers money columns and Margin %), `required`, `calculated`, `allowed` (for enums), `pattern` (regex for ID formats).
- `COLUMNS: dict[str, tuple[ColumnSpec, ...]]`: the one place that maps headers to snake_case names. Output column order is tuple order, which matches spec §9.
- `STATUSES`, `SALES_CHANNELS`, `CATEGORIES`, `PROVINCES`, `UNIQUE_KEYS` (`Orders: Order ID`, `Products: SKU`, `Customers: Customer ID`).

### errors.py
- `ErrorCategory` (str Enum): `config`, `auth`, `unreachable`, `missing_tab`, `missing_column`, `empty_tab`.
- `DataSourceError(Exception)`: has `category` and `message`. `__str__` returns only the message.

### config.py
- `Config` (frozen dataclass): `sheet_id`, `credentials_path`. `__repr__` hides both values so they can never leak into logs.
- `load_config(env: Mapping[str, str] = os.environ) -> Config`: raises `config` naming the first unset or blank variable. The message holds the variable **name** only.

### sheets_client.py
- `RawTabs = dict[str, list[list[object]]]`.
- `SheetsClient` (Protocol): `fetch_tabs(tabs: Sequence[str]) -> RawTabs`.
- `GspreadSheetsClient(config: Config)`:
  - `fetch_tabs(tabs)`:
    - authorises with the service account key, opens the sheet by key and reads all tabs with **one** `batch_get`;
    - requests `value_render_option=UNFORMATTED_VALUE` and `date_time_render_option=SERIAL_NUMBER` (§3);
    - returns only the tabs that exist.
  - Exception mapping:
    - auth or credential-file errors become `auth`;
    - `APIError`, network errors and timeouts become `unreachable`;
    - the original exception is chained with `from None`, so no traceback text or IDs reach the message.
  - This is the only module that imports `gspread` or `google.*`.

### parsing.py
- `ParsedTab` (dataclass): `tab`, `headers` (trimmed), `rows: list[ParsedRow]`, where `ParsedRow` = `sheet_row: int` + `cells: dict[header, raw value]`.
- `parse_tabs(raw: RawTabs) -> dict[str, ParsedTab]`, in order:
  - raises `missing_tab` for any tab absent from `TABS`;
  - trims headers and ignores extra columns;
  - raises `missing_column` (tab + column) for any spec column that is missing;
  - skips fully blank rows but keeps the real sheet row number (header = 1);
  - drops trailing blanks;
  - raises `empty_tab` when no data rows remain.
- `coerce_cell(value, spec) -> tuple[value | None, reason | None]`: converts one cell with no side effects.
  - Text is trimmed.
  - A decimal must be int or float (text breaks the rule).
  - Integers must be whole numbers.
  - A date may be a serial number (epoch 1899-12-30) or ISO text parsed strictly, so `2026-02-30` fails.
  - A blank Discount becomes 0.
  - Any other blank required cell gives the reason `required`.

### report.py
- `Severity` (str Enum): `dropped`, `warning`.
- `ReportEntry` (frozen dataclass): `tab`, `row`, `column` (sheet header), `value`, `reason`, `severity`.
- `TabSummary`: `rows_read`, `rows_dropped`, `drop_rate`, and a property `over_threshold` (`drop_rate > 0.05`).
- `ValidationReport`: `entries`, `summaries: dict[tab, TabSummary]`, and helpers `dropped()` and `warnings()`.
- `mask_email(value: object) -> str`: gives first character + `***` + `@domain`. Without an `@` it gives first character + `***`.
- `make_entry(...)`: builds an entry and **always** passes Email values through `mask_email`, so no other code path can store a full email.

### validation.py
Each function returns the valid rows plus report entries. A row that breaks several rules gets one entry per rule and is dropped once.
- `validate_products(tab) -> (rows, entries)`: formats, enums, `Price > 0`, `Unit Cost ≥ 0`, `Inventory ≥ 0`.
- `validate_customers(tab) -> (rows, entries)`: ID format, `@` in email, province list, real `Customer Since`.
- `validate_orders(tab, products, customers, today) -> (rows, entries)`:
  - cell rules, `Quantity ≥ 1`, `Unit Price > 0`;
  - `0 ≤ Discount ≤ Quantity × Unit Price` with a 0.01 tolerance;
  - Order Date must not be after `today`;
  - `SKU not found` and `Customer not found` are checked against the **validated** tables;
  - warnings: Line Total mismatch over 0.01, and Order Date before Customer Since.
- `find_duplicate_keys(tab, key) -> entries`: every row that shares a key is dropped (decision D1).
- `validate_all(tabs, today) -> (valid rows per tab, ValidationReport)`: runs Products, then Customers, then Orders, and builds the `TabSummary` for each tab. Warnings never count as drops.

### calculations.py
- `line_total(quantity, unit_price, discount) -> float`
- `margin_pct(price, unit_cost) -> float`: returns 0 when price is 0.
- `enrich_orders(orders, products) -> orders`: fills in Product Name and Category by SKU and the recomputed Line Total.
- `product_stats(orders) -> units_sold, revenue per SKU`: uses non-Refunded orders only. SKUs with no orders get 0.
- `customer_stats(orders) -> order_count, total_spent per customer`: uses non-Refunded orders only. Customers with no orders get 0.

### loader.py
- `LoadResult` (dataclass): `orders`, `products`, `customers` (DataFrames) and `report`.
- `load_data(client: SheetsClient | None = None, today: date | None = None) -> LoadResult`:
  - if `client` is None, builds `GspreadSheetsClient(load_config())`;
  - `today` defaults to `date.today()` (§7.4);
  - calls `fetch_tabs` exactly once, then parses, validates and recomputes;
  - finishes with `to_frames`.
- `to_frames(rows) -> DataFrames`:
  - renames columns using `schema.COLUMNS`, in spec §9 order, and drops extra columns;
  - dtypes: `string` for text and enums, `int64` for integers, `float64` for money and margin, `datetime64[ns]` (normalised to midnight) for dates.

## 4. Dependencies

`requirements.txt` holds the runtime dependencies:

```
gspread>=6.1,<7
google-auth>=2.29,<3
pandas>=2.2,<3
streamlit>=1.36,<2        # used by spec 003 only; not imported by spec 001 code
```

`requirements-dev.txt` holds the test and lint tools:

```
-r requirements.txt
pytest>=8.2,<9
ruff>=0.5
```

Python 3.11+. These ranges are version floors that I know exist. They have **not** been checked against the latest releases. In task 1, install into a fresh `.venv`, run the tests, then pin the exact versions that were resolved (`pip freeze`) and commit them.

No mocking library is needed beyond the standard `unittest.mock`. No clock-faking library is needed either, because `today` is passed in.

## 5. Mocking and fixtures

### 5.1 How the Sheets client is mocked
- **`FakeSheetsClient`** (in `conftest.py`) implements the `SheetsClient` protocol:
  - built from a `RawTabs` dict;
  - `fetch_tabs` counts its calls and returns a deep copy, so tests can't change the shared data;
  - it can instead raise a given `DataSourceError`.
  - The fake returns values **as the API would with unformatted rendering**: numbers as int or float, dates as serial numbers, and blanks as `""`. A `-` shown in the sheet is really the number 0, so the fake returns `0`.
- **`GspreadSheetsClient`** is tested with `unittest.mock.patch` on `gspread.service_account` / `gspread.Client`, so there is no network access. These tests check:
  - the render options passed to `batch_get`;
  - that only one `batch_get` call is made;
  - that each exception type becomes the right category;
  - that messages contain neither the fake sheet ID nor the credentials path.
- **Environment variables** are handled with the pytest `monkeypatch` fixture (`setenv`/`delenv`).
- No test builds a real client without patching, so the real sheet is never called (CLAUDE.md).

### 5.2 Fixture data
- **`base_valid.json`** is a `RawTabs` document with the headers in the sheet's order and `TODAY = 2026-06-01`. It contains:
  - **4 products**, including `SKU-0001` with Price 20 and Unit Cost 5 (margin 0.75);
  - **3 customers**;
  - **8 orders**, including at least one Refunded, one Unfulfilled, one with a blank Discount and one with Discount `0`. All dates are on or before `TODAY` and on or after the customer's Customer Since.
  - Calculated columns hold the **correct** sheet values, used for the cross-check criterion.
- **Variants** are made in the tests with small `conftest.py` helpers applied to a copy of the base data: `set_cell(tabs, tab, row, header, value)`, `drop_column`, `rename_header`, `add_column`, `append_row`, `insert_blank_row`, `clear_data_rows`. Each test's change is visible in the test itself, and the base file stays valid.
- **`threshold_100_orders.json`** holds 100 valid orders over the base products and customers. The threshold tests break 5 or 6 of them.

### 5.3 Fixture for each acceptance criterion

All criteria are tested in `test_loader.py` through `load_data(fake, today=TODAY)`, unless the table says otherwise.

| Acceptance criterion | Fixture and change | Test assertion |
|---|---|---|
| Discount is numeric; `-` and blank give 0 | base: one row has `0` (the API value of `-`) and one has `""` | `discount_cad` is float64; both rows are `0.0`; no report entries |
| Dates load; `2026-02-30` is dropped | base; set Order Date of one row to text `"2026-02-30"` | `order_date` and `customer_since` are datetime64; the row is dropped with column `Order Date` |
| Missing `Status` raises an error | base; `drop_column(Orders, "Status")` | raises `missing_column`; message contains `Orders` and `Status` |
| ` Status ` header loads | base; `rename_header(Orders, "Status", " Status ")` | loads; report is empty |
| `Shipped` drops only that row | base; set one Status to `Shipped` | exactly 1 dropped entry, for that row and column `Status` |
| `fulfilled` is dropped | base; set one Status to `fulfilled` | that row is dropped |
| Unknown SKU | base; set one order SKU to `SKU-9999` | dropped with reason `SKU not found` |
| Unknown Customer ID | base; set one order Customer ID to `C-999` | dropped with reason `Customer not found` |
| Bad product cascades to its orders | base; set `SKU-0002` Price to `0` | the product is dropped, and every order with `SKU-0002` is dropped with `SKU not found` |
| Duplicate Order ID | base; set order #2's ID equal to order #1's | both dropped; 2 entries |
| Quantity `0` or `2.5`; Discount too large | three separate tests, each with one row changed | each row is dropped |
| Line Total 0.05 off | base; add 0.05 to one sheet Line Total | the row is kept; 1 `warning`; output holds the recomputed value |
| Line Total 0.005 off | base; add 0.005 | no report entry |
| Recomputed stats exclude Refunded | base unchanged | `units_sold`, `revenue_cad`, `order_count` and `total_spent_cad` equal the fixture's sheet values, which were worked out by hand without Refunded orders |
| Extra columns ignored | base; `add_column(Orders, "Notes")` | no `notes` column in the output |
| Exact snake_case columns and order | base | `list(df.columns)` equals the §9 list for each tab |
| Future date dropped; today loads | base; one order `2026-06-02` and one `2026-06-01` (as serial numbers) | the first is dropped, the second loads |
| Order before Customer Since | base; set an Order Date one day before that customer's Customer Since | the row is kept with a `warning` |
| Margin 0.75 | base, `SKU-0001` | `margin_pct == 0.75` (also a unit test in `test_calculations.py`) |
| Blank row mid-tab | base; `insert_blank_row(Orders, 3)` | the same output as the base data; no entries; later rows keep their real sheet row numbers |
| 6 of 100 over the threshold, 5 of 100 not | `threshold_100_orders.json`; break 6 rows, then 5 | `over_threshold` is True, then False |
| Invalid email is masked | base; set one Email to `jane.example.com` (no `@`) | the entry value is `j***`; a valid-domain case is unit-tested in `test_report.py` (`j***@example.com`); no full email appears in `repr(report)` |
| Unset `SHEET_ID` | `monkeypatch.delenv("SHEET_ID")` (`test_config.py`) | raises `config`; message contains `SHEET_ID` |
| Auth and API failures | patched gspread raising each error (`test_sheets_client.py`) | raise `auth` / `unreachable`; the fake ID and path are absent; no `Traceback` in the message |
| Header-only tab | base; `clear_data_rows(Customers)` | raises `empty_tab`, naming `Customers` |
| **Manual check** (real sheet) | none; run by hand with `.env` set | 1,000 / 10 / 150 rows and 0 dropped. Record the result in the task list. |

## 6. Order of work

Each step follows spec → tests → code, and ends with `pytest` and `ruff check` passing. One task at a time.

1. **Project setup:** `requirements*.txt`, `pyproject.toml`, the empty package, `conftest.py` with `FakeSheetsClient` and a trivial smoke test. Pin the versions.
2. **`schema.py` + `errors.py`:** test that the mapping matches spec §9.
3. **`config.py`:** environment tests.
4. **`report.py`:** masking, summaries, threshold.
5. **`parsing.py`:** structure errors, blank rows, sheet row numbers, `coerce_cell` for every type.
6. **`validation.py`, Products and Customers.**
7. **`validation.py`, Orders:** references, dates against `today`, duplicates, warnings.
8. **`calculations.py`:** each function, plus the Refunded exclusion.
9. **`loader.py`:** pipeline and `to_frames`, with all end-to-end acceptance criteria in `test_loader.py`.
10. **`sheets_client.py`:** the real adapter, with patched-gspread tests.
11. **Manual smoke check** against the real sheet, then tick off the spec's acceptance criteria.

The next SDD step is to turn these steps into `specs/001-data-source.tasks.md`, a checklist that becomes the task list in the Definition of done.

## 7. Risks and notes
- **Sheet header order and exact spelling** have not been checked against the real sheet. Task 11 checks them. If the real headers differ, stop and raise it; don't change the schema quietly.
- **Serial-number dates** use the Google Sheets epoch, 1899-12-30. The base fixture includes a known pair (serial ↔ ISO) so this is tested.
- **Float money:** comparisons use the 0.01 tolerance from spec §3. Recomputed totals are not rounded at load time.

## 8. Decisions made while planning (approved 2026-09-30)

- **D1. Duplicate keys** are checked across all non-blank rows, before any other rule. If two rows share Order ID `#1001` and one also has a bad Status, both are still dropped as duplicates.
- **D2. A blank *calculated* cell** in the sheet is not a rule break. For Line Total it means there is nothing to compare against, so no warning is recorded. Spec §3 was updated to say so.
- **D3. A sheet Product Name or Category that differs from the Products lookup** is ignored. The lookup value is used (§3.1), and no warning is recorded.
- **D4. The API timeout** is 30 seconds, with no retries. The Refresh button in spec 003 is the retry.

### Changes approved during T2 (2026-09-30)

- **D5. The column type for decimals is named `decimal`,** not `money`, to match the spec's type names. It covers the money columns and Margin %.
- **D6. Error tests live in `tests/test_errors.py`,** added to the §2 file list.
