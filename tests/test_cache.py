"""Tests for cache.py. Implements specs/003-dashboard-ui.md §1 and §2.

Covers T3 in specs/003-dashboard-ui.tasks.md: AC-01, AC-02, AC-04, and AC-03 at unit
level (``clear``). A fake clock and a counting fake loader replace time and the sheet.
"""

import threading
import time

import pytest

from shopify_dashboard import cache
from shopify_dashboard.errors import DataSourceError, ErrorCategory


class FakeClock:
    """A clock the test moves forward by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeLoader:
    """Counts calls; returns a new result each call, or raises the queued errors first."""

    def __init__(self, errors: list[Exception] | None = None, delay: float = 0.0) -> None:
        self.calls = 0
        self._errors = list(errors or [])
        self._delay = delay

    def __call__(self) -> object:
        self.calls += 1
        if self._delay:
            time.sleep(self._delay)
        if self._errors:
            raise self._errors.pop(0)
        return f"result-{self.calls}"


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store(clock: FakeClock) -> cache.LoadCache:
    return cache.LoadCache(clock=clock)


def _error() -> DataSourceError:
    return DataSourceError(ErrorCategory.UNREACHABLE, "Could not reach the sheet.")


def test_ttl_is_five_minutes() -> None:
    assert cache.TTL_SECONDS == 300


def test_two_loads_within_ttl_call_loader_once(clock: FakeClock, store: cache.LoadCache) -> None:
    """AC-01."""
    load = FakeLoader()
    first = store.get(load)
    clock.now += 299.9
    assert store.get(load) is first
    assert load.calls == 1


@pytest.mark.parametrize("elapsed", [300.0, 300.1, 3600.0])
def test_load_at_or_after_ttl_calls_loader_again(
    clock: FakeClock, store: cache.LoadCache, elapsed: float
) -> None:
    """AC-02: 5 minutes or more after the last load."""
    load = FakeLoader()
    store.get(load)
    clock.now += elapsed
    assert store.get(load) == "result-2"
    assert load.calls == 2


def test_ttl_counts_from_the_latest_load(clock: FakeClock, store: cache.LoadCache) -> None:
    load = FakeLoader()
    store.get(load)
    clock.now += 300
    store.get(load)  # reload at t=300
    clock.now += 299
    store.get(load)  # still within the new window
    assert load.calls == 2


def test_clear_forces_reload_within_ttl(clock: FakeClock, store: cache.LoadCache) -> None:
    """AC-03 (unit level): Refresh clears the cache and the next get reloads."""
    load = FakeLoader()
    store.get(load)
    clock.now += 10
    store.clear()
    assert store.get(load) == "result-2"
    assert load.calls == 2


def test_clear_on_empty_cache(store: cache.LoadCache) -> None:
    store.clear()
    load = FakeLoader()
    assert store.get(load) == "result-1"


def test_failed_load_is_not_cached(store: cache.LoadCache) -> None:
    """AC-04: the error propagates and the next get calls the loader again."""
    error = _error()
    load = FakeLoader(errors=[error])
    with pytest.raises(DataSourceError) as raised:
        store.get(load)
    assert raised.value is error
    assert store.get(load) == "result-2"
    assert load.calls == 2


def test_failures_in_a_row_each_call_loader(store: cache.LoadCache) -> None:
    load = FakeLoader(errors=[_error(), _error()])
    for _ in range(2):
        with pytest.raises(DataSourceError):
            store.get(load)
    assert store.get(load) == "result-3"
    assert load.calls == 3


def test_failure_after_expiry_does_not_return_stale_result(
    clock: FakeClock, store: cache.LoadCache
) -> None:
    load = FakeLoader()
    store.get(load)
    clock.now += 300
    failing = FakeLoader(errors=[_error()])
    with pytest.raises(DataSourceError):
        store.get(failing)
    assert store.get(load) == "result-2"


def test_failure_after_clear_then_success(clock: FakeClock, store: cache.LoadCache) -> None:
    """Refresh during an outage shows the error; the next interaction tries again."""
    load = FakeLoader()
    store.get(load)
    store.clear()
    with pytest.raises(DataSourceError):
        store.get(FakeLoader(errors=[_error()]))
    assert store.get(load) == "result-2"


def test_default_clock_is_monotonic() -> None:
    load = FakeLoader()
    store = cache.LoadCache()
    store.get(load)
    store.get(load)
    assert load.calls == 1


def test_concurrent_gets_load_once(store: cache.LoadCache) -> None:
    """Sessions share one cache; simultaneous first loads make one sheet call."""
    load = FakeLoader(delay=0.05)
    results: list[object] = []
    threads = [threading.Thread(target=lambda: results.append(store.get(load))) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert load.calls == 1
    assert results == ["result-1"] * 5
