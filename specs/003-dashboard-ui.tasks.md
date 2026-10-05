# Tasks 003: Dashboard UI, Phase 1 (Data Explorer)

**Spec:** `specs/003-dashboard-ui.md` (Phase 1 Approved)
**Plan:** `specs/003-dashboard-ui.plan.md` (Approved)

This file is the task list for the Definition of done in CLAUDE.md.

Work on one task at a time, in order. Every task follows the same steps:
1. Write the tests.
2. See them fail.
3. Write the code.
4. Run `pytest` and `ruff check` until both pass.
5. Tick the box and report back.

Do not start the next task until the current one is reported.

## Acceptance criteria key

Each ID below refers to an acceptance criterion in spec §7, in the order it appears there. Manual checks are M1–M4.

### §7.1 Loading, errors and data quality

| ID | Criterion |
|---|---|
| AC-01 | Two loads within 5 minutes call the loader once |
| AC-02 | A load 5 minutes or more after the last one calls the loader again |
| AC-03 | "Refresh data" calls the loader again within the 5 minutes |
| AC-04 | A failed load is not cached |
| AC-05 | Each `DataSourceError` category shows its heading and the loader's message unchanged, with no stack trace |
| AC-06 | The Refresh button is visible on the error screen |
| AC-07 | Banner shown when a tab is over threshold; not shown otherwise |
| AC-08 | Dropped-row counts per tab match the report |
| AC-09 | `1234.5` displays as `$1,234.50`, `69.5` as `$69.50`; data unchanged |
| AC-10 | `config` errors for an unset and a placeholder value both show "Configuration problem"; no value shown |

### §7.2 Layout and scope

| ID | Criterion |
|---|---|
| AC-11 | Page title is "Shopify Data Explorer" |
| AC-12 | Refresh button is above the tabs |
| AC-13 | Tabs in order Orders, Products, Customers, Data quality |
| AC-14 | On a load error: no tabs; title, Refresh button and error shown |
| AC-15 | No KPI, total or chart is shown |
| AC-16 | `app.py` calls only `load_data()` from the data layer |

### §7.2 Table tabs

| ID | Criterion |
|---|---|
| AC-17 | No filters: "Showing Y of Y rows" per tab |
| AC-18 | With filters, X is the filtered row count |
| AC-19 | Every §6.3 money column shown with `$` and exactly 2 decimals |
| AC-20 | `margin_pct` `0.75` → `75.0%`, `0.6667` → `66.7%` |
| AC-21 | Headers are the sheet headers |
| AC-22 | Rows in the loader's order |
| AC-23 | Customers table never shows a full email |
| AC-24 | Displaying a table leaves the loader's DataFrame unchanged |
| AC-25 | Refunded orders are listed |

### §7.2 Filters

| ID | Criterion |
|---|---|
| AC-26 | Order Date range is inclusive on both ends and drops orders outside it |
| AC-27 | Category, Status or Sales Channel selection on Orders keeps only matching rows |
| AC-28 | An empty selection keeps every row |
| AC-29 | Options are the distinct values in the data, sorted A–Z |
| AC-30 | Order Date range defaults to the earliest and latest `order_date` |
| AC-31 | Start after end keeps no rows and shows "Start date is after end date." |
| AC-32 | Selections kept after Refresh; vanished values removed |
| AC-33 | Two Orders filters combine with AND |
| AC-34 | Category on Products keeps only matching rows |
| AC-35 | Province on Customers keeps only matching rows |
| AC-36 | Filtering one tab does not change another tab's rows |
| AC-37 | Filter functions return a new DataFrame; input unchanged |
| AC-38 | `filters.py` does not import Streamlit |

### §7.2 Data quality tab

| ID | Criterion |
|---|---|
| AC-39 | Summary shows rows read, dropped, drop rate and warnings per tab, matching the report |
| AC-40 | Warning counts match the `warning` entries per tab |
| AC-41 | Every entry appears with its six fields |
| AC-42 | `value` shown exactly as stored |
| AC-43 | Entries sorted by tab, then row, then column |
| AC-44 | No entries → "No problems found." |
| AC-45 | An `Email` entry shows the masked value |

### §7.2 Launcher

| ID | Criterion |
|---|---|
| AC-46 | No file under `src/` imports a dotenv library or opens `.env` (static) |
| M1 | Manual: filled-in `.env` → app starts, real sheet loads, no config value printed |
| M2 | Manual: `.env` copied from `.env.example` → "Configuration problem" with the placeholder message |
| M3 | Manual: a session `SHEET_ID` different from `.env` → the `.env` value is used |
| M4 | Manual: no `.env` → missing-file message, app not started, non-zero exit |

Planning decisions U1–U11 are listed in plan §8.

## Tasks

- [x] **T1. Display helpers** (`display.py`, `tests/test_display.py`)
  - `ERROR_HEADINGS` for every `ErrorCategory`, with a test that none is missing.
  - `MONEY_FORMAT = "$%,.2f"`, `PCT_FORMAT = "%.1f%%"`, `MONEY_COLUMNS` and `number_formats(tab)` (sheet header → format string) (U11).
  - `table_view(tab, df)`:
    - money columns stay numeric and unrounded;
    - `margin_pct` × 100, still numeric;
    - `email` masked with `mask_email`;
    - dates as `YYYY-MM-DD` text (U4);
    - sheet headers in schema order; row order unchanged.
  - `row_count_text(shown, total)` with thousands separators (U5).
  - No Streamlit import.
  - *Covers:*
    - AC-05 (headings, unit level);
    - AC-09, AC-19 (format strings and numeric values; rendered text is Streamlit's, U11);
    - AC-20 (`0.75` → `75.0`, `0.6667` → `66.67`, with `PCT_FORMAT`);
    - AC-17 (count text), AC-21, AC-22, AC-23, AC-24.

- [x] **T2. Filters** (`filters.py`, `tests/test_filters.py`)
  - `options`, `default_date_range` (`None` when empty, U6), `prune_selection`, `filter_values`, `filter_date_range`, `filter_orders`, `filter_products`, `filter_customers`.
  - Tested on the spec 001 fixture `LoadResult` plus small DataFrames with dates on the range boundaries.
  - *Covers:* AC-26 to AC-35 and AC-37 at unit level (AC-30 to AC-32 also in T6).

- [ ] **T3. Cache** (`cache.py`, `tests/test_cache.py`)
  - `LoadCache` with `TTL_SECONDS = 300`, an injectable clock, `get`, `clear` and a lock.
  - `FakeClock` and a counting fake loader in the tests.
  - *Covers:* AC-01, AC-02, AC-04; AC-03 (`clear`, unit level).

- [ ] **T4. Data quality helpers** (`quality.py`, `tests/test_quality.py`)
  - `banner_messages`, `summary_frame` (drop rate with 1 decimal, U7), `entries_frame` (`None` when empty; values as `str(value)`, U3).
  - Reports built with `make_entry` and `TabSummary`.
  - *Covers:* AC-07 (messages), AC-08, AC-39 to AC-45 at unit level.

- [ ] **T5. App frame** (`app.py`, `tests/test_app.py`)
  - Page config, title, "Refresh data" button, `LoadCache` through `st.cache_resource`, error screen with `st.stop()`, banner, the four tabs (empty for now).
  - `AppTest.from_file` with `load_data` patched; autouse fixture clears `st.cache_resource`; `run(timeout=30)`.
  - *Covers:* AC-03 (button), AC-05, AC-06, AC-07, AC-10, AC-11, AC-12, AC-13, AC-14.

- [ ] **T6. App table tabs** (`app.py`, `tests/test_app.py`)
  - Per tab: row count, widgets with per-tab keys, filtered table.
  - `st.dataframe(..., hide_index=True, column_config=...)` with `NumberColumn(format=...)` built from `number_formats(tab)` (U11).
  - Start and End `st.date_input` (U2), the start-after-end warning, no date pickers on an empty Orders tab (U6).
  - Selections pruned against current options before each multiselect is drawn.
  - Tests read the column config from `at.dataframe[i].proto.columns` and the dtypes from `.value`.
  - *Covers:*
    - AC-09, AC-19, AC-20 (column config passed to `st.dataframe`; columns are numeric);
    - AC-17, AC-18, AC-21, AC-23, AC-25;
    - AC-30, AC-31, AC-32, AC-36.

- [ ] **T7. App Data quality tab** (`app.py`, `tests/test_app.py`)
  - Summary table, then the entries table or "No problems found."
  - A test that the whole app shows no chart or metric element.
  - *Covers:* AC-08, AC-39, AC-41, AC-44 (in the app); AC-15.

- [ ] **T8. Static checks** (`tests/test_static.py`)
  - `ast`-based: the four pure modules import no `streamlit`; nothing in `src/` imports `dotenv` or names `.env`; `app.py` imports nothing from the data-layer modules and uses only `load_data` (and `DataSourceError`) from the package root.
  - *Covers:* AC-16, AC-38, AC-46.

- [ ] **T9. Launcher and sign-off** (`run.ps1`)
  - Written to plan §3 (U1, U8, U9). Claude does not run it, because it loads `.env`.
  - The user runs M1–M4; results recorded below.
  - Propose (not apply) a CLAUDE.md update for the `streamlit run` command, now that the entry point exists.
  - Tick the acceptance criteria in spec §7.
  - *Covers:* M1–M4. Final check of AC-01 to AC-46 (full `pytest` run and `ruff check` clean).

## Manual check result

Not run yet.
