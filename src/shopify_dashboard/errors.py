"""Load-stopping errors. Implements specs/001-data-source.md §7.1."""

from enum import StrEnum


class ErrorCategory(StrEnum):
    """Why a load stopped. Implements specs/001-data-source.md §7.1."""

    CONFIG = "config"
    AUTH = "auth"
    UNREACHABLE = "unreachable"
    MISSING_TAB = "missing_tab"
    MISSING_COLUMN = "missing_column"
    EMPTY_TAB = "empty_tab"


class DataSourceError(Exception):
    """A load failure with a category and a safe message. Implements specs/001-data-source.md §7.1.

    The message must never contain the sheet ID, the credentials path or a stack trace;
    callers are responsible for building it from names only.
    """

    def __init__(self, category: ErrorCategory, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message

    def __str__(self) -> str:
        return self.message
