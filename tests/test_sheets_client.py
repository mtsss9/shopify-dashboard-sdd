"""Tests for sheets_client.py with gspread patched out (no network).

Implements specs/001-data-source.md §2, §3, §7.1 and §8 (AC-01 render option, AC-24, D4).
"""

import json
from unittest.mock import MagicMock, patch

import google.auth.exceptions as gauth
import gspread
import pytest
import requests

from conftest import TABS, TODAY
from shopify_dashboard import load_data
from shopify_dashboard.config import Config
from shopify_dashboard.errors import DataSourceError, ErrorCategory
from shopify_dashboard.sheets_client import GspreadSheetsClient

FAKE_ID = "fake-sheet-id-123"
FAKE_PATH = "C:/fake/dir/service-key.json"
CONFIG = Config(sheet_id=FAKE_ID, credentials_path=FAKE_PATH)
PATCH = "shopify_dashboard.sheets_client.gspread.service_account"


def fake_gspread(titles: list[str], values: dict[str, list] | None = None) -> MagicMock:
    """A patched gspread client whose sheet has ``titles`` and returns ``values``."""
    client = MagicMock()
    http = client.http_client
    http.fetch_sheet_metadata.return_value = {
        "sheets": [{"properties": {"title": t}} for t in titles]
    }

    def batch(sheet_id: str, ranges: list[str], params: dict) -> dict:
        names = [r.strip("'") for r in ranges]
        value_ranges = []
        for name in names:
            vr = {"range": f"{name}!A1:Z100", "majorDimension": "ROWS"}
            if values and values.get(name):
                vr["values"] = values[name]
            value_ranges.append(vr)
        return {"spreadsheetId": sheet_id, "valueRanges": value_ranges}

    http.values_batch_get.side_effect = batch
    return client


def api_error(status: int, body: bytes | None = None) -> gspread.exceptions.APIError:
    response = requests.Response()
    response.status_code = status
    response._content = (
        body
        or json.dumps(
            {"error": {"code": status, "message": f"Requested entity {FAKE_ID} failed"}}
        ).encode()
    )
    return gspread.exceptions.APIError(response)


# --- Reading ---------------------------------------------------------------------------


def test_reads_all_tabs_in_one_batch() -> None:
    """Spec §8: one metadata lookup, then exactly one batch of value reads."""
    client = fake_gspread(list(TABS), {"Orders": [["Order ID"], ["#1001"]]})
    with patch(PATCH, return_value=client) as service_account:
        raw = GspreadSheetsClient(CONFIG).fetch_tabs(TABS)

    service_account.assert_called_once_with(
        filename=FAKE_PATH,
        scopes=gspread.auth.READONLY_SCOPES,
        http_client=gspread.http_client.HTTPClient,  # no BackOffHTTPClient: no retries (D4)
    )
    http = client.http_client
    http.fetch_sheet_metadata.assert_called_once_with(
        FAKE_ID, params={"fields": "sheets.properties.title"}
    )
    assert http.values_batch_get.call_count == 1
    sheet_id, ranges = http.values_batch_get.call_args.args
    assert (sheet_id, ranges) == (FAKE_ID, ["'Products'", "'Customers'", "'Orders'"])
    assert raw == {"Products": [], "Customers": [], "Orders": [["Order ID"], ["#1001"]]}


def test_requests_unformatted_values_and_serial_dates() -> None:
    """AC-01 and spec §3: unformatted values turn a `-` display into 0."""
    client = fake_gspread(list(TABS))
    with patch(PATCH, return_value=client):
        GspreadSheetsClient(CONFIG).fetch_tabs(TABS)
    params = client.http_client.values_batch_get.call_args.kwargs["params"]
    assert params == {
        "valueRenderOption": "UNFORMATTED_VALUE",
        "dateTimeRenderOption": "SERIAL_NUMBER",
        "majorDimension": "ROWS",
    }


def test_timeout_is_30_seconds() -> None:
    """D4."""
    client = fake_gspread(list(TABS))
    with patch(PATCH, return_value=client):
        GspreadSheetsClient(CONFIG).fetch_tabs(TABS)
    client.set_timeout.assert_called_once_with(30)


def test_returns_only_tabs_that_exist() -> None:
    client = fake_gspread(["Orders", "Products", "Notes"])
    with patch(PATCH, return_value=client):
        raw = GspreadSheetsClient(CONFIG).fetch_tabs(TABS)
    assert set(raw) == {"Products", "Orders"}
    assert client.http_client.values_batch_get.call_args.args[1] == ["'Products'", "'Orders'"]


def test_no_existing_tabs_makes_no_value_read() -> None:
    client = fake_gspread(["Sheet1"])
    with patch(PATCH, return_value=client):
        assert GspreadSheetsClient(CONFIG).fetch_tabs(TABS) == {}
    client.http_client.values_batch_get.assert_not_called()


def test_tab_names_are_quoted_for_a1_ranges() -> None:
    client = fake_gspread(["Bob's Orders"])
    with patch(PATCH, return_value=client):
        GspreadSheetsClient(CONFIG).fetch_tabs(["Bob's Orders"])
    assert client.http_client.values_batch_get.call_args.args[1] == ["'Bob''s Orders'"]


# --- Error mapping (AC-24) -------------------------------------------------------------


def assert_safe(err: DataSourceError) -> None:
    """No sheet ID, no credentials path, no stack trace, no chained cause."""
    text = str(err) + repr(err)
    assert FAKE_ID not in text
    assert FAKE_PATH not in text
    assert "Traceback" not in text
    assert err.__cause__ is None and err.__suppress_context__


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError(2, "No such file", FAKE_PATH),
        ValueError(f"Service account info was not in the expected format: {FAKE_PATH}"),
        gauth.DefaultCredentialsError(f"bad key {FAKE_PATH}"),
    ],
)
def test_credential_file_errors_raise_auth(error: Exception) -> None:
    with patch(PATCH, side_effect=error), pytest.raises(DataSourceError) as info:
        GspreadSheetsClient(CONFIG).fetch_tabs(TABS)
    assert info.value.category is ErrorCategory.AUTH
    assert_safe(info.value)


@pytest.mark.parametrize(
    "error",
    [
        gauth.RefreshError(f"invalid_grant for {FAKE_ID}"),
        api_error(401),
        api_error(403),  # the sheet is not shared with the service account (D25)
        api_error(403, body=b"<html>Forbidden</html>"),  # unparseable body: status still counts
    ],
)
def test_sign_in_and_permission_failures_raise_auth(error: Exception) -> None:
    client = fake_gspread(list(TABS))
    client.http_client.fetch_sheet_metadata.side_effect = error
    with patch(PATCH, return_value=client), pytest.raises(DataSourceError) as info:
        GspreadSheetsClient(CONFIG).fetch_tabs(TABS)
    assert info.value.category is ErrorCategory.AUTH
    assert_safe(info.value)


@pytest.mark.parametrize(
    "error",
    [
        requests.exceptions.Timeout(f"timed out reading {FAKE_ID}"),
        requests.exceptions.ConnectionError("connection refused"),
        gauth.TransportError("token endpoint unreachable"),  # a GoogleAuthError subclass
        api_error(404),  # e.g. a wrong SHEET_ID
        api_error(429),
        api_error(500),
    ],
)
def test_api_and_network_errors_raise_unreachable(error: Exception) -> None:
    client = fake_gspread(list(TABS))
    client.http_client.values_batch_get.side_effect = error
    with patch(PATCH, return_value=client), pytest.raises(DataSourceError) as info:
        GspreadSheetsClient(CONFIG).fetch_tabs(TABS)
    assert info.value.category is ErrorCategory.UNREACHABLE
    assert_safe(info.value)


def test_client_repr_hides_config() -> None:
    text = repr(GspreadSheetsClient(CONFIG))
    assert FAKE_ID not in text and FAKE_PATH not in text


# --- load_data without a client (completes D23) ----------------------------------------


def test_load_data_builds_the_real_client_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, base_tabs: dict
) -> None:
    monkeypatch.setenv("SHEET_ID", FAKE_ID)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", FAKE_PATH)
    client = fake_gspread(list(TABS), base_tabs)
    with patch(PATCH, return_value=client):
        result = load_data(today=TODAY)
    assert (len(result.orders), len(result.products), len(result.customers)) == (8, 4, 3)
    assert client.http_client.values_batch_get.call_count == 1


def test_load_data_without_config_never_touches_gspread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHEET_ID", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", FAKE_PATH)
    with patch(PATCH) as service_account, pytest.raises(DataSourceError) as info:
        load_data(today=TODAY)
    assert info.value.category is ErrorCategory.CONFIG
    service_account.assert_not_called()
