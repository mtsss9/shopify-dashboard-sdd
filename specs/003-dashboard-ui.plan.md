# Plan 003: Dashboard UI, Phase 1 (Data Explorer)

**Spec:** `specs/003-dashboard-ui.md` (Phase 1 Approved)
**Status:** Draft, waiting for approval of the decisions in §8

This plan says *how* Phase 1 of spec 003 will be built. Where the plan and the spec disagree, the spec wins. Phase 2 (KPIs and charts) is out of scope.

## 1. Approach

All logic that can be tested without a browser is pure Python with no Streamlit import. `app.py` is a thin Streamlit script that builds widgets and passes their values to that logic.

```
run.ps1 ──► sets env vars from .env (.env wins), PYTHONPATH=src
              └─► streamlit run src/shopify_dashboard/app.py
                    │
                    ├─ cache.LoadCache.get(load_data)       5-min TTL, failures not cached (§1)
                    │     └─ "Refresh data" → LoadCache.clear() (§2)
                    │
                    ├─ DataSourceError → display.ERROR_HEADINGS[category] + error.message (§3)
                    │
                    └─ LoadResult
                          ├─ quality.banner_messages(report)               (§4)
                          ├─ Orders/Products/Customers tabs:
                          │     filters.options / default_date_range / prune_selection   → widgets
                          │     filters.filter_orders / filter_products / filter_customers
                          │     display.table_view(tab, filtered_df)       (§5, §6.3)
                          └─ Data quality tab:
                                quality.summary_frame / entries_frame      (§6.5)
```

The loader (`load_data()`) is the only part of the spec 001 data layer that `app.py` calls (§6.1).

## 2. Files

### src/shopify_dashboard/

Only `app.py` imports Streamlit. None of the other new modules do.

| File | Responsibility | Spec |
|---|---|---|
| `cache.py` | `LoadCache`: 5-minute result cache with an injectable clock; failures never stored; `clear()` | §1, §2 |
| `display.py` | Money and percent formatting, sheet-header renaming, email masking for display, the per-category error headings, the row-count text | §3, §5, §6.3 |
| `filters.py` | Filter functions, filter options, default date range, selection pruning | §6.4 |
| `quality.py` | Over-threshold banner messages, the Data quality summary and entries tables | §4, §6.5 |
| `app.py` | Streamlit script: layout, widgets, session state, calls the modules above | §1–4, §6 |

### tests/

| File | What it covers |
|---|---|
| `test_cache.py` | TTL, refresh, failures not cached, with a fake clock and a counting fake loader |
| `test_display.py` | Money/percent formatting, header names, masking, input unchanged, error headings |
| `test_filters.py` | Every filter criterion in §7.2, on fixture DataFrames |
| `test_quality.py` | Banner, summary, warning counts, entry order, "No problems found." case, raw values |
| `test_app.py` | `streamlit.testing.v1.AppTest` runs of `app.py` with `load_data` patched |
| `test_static.py` | `filters.py` (and the other pure modules) import no Streamlit; nothing in `src/` imports a dotenv library or opens `.env`; `app.py` imports nothing from the data layer except `load_data` |

### Project root

| File | Purpose |
|---|---|
| `run.ps1` | Launcher (§6.6) |

No new dependencies: `streamlit==1.64.0` is already pinned in `requirements.txt`, and `AppTest` ships with it.

## 3. Functions and responsibilities

Every function has type hints and a docstring naming the spec section, as CLAUDE.md requires.

### cache.py
- `TTL_SECONDS = 300`.
- `LoadCache(clock: Callable[[], float] = time.monotonic)`:
  - `get(load: Callable[[], LoadResult]) -> LoadResult`: returns the stored result if it is younger than 300 s; otherwise calls `load()`, stores the result with its time, and returns it. If `load()` raises, nothing is stored and the exception propagates (§1).
  - `clear() -> None`: forgets the stored result (§2).
  - A `threading.Lock` guards `get` and `clear`, because Streamlit serves sessions on several threads.
- `app.py` keeps one `LoadCache` per server process through `st.cache_resource`, so all browser sessions share it the way `st.cache_data` would. `st.cache_data` itself is not used, because its clock can't be controlled in tests (§7.1).

### display.py
- `ERROR_HEADINGS: dict[ErrorCategory, str]`: the §3 table. A test checks that every `ErrorCategory` has a heading.
- `format_money(value: float) -> str`: `1234.5` → `"$1,234.50"` (§5).
- `format_pct(value: float) -> str`: `0.75` → `"75.0%"`, `0.6667` → `"66.7%"` (§6.3).
- `MONEY_COLUMNS: dict[str, tuple[str, ...]]`: the §6.3 list, per tab.
- `table_view(tab: str, df: DataFrame) -> DataFrame`: returns a **new** DataFrame for display:
  - money columns formatted with `format_money`, `margin_pct` with `format_pct`;
  - `email` passed through `mask_email` (spec 001 `report.py`);
  - dates shown as `YYYY-MM-DD` text (decision U4);
  - columns renamed to sheet headers using the reverse of `schema.COLUMNS` (§6.3), in the same order;
  - row order unchanged. The input DataFrame is never changed.
- `row_count_text(shown: int, total: int) -> str`: `"Showing X of Y rows"` (decision U5 for number format).

### filters.py
- `options(df: DataFrame, column: str) -> list[str]`: distinct non-missing values, sorted A–Z (§6.4).
- `default_date_range(df: DataFrame) -> tuple[date, date] | None`: earliest and latest `order_date`; `None` for an empty DataFrame (decision U6).
- `prune_selection(selected: Sequence[str], available: Sequence[str]) -> list[str]`: keeps selected values still available, in their original order (§6.4, kept across refresh).
- `filter_values(df, column, selected) -> DataFrame`: empty `selected` keeps every row.
- `filter_date_range(df, column, start, end) -> DataFrame`: both ends inclusive; `start > end` keeps no rows.
- `filter_orders(df, start, end, categories, statuses, channels) -> DataFrame`, `filter_products(df, categories) -> DataFrame` and `filter_customers(df, provinces) -> DataFrame`: AND-combine the above.
- Every function returns a new DataFrame and leaves its input unchanged.

### quality.py
- `banner_messages(report: ValidationReport) -> list[str]`: one `"<Tab>: 6.0% of rows were dropped"` per over-threshold tab, in Orders, Products, Customers order (§4).
- `summary_frame(report) -> DataFrame`: columns `Tab`, `Rows read`, `Rows dropped`, `Drop rate`, `Warnings`; one row per tab in Orders, Products, Customers order. Drop rate shown with 1 decimal like the banner (decision U7).
- `entries_frame(report) -> DataFrame | None`: the six columns, sorted by tab order, then row, then column; `None` when there are no entries, so `app.py` shows "No problems found." Values are kept exactly as stored (decision U3).

### app.py
Top to bottom, on every rerun:
1. `st.set_page_config` and `st.title("Shopify Data Explorer")`.
2. `st.button("Refresh data")`; when pressed, `cache.clear()`.
3. `cache.get(load_data)` in a `try`. On `DataSourceError`: `st.error` with the heading and the message on separate lines, then `st.stop()`. No other exception handling is added, so no stack trace text is produced by our code.
4. `st.warning` for each banner message.
5. `st.tabs(["Orders", "Products", "Customers", "Data quality"])`.
6. Each table tab: widgets with per-tab `key`s, then the count, then `st.dataframe(display.table_view(...), hide_index=True)`.
   - Before each multiselect is drawn, its stored selection is pruned with `prune_selection` against the current options (§6.4 refresh rule).
   - Start and end date are two `st.date_input` widgets (decision U2). On first run they default to `default_date_range`. If start > end, `st.warning("Start date is after end date.")` and the filtered table is empty.
7. Data quality tab: `st.dataframe(summary_frame(...))`, then `st.dataframe(entries_frame(...))` or `st.write("No problems found.")`.

`app.py` imports `load_data` and `DataSourceError` from the package, plus `cache`, `display`, `filters` and `quality`. It imports nothing else from the data layer (§6.1).

### run.ps1
- `$ErrorActionPreference = 'Stop'`; works from the script's own folder (`$PSScriptRoot`), whatever the current directory.
- If `.env` is missing: `Write-Host` a message saying `.env` is missing and should be created from `.env.example`, then `exit 1`.
- Reads `.env` line by line: skips blank lines and lines starting with `#`; splits on the first `=`; trims the key and value; removes one pair of matching surrounding quotes (decision U8). A non-empty line without `=` stops the script with a message naming the line **number** only (decision U8).
- Sets each pair with `Set-Item "env:$key" $value`, which replaces any value already in the session (.env wins).
- Prepends `src` to `PYTHONPATH` so `app.py` can import `shopify_dashboard` (decision U1).
- Runs `.venv\Scripts\python.exe -m streamlit run src/shopify_dashboard/app.py`; if `.venv` is missing, stops with a message (decision U9).
- Never prints a key's value.

## 4. Testing approach

### 4.1 Pure modules
`test_cache.py`, `test_display.py`, `test_filters.py` and `test_quality.py` are plain pytest tests:
- **Clock:** a `FakeClock` object whose `now` is advanced by the test (e.g. 299 s, then 300 s).
- **Loader:** a counting fake callable that returns a `LoadResult` or raises a given `DataSourceError`.
- **DataFrames:** a real `LoadResult` from `load_data(FakeSheetsClient(base_tabs), today=TODAY)` (the spec 001 fixtures in `conftest.py`), plus small DataFrames built in the test where a case needs exact values (e.g. dates on the range boundaries).
- **Reports:** `ValidationReport` built directly with `make_entry` and `TabSummary`, so over-threshold, no-entries and mixed-value cases are explicit in each test.
- "Input unchanged" is checked by comparing against a `df.copy(deep=True)` taken before the call.

### 4.2 The Streamlit app
`test_app.py` uses `AppTest.from_file("src/shopify_dashboard/app.py")`:
- `load_data` is patched at `shopify_dashboard.load_data` with `unittest.mock.patch`, so the real sheet is never called (CLAUDE.md).
- An autouse fixture clears `st.cache_resource` before each test, so the shared `LoadCache` does not leak between tests.
- Checks: title text, button label, tab labels and order, error heading and message, no tabs on error, banner present or absent, row-count text, Refunded rows listed, masked email, "Refresh data" calls the loader again, and selections kept after refresh with a vanished value removed.
- Exact TTL timing is tested in `test_cache.py`, not here.

### 4.3 Static checks
`test_static.py` parses source files with `ast`, never by running them:
- `filters.py`, `display.py`, `quality.py` and `cache.py` import no `streamlit`.
- No file under `src/` imports `dotenv` or contains a string constant naming `.env`.
- `app.py` imports nothing from `loader`, `sheets_client`, `parsing`, `validation`, `calculations` or `config`, and uses only `load_data` from the package root.

### 4.4 Manual checks
The three launcher checks in spec §7.2 need the real `.env`. CLAUDE.md forbids Claude from reading it, so **the user runs them** and the results are recorded in the task list. Claude also never runs `run.ps1`, because it loads `.env`.

### 4.5 Acceptance-criterion map

| Spec §7 criterion | Test file |
|---|---|
| 7.1 cache within / after 5 min, failure not cached | `test_cache.py` |
| 7.1 Refresh calls the loader again | `test_cache.py` (`clear`) and `test_app.py` (button) |
| 7.1 heading + loader message per category, no stack trace; Refresh visible on error | `test_display.py` (headings), `test_app.py` |
| 7.1 banner shown / not shown; dropped counts | `test_quality.py`, `test_app.py` |
| 7.1 `1234.5` → `$1,234.50`, `69.5` → `$69.50`, data unchanged | `test_display.py` |
| 7.1 `config` unset vs placeholder share heading, no value | `test_app.py` (two `DataSourceError`s built with `load_config`'s real messages) |
| 7.2 layout and scope | `test_app.py`, `test_static.py` |
| 7.2 table tabs | `test_display.py`, `test_app.py` |
| 7.2 filters | `test_filters.py`; "one tab does not change another" and refresh pruning also in `test_app.py` |
| 7.2 data quality tab | `test_quality.py`, `test_app.py` |
| 7.2 launcher, static | `test_static.py` |
| 7.2 launcher, manual | user, recorded in the task list |

## 5. Order of work

Each step follows spec → tests → code, and ends with `pytest` and `ruff check` passing. One task at a time.

1. **`display.py`:** formatting, headings, `table_view`.
2. **`filters.py`:** all filter functions and helpers.
3. **`cache.py`:** `LoadCache` with the fake clock.
4. **`quality.py`:** banner, summary, entries.
5. **`app.py`, frame:** title, Refresh, error screen, banner, four empty tabs (AppTest).
6. **`app.py`, table tabs:** widgets, counts, tables, refresh pruning.
7. **`app.py`, Data quality tab.**
8. **`test_static.py`.**
9. **`run.ps1`**, then the user's manual checks, then tick off the spec's acceptance criteria.

The next SDD step is to turn these steps into `specs/003-dashboard-ui.tasks.md`.

## 6. Risks and notes

- **Formatted money columns are text** in the displayed table, so clicking a money column header in the browser sorts it as text, not by value. The spec does not require sorting. A numeric column with Streamlit's own formatting would sort correctly but can't be checked by pure tests. Raise again if sorting matters.
- **Mixed-type `value` column** (text, numbers, dates in one column): Streamlit's Arrow conversion may refuse it or convert it with a warning. See decision U3.
- **Shared cache:** one `LoadCache` serves every browser session, like `st.cache_data`. One user's Refresh clears it for everyone. That matches §2 for a single-user dashboard.
- **AppTest limits:** `AppTest` doesn't render the browser, so the visual order of elements is checked by element order in the script's output tree, not by pixel position.

## 7. Spec coverage

All of spec 003 §1–7 for Phase 1 is covered by §3–5 above. Phase 2 is not part of this plan.

## 8. Decisions for approval

These are details the spec leaves open. Each one needs approval before the task that uses it.

- **U1. `PYTHONPATH`.** `streamlit run` puts the script's folder on `sys.path`, not `src/`, so `import shopify_dashboard` would fail. `run.ps1` prepends `src` to `PYTHONPATH`. The alternative is an editable install (`pip install -e .`), which needs a `[build-system]` in `pyproject.toml`.
- **U2. Two date pickers.** Start and End are separate `st.date_input` widgets rather than one range picker. A range picker can't produce start > end, so the spec's warning could never show, and it returns a half-chosen range while the user is clicking.
- **U3. Report values in the table.** "Exactly as stored" is shown as `str(value)` of the stored value (e.g. `45812` stays `45812`, `"Shipped"` stays `Shipped`, blank stays empty). That is the text of the raw value, not a reformat. It avoids the Arrow error from a mixed-type column.
- **U4. Date display.** `order_date` and `customer_since` are shown as `YYYY-MM-DD`, not with a `00:00:00` time part.
- **U5. Row counts** use thousands separators: "Showing 1,000 of 1,000 rows".
- **U6. Empty DataFrame.** If every row of a tab was dropped, the tab shows "Showing 0 of 0 rows", the multiselects have no options, and the Orders date pickers are not shown.
- **U7. Drop rate format** in the summary table matches the banner: a percentage with 1 decimal (`6.0%`).
- **U8. `.env` parsing.** Blank lines and `#` comments are skipped, the line is split on the first `=`, and one pair of matching surrounding quotes is removed. A non-empty line without `=` stops the script, naming the line number but never its text.
- **U9. Python used by `run.ps1`.** The project's `.venv\Scripts\python.exe`. If `.venv` is missing, the script stops with a message instead of falling back to the system Python, which doesn't have the dependencies.
- **U10. Pure modules.** `display.py`, `filters.py`, `quality.py` and `cache.py` are new modules in the package, beyond `filters.py` and `app.py`, which spec §6 names. They follow the CLAUDE.md rule that logic stays out of Streamlit.
