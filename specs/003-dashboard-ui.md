# 003 Dashboard UI

**Status:** Draft
**Depends on:** 001-data-source, 002-kpis

> This spec so far covers only the data-loading behaviour moved out of spec 001. KPI display, charts and layout will be added later.

## 1. Loading and caching

- The dashboard gets its data by calling the spec 001 loader.
- Results are cached for **5 minutes**. Within that window, no new API call is made.
- A failed load (`DataSourceError`) is never cached. The next page interaction tries again.
- The cache and the refresh logic live in the UI layer. They may use Streamlit (e.g. `st.cache_data`), but the loader must not.

## 2. Refresh button

- The dashboard has a "Refresh data" button.
- Pressing it clears the cache and reloads immediately, even if the 5 minutes have not passed.

## 3. Load errors

When the loader raises a `DataSourceError`, the dashboard shows an error screen instead of the KPIs and charts. It does not crash, and it shows no stack trace.

| Category | Message shown |
|---|---|
| `config` | "Configuration missing: `<variable name>` is not set." |
| `auth` | "Could not sign in to Google Sheets. Check the service account." |
| `unreachable` | "Could not reach the Google Sheet. Try Refresh data." |
| `missing_tab` | "The sheet is missing the `<tab>` tab." |
| `missing_column` | "The `<tab>` tab is missing the `<column>` column." |
| `empty_tab` | "The `<tab>` tab has no data." |

The "Refresh data" button stays visible on the error screen.

As spec 001 §7.1 requires, messages never show the `SHEET_ID` value or the credentials path.

## 4. Data-quality indicators

- The dashboard always shows the number of dropped rows for each tab, from the validation report.
- If any tab has `over_threshold = true`, a warning banner names that tab and its drop rate, e.g. "Orders: 6.0% of rows were dropped".
- Warnings (severity `warning`) are counted separately from dropped rows and never trigger the banner.
- The dashboard never displays full customer emails.

## 5. Money display

- Money values are shown in CAD with exactly 2 decimals (e.g. `$1,234.50`).
- Rounding to 2 decimals happens **only at display time**. The spec 001 loader does not round; it keeps full precision and compares money with a 1-cent tolerance (spec 001 §3).
- Margin % is not money. It is shown as a percentage, and this rule does not apply to it.

## 6. Acceptance criteria

All criteria use a mocked loader and a controllable clock.

- [ ] Two loads within 5 minutes call the loader once.
- [ ] A load 5 minutes or more after the last one calls the loader again.
- [ ] Pressing "Refresh data" calls the loader again within the 5 minutes.
- [ ] A load that fails is not cached. The next load calls the loader again.
- [ ] Each `DataSourceError` category shows its message from §3, with no stack trace.
- [ ] The Refresh button is visible on the error screen.
- [ ] A report with a tab where `over_threshold = true` shows the banner. With none, no banner is shown.
- [ ] Dropped-row counts per tab match the report.
- [ ] A money value of `1234.5` is displayed as `$1,234.50` and `69.5` as `$69.50`, while the underlying data is unchanged.
