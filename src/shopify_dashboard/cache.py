"""Load cache for the dashboard. Implements specs/003-dashboard-ui.md §1 and §2.

No Streamlit import. ``app.py`` keeps one ``LoadCache`` per server process through
``st.cache_resource``; the clock is injectable so the TTL can be tested (plan 003 §3).
"""

import threading
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

TTL_SECONDS = 300
"""How long a successful load is reused. Implements specs/003-dashboard-ui.md §1."""


class LoadCache:
    """Stores the last successful load for ``TTL_SECONDS``. Implements spec 003 §1 and §2.

    A failed load is never stored. One lock guards ``get`` and ``clear``, so concurrent
    sessions make a single loader call.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._value: object = None
        self._loaded_at: float | None = None

    def get(self, load: Callable[[], T]) -> T:
        """Return the stored result if younger than the TTL; otherwise call ``load``.

        Implements specs/003-dashboard-ui.md §1. If ``load`` raises, nothing is stored and
        the exception propagates.
        """
        with self._lock:
            now = self._clock()
            if self._loaded_at is not None and now - self._loaded_at < TTL_SECONDS:
                return self._value  # type: ignore[return-value]
            self._value, self._loaded_at = None, None
            value = load()
            self._value, self._loaded_at = value, now
            return value

    def clear(self) -> None:
        """Forget the stored result. Implements specs/003-dashboard-ui.md §2."""
        with self._lock:
            self._value, self._loaded_at = None, None
