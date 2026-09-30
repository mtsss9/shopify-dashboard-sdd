# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A Shopify sales dashboard. It reads order, product and customer data from a Google Sheet and shows KPIs and charts. It is built with spec-driven development (SDD).


## Stack

- Python 3.11+
- Streamlit (dashboard UI)
- gspread + google-auth (Google Sheets API through a service account)
- pandas (data handling)
- pytest (tests), ruff (lint and format)

## Commands

```bash
pytest                                   # run all tests
pytest tests/test_kpis.py::test_name     # run a single test
ruff check .                             # lint
ruff format .                            # format
streamlit run src/<app>.py               # run the dashboard (entry point not created yet)
```

## Workflow rules (SDD)

- Specs come first. Write no code for a feature until its spec in `specs/` has status **Approved**.
- Work in this order: spec → plan → tasks → tests → code. Never skip a step.
- The spec is the source of truth. If the code and the spec disagree, stop and ask. Do not quietly change either one.
- Make spec changes openly: propose the edit, wait for approval, then update the code.
- Do one task at a time. Finish, test and report each task before you start the next.

Specs:
- `specs/001-data-source.md`: Google Sheet ingestion
- `specs/002-kpis.md`: KPI definitions and worked examples
- `specs/003-dashboard-ui.md`: Streamlit UI

## Architecture and code rules

- All source code goes in `src/` and all tests go in `tests/`.
- KPI and data logic is pure Python with **no Streamlit imports**, so it can be tested without the UI. Streamlit is only a thin presentation layer over it.
- Tests never call the real Google Sheet. They use fixture data in `tests/fixtures/`.
- Every KPI function has at least one unit test that uses the worked examples in `specs/002-kpis.md`.
- Every function has type hints. Docstrings are short and name the spec section they implement, e.g. `Implements specs/002-kpis.md §3.`

## Business rules (apply everywhere)

- The currency is CAD.
- Orders with Status `Refunded` are left out of all revenue and units-sold figures.
- Revenue is the sum of `Line Total (CAD)`, which is already net of discount.

## Security rules

- Never read, print, edit or commit `credentials.json` or `.env`.
- Configuration comes from the environment variables `SHEET_ID` and `GOOGLE_APPLICATION_CREDENTIALS`. Never hardcode it.
- Never push the values of `SHEET_ID` or `GOOGLE_APPLICATION_CREDENTIALS` to GitHub. That includes commits, PRs, issues and comments.
- Never log full customer emails.

## Definition of done

- Tests pass (`pytest`) and lint is clean (`ruff check`).
- The task is ticked off in the feature's task list.
- Any behaviour the spec does not cover has been raised as a question, not guessed.
