"""Evaluate detection, boundary status, and parser outcomes on v7 truncations."""

from __future__ import annotations

import csv
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

try:
    from PIL import Image
    from pypdf import PdfReader
except ImportError as error:
    raise SystemExit("Install optional validation dependencies with: .venv/Scripts/python.exe -m pip install -e '.[validation]'") from error


ROOT = Path(__file__).resolve().parent / "experiment_set_v7"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
RESULTS_DIR = ROOT / "results_truncation_content"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _independent_parse(path: Path, fmt: str) -> tuple[bool, str]:
    try:
        if fmt == "jpeg":
            with Image.open(path) as image:
                image.load()
                return image.format == "JPEG", "Pillow decoded JPEG"
        reader = PdfReader(path, strict=True)
        try:
            return len(reader.pages) > 0, f"pypdf parsed {len(reader.pages)} page(s)"
        finally:
            reader.close()
    except Exception as error:
        return False, f"{type(error).__name__}: {error}"


def _content_equivalent(recovered: Path, original: Path, fmt: str) -> bool:
    if fmt == "jpeg":
        with Image.open(original) as source_image:
            source_image.load()
            with Image.open(recovered) as recovered_image:
                recovered_image.load()
                return (
                    source_image.format == recovered_image.format == "JPEG"
                    and source_image.size == recovered_image.size
                    and source_image.tobytes() == recovered_image.tobytes()
                )
    source_pdf = PdfReader(original, strict=True)
    recovered_pdf = PdfReader(recovered, strict=True)
    try:
        return (
            len(source_pdf.pages) == len(recovered_pdf.pages)
            and all(
                str(source_page.mediabox) == str(recovered_page.mediabox)
                for source_page, recovered_page in zip(source_pdf.pages, recovered_pdf.pages)
            )
        )
    finally:
        source_pdf.close()
        recovered_pdf.close()


def main() -> None:
    truth_path = ROOT / "ground_truth.csv"
    if not truth_path.is_file():
        raise SystemExit("Dataset not found. Run make_truncation_set_v7.py first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True)
    details: list[dict[str, object]] = []
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)

    truths = _read_csv(truth_path)
    for index, truth in enumerate(truths, start=1):
        output_dir = RESULTS_DIR / truth["scenario"] / truth["sample_id"]
        result = subprocess.run(
            [sys.executable, "-m", "pdrs.cli", str(IMAGE_DIR / truth["image_filename"]), str(output_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"PDRS scan failed for {truth['scenario']}/{truth['sample_id']}:\n{result.stderr}")
        with (output_dir / "manifest.csv").open(newline="", encoding="utf-8") as handle:
            manifest = list(csv.DictReader(handle))
        candidate = next((row for row in manifest if int(row["offset"]) == int(truth["expected_offset"])), None)
        candidate_path = None if candidate is None else output_dir / candidate["filename"]
        complete_boundary = candidate is not None and candidate["complete_boundary"].lower() == "true"
        pdrs_valid = candidate is not None and candidate["format_valid"].lower() == "true"
        hash_match = candidate is not None and candidate["sha256"] == truth["original_sha256"]
        parser_accepted, parser_note = (False, "No candidate emitted") if candidate_path is None else _independent_parse(candidate_path, truth["format"])
        content_equivalent = False
        if candidate_path is not None and parser_accepted:
            try:
                content_equivalent = _content_equivalent(
                    candidate_path,
                    SOURCE_DIR / truth["source_filename"],
                    truth["format"],
                )
            except Exception:
                content_equivalent = False

        row = {
            "scenario": truth["scenario"],
            "sample_id": truth["sample_id"],
            "format": truth["format"],
            "candidate_found": candidate is not None,
            "candidate_size_bytes": 0 if candidate is None else int(candidate["size_bytes"]),
            "included_source_bytes": int(truth["included_source_bytes"]),
            "complete_boundary": complete_boundary,
            "pdrs_format_valid": pdrs_valid,
            "sha256_exact_match": hash_match,
            "independent_parser_accepted": parser_accepted,
            "decoded_content_equivalent": content_equivalent,
            "parser_note": parser_note,
        }
        details.append(row)
        grouped[str(row["scenario"])].append(row)
        if index % 10 == 0 or index == len(truths):
            print(f"Completed {index}/{len(truths)} truncation scans")

    with (RESULTS_DIR / "sample_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)

    summaries: list[dict[str, object]] = []
    for scenario, rows in sorted(grouped.items()):
        summaries.append({
            "scenario": scenario,
            "samples": len(rows),
            "candidate_detections": sum(bool(row["candidate_found"]) for row in rows),
            "complete_boundaries": sum(bool(row["complete_boundary"]) for row in rows),
            "pdrs_format_valid": sum(bool(row["pdrs_format_valid"]) for row in rows),
            "exact_sha256_matches": sum(bool(row["sha256_exact_match"]) for row in rows),
            "independent_parser_accepts": sum(bool(row["independent_parser_accepted"]) for row in rows),
            "decoded_content_equivalent": sum(bool(row["decoded_content_equivalent"]) for row in rows),
        })
    with (RESULTS_DIR / "scenario_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    print(f"Sample details:  {RESULTS_DIR / 'sample_details.csv'}")
    print(f"Scenario summary:{RESULTS_DIR / 'scenario_summary.csv'}")


if __name__ == "__main__":
    main()
