"""Compare carved candidates with a dataset ground-truth CSV."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


HASH_FIELDS = ("source_sha256", "original_sha256", "expected_sha256", "sha256")
OFFSET_FIELDS = ("expected_offset", "image_offset", "offset")
IMAGE_FIELDS = ("image_filename", "raw_image_filename")
SOURCE_NAME_FIELDS = ("source_filename", "filename", "source_name")
PRESENT_FIELDS = ("target_present", "present")
FALSE_VALUES = {"0", "false", "no", "n", "absent"}

DETAIL_FIELDS = (
    "source_filename",
    "target_present",
    "expected_offset",
    "expected_sha256",
    "recovered_filename",
    "recovered_offset",
    "sha256_match",
    "offset_match",
    "status",
)


@dataclass(frozen=True)
class GroundTruthRecord:
    source_filename: str
    target_present: bool
    expected_offset: int | None
    expected_sha256: str | None


@dataclass(frozen=True)
class EvaluationResult:
    summary: Mapping[str, int | float | str | None]
    details: tuple[Mapping[str, object], ...]
    candidate_status: Mapping[str, str]


def _header_map(fieldnames: Sequence[str | None] | None) -> dict[str, str]:
    if not fieldnames:
        raise ValueError("Ground-truth CSV has no header row.")
    return {name.strip().casefold(): name for name in fieldnames if name and name.strip()}


def _first_field(headers: Mapping[str, str], choices: Sequence[str]) -> str | None:
    return next((headers[name] for name in choices if name in headers), None)


def _csv_rows(path: Path) -> tuple[list[dict[str, str]], dict[str, str]]:
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            headers = _header_map(reader.fieldnames)
            rows = [
                {key: (value or "").strip() for key, value in row.items() if key is not None}
                for row in reader
            ]
    except (OSError, csv.Error, UnicodeError) as error:
        raise ValueError(f"Cannot read ground-truth CSV: {error}") from error
    return rows, headers


def load_ground_truth(path: Path, image_filename: str) -> list[GroundTruthRecord]:
    """Load records matching one raw image, accepting the study's common CSV schemas."""
    rows, headers = _csv_rows(path)
    hash_field = _first_field(headers, HASH_FIELDS)
    if hash_field is None:
        raise ValueError(
            "Ground-truth CSV must include source_sha256, original_sha256, expected_sha256, or sha256."
        )

    image_field = _first_field(headers, IMAGE_FIELDS)
    if image_field:
        image_key = Path(image_filename).name.casefold()
        rows = [row for row in rows if Path(row.get(image_field, "")).name.casefold() == image_key]
    else:
        scenario_field = headers.get("scenario")
        scenario_rows = (
            [row for row in rows if row.get(scenario_field, "").casefold() == Path(image_filename).stem.casefold()]
            if scenario_field
            else []
        )
        if scenario_rows:
            rows = scenario_rows
        elif len(rows) != 1:
            raise ValueError(
                "This CSV does not identify the raw image. Use a single-image CSV or one with image_filename."
            )

    if not rows:
        raise ValueError(f"No ground-truth rows match image {Path(image_filename).name}.")

    offset_field = _first_field(headers, OFFSET_FIELDS)
    name_field = _first_field(headers, SOURCE_NAME_FIELDS)
    present_field = _first_field(headers, PRESENT_FIELDS)
    records: list[GroundTruthRecord] = []
    for row_number, row in enumerate(rows, start=2):
        hash_value = row.get(hash_field, "").casefold()
        if hash_value and not re.fullmatch(r"[0-9a-f]{64}", hash_value):
            raise ValueError(f"Invalid SHA-256 value in ground-truth row {row_number}.")
        present_text = row.get(present_field, "true").casefold() if present_field else "true"
        target_present = present_text not in FALSE_VALUES

        expected_offset: int | None = None
        offset_text = row.get(offset_field, "") if offset_field else ""
        if offset_text:
            try:
                expected_offset = int(offset_text)
            except ValueError as error:
                raise ValueError(f"Invalid expected offset in ground-truth row {row_number}.") from error

        if target_present and not hash_value:
            raise ValueError(f"Missing SHA-256 in positive ground-truth row {row_number}.")
        records.append(
            GroundTruthRecord(
                source_filename=(row.get(name_field, "") if name_field else "") or f"ground_truth_row_{row_number}",
                target_present=target_present,
                expected_offset=expected_offset,
                expected_sha256=hash_value or None,
            )
        )
    return records


def evaluate_ground_truth(
    records: Sequence[GroundTruthRecord],
    candidates: Sequence[Mapping[str, object]],
) -> EvaluationResult:
    """Match candidates to expected source hashes, preferring exact offsets."""
    positive_records = [record for record in records if record.target_present]
    used_candidate_indexes: set[int] = set()
    matched_by_record: dict[int, int] = {}

    for record_index, record in enumerate(records):
        if not record.target_present or not record.expected_sha256:
            continue
        matching = [
            index
            for index, candidate in enumerate(candidates)
            if index not in used_candidate_indexes
            and str(candidate.get("sha256", "")).casefold() == record.expected_sha256
        ]
        if matching:
            matching.sort(
                key=lambda index: (
                    record.expected_offset is not None
                    and int(candidates[index].get("offset", -1)) == record.expected_offset,
                    -index,
                ),
                reverse=True,
            )
            candidate_index = matching[0]
            used_candidate_indexes.add(candidate_index)
            matched_by_record[record_index] = candidate_index

    detail_rows: list[dict[str, object]] = []
    candidate_status: dict[str, str] = {}
    offset_match_count = 0
    for record_index, record in enumerate(records):
        candidate_index = matched_by_record.get(record_index)
        recovered = candidates[candidate_index] if candidate_index is not None else None
        sha_match = recovered is not None
        offset_match = (
            sha_match
            and record.expected_offset is not None
            and int(recovered.get("offset", -1)) == record.expected_offset
        )
        if offset_match:
            offset_match_count += 1
        if record.target_present:
            status = "exact" if sha_match and offset_match else (
                "hash_match_offset_mismatch" if sha_match else "not_recovered"
            )
        elif record.expected_sha256 and any(
            str(candidate.get("sha256", "")).casefold() == record.expected_sha256 for candidate in candidates
        ):
            status = "unexpected_recovery"
        else:
            status = "correctly_absent"

        recovered_filename = str(recovered.get("filename", "")) if recovered else ""
        recovered_offset = int(recovered["offset"]) if recovered else None
        detail_rows.append(
            {
                "source_filename": record.source_filename,
                "target_present": record.target_present,
                "expected_offset": record.expected_offset,
                "expected_sha256": record.expected_sha256 or "",
                "recovered_filename": recovered_filename,
                "recovered_offset": recovered_offset,
                "sha256_match": sha_match,
                "offset_match": bool(offset_match),
                "status": status,
            }
        )
        if recovered_filename:
            candidate_status[recovered_filename] = status

    candidate_count = len(candidates)
    recovered_count = len(matched_by_record)
    expected_count = len(positive_records)
    offset_expected_count = sum(record.expected_offset is not None for record in positive_records)
    false_positive_count = candidate_count - len(used_candidate_indexes)
    summary: dict[str, int | float | str | None] = {
        "candidate_count": candidate_count,
        "expected_present_count": expected_count,
        "recovered_exact_count": recovered_count,
        "expected_offset_count": offset_expected_count,
        "offset_match_count": offset_match_count,
        "expected_absent_count": len(records) - expected_count,
        "false_positive_candidate_count": false_positive_count,
        "candidate_precision": recovered_count / candidate_count if candidate_count else None,
        "recovery_recall": recovered_count / expected_count if expected_count else None,
        "offset_match_rate": (
            offset_match_count / offset_expected_count if offset_expected_count else None
        ),
    }
    return EvaluationResult(summary, tuple(detail_rows), candidate_status)


def write_evaluation(output_dir: Path, result: EvaluationResult) -> tuple[Path, Path]:
    """Write per-source comparisons and aggregate metrics without overwriting files."""
    comparison_path = output_dir / "ground_truth_comparison.csv"
    with comparison_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(DETAIL_FIELDS))
        writer.writeheader()
        writer.writerows(result.details)

    summary_path = output_dir / "evaluation_summary.csv"
    with summary_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("metric", "value"))
        writer.writerows(result.summary.items())
    return comparison_path, summary_path
