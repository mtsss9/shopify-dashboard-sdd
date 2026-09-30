"""Configuration from the environment. Implements specs/001-data-source.md §2 and §7.1."""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from shopify_dashboard.errors import DataSourceError, ErrorCategory

SHEET_ID_VAR = "SHEET_ID"
CREDENTIALS_VAR = "GOOGLE_APPLICATION_CREDENTIALS"


@dataclass(frozen=True, repr=False)
class Config:
    """Sheet ID and credentials path. Implements specs/001-data-source.md §2.

    ``repr`` hides both values so they can never leak into logs or error output.
    """

    sheet_id: str
    credentials_path: str

    def __repr__(self) -> str:
        return "Config(sheet_id=<hidden>, credentials_path=<hidden>)"


def load_config(env: Mapping[str, str] = os.environ) -> Config:
    """Read the two required variables. Implements specs/001-data-source.md §2 and §7.1.

    Raises ``DataSourceError(config)`` naming the first unset or blank variable. The
    message holds the variable name only, never a value.
    """
    values: dict[str, str] = {}
    for name in (SHEET_ID_VAR, CREDENTIALS_VAR):
        value = env.get(name, "").strip()
        if not value:
            raise DataSourceError(ErrorCategory.CONFIG, f"Environment variable {name} is not set.")
        values[name] = value
    return Config(sheet_id=values[SHEET_ID_VAR], credentials_path=values[CREDENTIALS_VAR])
