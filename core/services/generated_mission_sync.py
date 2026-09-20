"""Orchestration helpers for synchronizing generated mission CSV files.

The importer remains the single source of truth for CSV normalization and
database writes.  This module only discovers files, isolates failures per
file, and aggregates operator-facing counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Callable


IMPORT_SUMMARY_PATTERN = re.compile(
    r"Import complete:\s*"
    r"files=(?P<files>\d+),\s*"
    r"created=(?P<created>\d+),\s*"
    r"updated=(?P<updated>\d+),\s*"
    r"skipped=(?P<skipped>\d+),\s*"
    r"invalidated_attempts=(?P<invalidated_attempts>\d+),\s*"
    r"affected_users=(?P<affected_users>\d+)"
)


@dataclass(frozen=True)
class ImportCounts:
    files: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    invalidated_attempts: int = 0
    affected_users: int = 0

    def __add__(self, other: "ImportCounts") -> "ImportCounts":
        return ImportCounts(
            files=self.files + other.files,
            created=self.created + other.created,
            updated=self.updated + other.updated,
            skipped=self.skipped + other.skipped,
            invalidated_attempts=self.invalidated_attempts + other.invalidated_attempts,
            affected_users=self.affected_users + other.affected_users,
        )


@dataclass(frozen=True)
class FileSyncResult:
    path: Path
    counts: ImportCounts = ImportCounts()
    error: str = ""
    details: str = ""

    @property
    def succeeded(self) -> bool:
        return not self.error


@dataclass
class GeneratedMissionSyncReport:
    source_dir: Path
    counts: ImportCounts = ImportCounts()
    errors: int = 0
    results: list[FileSyncResult] = field(default_factory=list)


def discover_generated_csvs(source_dir: Path) -> list[Path]:
    """Return every generated CSV in deterministic order."""
    resolved = Path(source_dir).resolve()
    if not resolved.is_dir():
        raise ValueError(f"Generated mission directory does not exist: {resolved}")
    csv_paths = sorted(path for path in resolved.rglob("*.csv") if path.is_file())
    if not csv_paths:
        raise ValueError(f"No CSV files found: {resolved}")
    return csv_paths


def parse_import_counts(output: str) -> ImportCounts:
    """Parse the stable summary emitted by ``import_missions``."""
    match = IMPORT_SUMMARY_PATTERN.search(output)
    if match is None:
        raise ValueError("import_missions did not emit a recognizable summary")
    return ImportCounts(**{key: int(value) for key, value in match.groupdict().items()})


def sync_generated_csvs(
    source_dir: Path,
    *,
    import_file: Callable[[Path], tuple[ImportCounts, str]],
) -> GeneratedMissionSyncReport:
    """Import generated CSVs independently and continue after file failures.

    ``import_file`` is injected by the management command so this service does
    not duplicate or depend on the importer implementation.  Each importer
    call owns its database transaction, preventing one malformed file from
    rolling back other valid files.
    """
    source_dir = Path(source_dir).resolve()
    report = GeneratedMissionSyncReport(source_dir=source_dir)

    for csv_path in discover_generated_csvs(source_dir):
        try:
            counts, details = import_file(csv_path)
        except Exception as error:  # The command records the concrete failure.
            result = FileSyncResult(
                path=csv_path,
                error=f"{type(error).__name__}: {error}",
            )
            report.errors += 1
        else:
            result = FileSyncResult(path=csv_path, counts=counts, details=details)
            report.counts = report.counts + counts
        report.results.append(result)

    return report
