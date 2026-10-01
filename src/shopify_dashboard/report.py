"""Validation report. Implements specs/001-data-source.md §7.2 and §7.3."""

import re
from dataclasses import dataclass, field
from enum import StrEnum

EMAIL_COLUMN = "Email"
DROP_THRESHOLD = 0.05
_MASKED = re.compile(r"[^@]?\*\*\*(@[^@]*)?")  # already masked: re-masking is a no-op


class Severity(StrEnum):
    """How a row problem was handled. Implements specs/001-data-source.md §7.2."""

    DROPPED = "dropped"
    WARNING = "warning"


def mask_email(value: object) -> str:
    """Mask an email as first character + ``***`` + ``@domain``. Implements spec 001 §7.3.

    Without an ``@`` only the first character is kept. A blank value stays blank.
    The result is stable under re-masking.
    """
    text = str(value).strip()
    if not text or _MASKED.fullmatch(text):
        return text
    local, at, domain = text.rpartition("@")
    if not at:
        return f"{text[0]}***"
    return f"{local[:1]}***@{domain}"


@dataclass(frozen=True)
class ReportEntry:
    """One row problem. Implements specs/001-data-source.md §7.3.

    Email values are masked on construction, so no code path can store a full email.
    """

    tab: str
    row: int
    column: str
    value: object
    reason: str
    severity: Severity

    def __post_init__(self) -> None:
        if self.column == EMAIL_COLUMN:
            object.__setattr__(self, "value", mask_email(self.value))


def make_entry(
    tab: str,
    row: int,
    column: str,
    value: object,
    reason: str,
    severity: Severity = Severity.DROPPED,
) -> ReportEntry:
    """Build a report entry; Email values are masked. Implements specs/001-data-source.md §7.3."""
    return ReportEntry(tab, row, column, value, reason, severity)


@dataclass(frozen=True)
class TabSummary:
    """Per-tab counts. Implements specs/001-data-source.md §7.3."""

    rows_read: int
    rows_dropped: int

    @property
    def drop_rate(self) -> float:
        """Rows dropped ÷ data rows read; 0 when nothing was read."""
        return self.rows_dropped / self.rows_read if self.rows_read else 0.0

    @property
    def over_threshold(self) -> bool:
        """True when the drop rate is greater than 5%."""
        return self.drop_rate > DROP_THRESHOLD


@dataclass
class ValidationReport:
    """All row problems plus per-tab summaries. Implements specs/001-data-source.md §7.3."""

    entries: list[ReportEntry] = field(default_factory=list)
    summaries: dict[str, TabSummary] = field(default_factory=dict)

    def dropped(self) -> list[ReportEntry]:
        """Entries with severity ``dropped``."""
        return [e for e in self.entries if e.severity is Severity.DROPPED]

    def warnings(self) -> list[ReportEntry]:
        """Entries with severity ``warning``."""
        return [e for e in self.entries if e.severity is Severity.WARNING]
