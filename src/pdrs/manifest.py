"""CSV manifest serialization shared by the CLI and desktop interface."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Mapping, Sequence


MANIFEST_FIELDS = (
    "filename",
    "format",
    "offset",
    "end_offset_exclusive",
    "size_bytes",
    "complete_boundary",
    "format_valid",
    "validation_note",
    "sha256",
)


def write_manifest(output_dir: Path, rows: Sequence[Mapping[str, object]]) -> Path:
    """Create a manifest without replacing a previous scan's results."""
    manifest_path = output_dir / "manifest.csv"
    fieldnames = list(rows[0]) if rows else list(MANIFEST_FIELDS)
    with manifest_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return manifest_path
