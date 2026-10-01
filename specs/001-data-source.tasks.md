# Tasks 001: Data Source

**Spec:** `specs/001-data-source.md` (Approved)
**Plan:** `specs/001-data-source.plan.md` (Approved)

This file is the task list for the Definition of done in CLAUDE.md.

Work on one task at a time, in order. Every task follows the same steps:
1. Write the tests.
2. See them fail.
3. Write the code.
4. Run `pytest` and `ruff check` until both pass.
5. Tick the box and report back.

Do not start the next task until the current one is reported.

## Acceptance criteria key

Each ID below refers to an acceptance criterion in spec §10, in the order it appears there.

| ID | Criterion |
|---|---|
| AC-01 | Discount is numeric; `-` and blank load as `0` |
| AC-02 | Dates load as dates; `2026-02-30` is dropped and reported |
| AC-03 | Missing `Status` raises `missing_column`, naming `Orders` and `Status` |
| AC-04 | A ` Status ` header with extra spaces loads normally |
| AC-05 | A `Shipped` Status drops exactly that row and reports it |
| AC-06 | A `fulfilled` (lowercase) Status is dropped |
| AC-07 | An unknown SKU is dropped with reason `SKU not found` |
| AC-08 | An unknown Customer ID is dropped with reason `Customer not found` |
| AC-09 | A bad Products row is dropped, and so are its orders |
| AC-10 | Duplicate Order IDs are both dropped and both reported |
| AC-11 | Quantity `0`, Quantity `2.5`, and a too-large Discount are each dropped |
| AC-12 | A Line Total 0.05 off is kept as a `warning`; the output holds the recomputed value |
| AC-13 | A Line Total 0.005 off is not reported |
| AC-14 | Recomputed stats exclude Refunded and match the sheet values |
| AC-15 | Extra columns are ignored and left out of the output |
| AC-16 | Output has exactly the snake_case columns of §9, in order |
| AC-17 | A future Order Date is dropped; today's date loads |
| AC-18 | An Order Date before Customer Since is kept as a `warning` |
| AC-19 | Margin % for Price 20 and Unit Cost 5 is `0.75` |
| AC-20 | Blank rows in the middle of a tab are skipped, not reported |
| AC-21 | 6 of 100 dropped sets `over_threshold`; 5 of 100 does not |
| AC-22 | An invalid email appears masked in the report |
| AC-23 | Unset `SHEET_ID` raises `config`, naming the variable only |
| AC-24 | Auth and API failures raise `auth` and `unreachable`, with no secrets and no stack trace |
| AC-25 | A header-only tab raises `empty_tab` |
| MANUAL | The real sheet loads 1,000 / 10 / 150 rows with 0 dropped |

Planning decisions D1–D4 are listed in plan §8.

## Tasks

- [x] **T1. Project setup**
  - Create `requirements.txt`, `requirements-dev.txt`, `pyproject.toml` (pytest and ruff settings), and the empty `src/shopify_dashboard/` package.
  - In `tests/conftest.py`, add `FakeSheetsClient`, `TODAY = 2026-06-01` and the fixture mutation helpers.
  - Create `tests/fixtures/base_valid.json` and `tests/fixtures/threshold_100_orders.json`.
  - Install into `.venv`, then pin the exact versions that were resolved.
  - Add a smoke test that the base fixture loads into the fake.
  - *Covers:* no acceptance criteria (groundwork for all of them).

- [x] **T2. Schema and errors** (`schema.py`, `errors.py`)
  - Column specs, enums, province list, unique keys and the single header → snake_case mapping.
  - `ErrorCategory` and `DataSourceError`.
  - *Covers:* AC-16 (mapping and column order match §9, unit level).

- [x] **T3. Config** (`config.py`)
  - `load_config` reads the two environment variables. `Config.__repr__` hides both values.
  - *Covers:* AC-23.

- [x] **T4. Validation report** (`report.py`)
  - `ReportEntry`, `TabSummary`, `ValidationReport`, `mask_email` and `make_entry`. Every Email value passes through the mask.
  - *Covers:*
    - AC-21 (threshold at 6 vs 5 of 100, unit level);
    - AC-22 (masking formats; no full email in `repr(report)`).

- [ ] **T5. Parsing** (`parsing.py`)
  - Tab and column structure checks, header trimming, blank-row skipping, sheet row numbers and `coerce_cell` for every column type.
  - *Covers:*
    - AC-01 (a blank Discount becomes 0; the number 0 stays 0);
    - AC-02 (serial dates and strict ISO parsing; `2026-02-30` is rejected);
    - AC-03;
    - AC-04;
    - AC-11 (`2.5` is not a whole number);
    - AC-15 (extra columns are ignored);
    - AC-20;
    - AC-25;
    - D2 (a blank calculated cell is not a rule break).

- [ ] **T6. Validation: Products and Customers** (`validation.py`)
  - `validate_products` and `validate_customers`: formats, enums, numeric limits, the province list and the email `@` check.
  - *Covers:*
    - AC-09 (the bad Products row is dropped; the order side follows in T7);
    - AC-22 (an invalid email is dropped and its report entry is masked).

- [ ] **T7. Validation: Orders and duplicates** (`validation.py`)
  - `validate_orders`:
    - cell rules and Discount limits;
    - Order Date against `today`;
    - references checked against the **validated** Products and Customers;
    - a warning for a Line Total mismatch;
    - a warning for an Order Date before Customer Since.
  - `find_duplicate_keys` and `validate_all`: Products → Customers → Orders order, and per-tab summaries.
  - *Covers:*
    - AC-05, AC-06, AC-07, AC-08;
    - AC-09 (the cascade to orders);
    - AC-10;
    - AC-11 (Quantity `0`, too-large Discount);
    - AC-12 (the warning is kept, not dropped);
    - AC-13;
    - AC-17, AC-18;
    - D1 (duplicates are checked before other rules);
    - D2 (a blank sheet Line Total gives no warning).

- [ ] **T8. Calculations** (`calculations.py`)
  - `line_total`, `margin_pct` (0 when Price is 0), `enrich_orders`, `product_stats` and `customer_stats`. Refunded orders are excluded, and items with no orders get 0.
  - *Covers:*
    - AC-12 (the recomputed Line Total);
    - AC-14;
    - AC-19;
    - D3 (the lookup overrides the sheet's Product Name and Category).

- [ ] **T9. Loader** (`loader.py`, `__init__.py`)
  - `load_data(client, today)` and `LoadResult`.
  - `to_frames` handles the snake_case rename, column order and dtypes.
  - The fetch is called exactly once for each load.
  - All acceptance criteria are tested end-to-end in `test_loader.py` through `FakeSheetsClient`.
  - *Covers (end-to-end):* AC-01 to AC-22, and AC-25.

- [ ] **T10. Google Sheets adapter** (`sheets_client.py`)
  - `GspreadSheetsClient`:
    - one `batch_get`;
    - unformatted values and serial-number dates;
    - a 30-second timeout and no retries;
    - errors converted to `auth` or `unreachable`, chained with `from None`.
  - Tested with gspread patched out, so there is no network access.
  - *Covers:*
    - AC-24;
    - AC-01 (asserts the unformatted render option, which is what turns `-` into `0`);
    - D4.

- [ ] **T11. Manual check and sign-off**
  - With `.env` set locally, run `load_data()` against the real sheet once.
  - Confirm 1,000 / 10 / 150 rows with 0 dropped, and that the real headers match the schema.
  - If anything differs, stop and raise it; don't change the schema.
  - Record the result below. Tick the acceptance criteria in spec §10.
  - *Covers:* MANUAL. Final check of AC-01 to AC-25 (full `pytest` run and `ruff check` clean).

## Manual check result

*(Fill in during T11: date, row counts, dropped count, any notes. Do not paste the sheet ID or any customer data.)*
