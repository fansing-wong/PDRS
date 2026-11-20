"""Carve and independently validate the v6 JPEG/PDF sample set."""

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
    raise SystemExit("Install optional validation dependencies: .venv/Scripts/python.exe -m pip install -e '.[validation]'") from error


ROOT = Path(__file__).resolve().parent / "experiment_set_v6"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
RESULTS_DIR = ROOT / "results_jpeg_pdf"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    truth_path = ROOT / "ground_truth.csv"
    if not truth_path.is_file():
        raise SystemExit("Dataset not found. Run make_jpeg_pdf_set_v6.py first.")
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
        manifest = _read_csv(output_dir / "manifest.csv")
        expected_offset = int(truth["expected_offset"])
        candidate = next((row for row in manifest if int(row["offset"]) == expected_offset), None)
        target_present = truth["target_present"].lower() == "true"
        true_header = candidate is not None and target_present
        false_positive = candidate is not None and not target_present
        hash_match = candidate is not None and target_present and candidate["sha256"] == truth["source_sha256"]
        parser_success = False
        content_match = False
        parser_note = ""

        if candidate is not None:
            recovered = output_dir / candidate["filename"]
            try:
                if truth["format"] == "jpeg":
                    with Image.open(recovered) as recovered_image:
                        recovered_image.load()
                        parser_success = recovered_image.format == "JPEG"
                    if target_present and parser_success:
                        with Image.open(SOURCE_DIR / truth["source_filename"]) as source_image:
                            source_image.load()
                            with Image.open(recovered) as recovered_image:
                                recovered_image.load()
                                content_match = (
                                    source_image.format == recovered_image.format
                                    and source_image.size == recovered_image.size
                                    and source_image.tobytes() == recovered_image.tobytes()
                                )
                else:
                    recovered_pdf = PdfReader(recovered, strict=True)
                    try:
                        parser_success = len(recovered_pdf.pages) == 1
                    finally:
                        recovered_pdf.close()
                    if target_present and parser_success:
                        source_pdf = PdfReader(SOURCE_DIR / truth["source_filename"], strict=True)
                        recovered_pdf = PdfReader(recovered, strict=True)
                        try:
                            content_match = (
                                len(source_pdf.pages) == len(recovered_pdf.pages)
                                and str(source_pdf.pages[0].mediabox) == str(recovered_pdf.pages[0].mediabox)
                            )
                        finally:
                            source_pdf.close()
                            recovered_pdf.close()
            except Exception as error:
                parser_note = f"{type(error).__name__}: {error}"

        row = {
            "scenario": truth["scenario"],
            "sample_id": truth["sample_id"],
            "format": truth["format"],
            "target_present": target_present,
            "candidate_found_at_expected_offset": candidate is not None,
            "true_header_detection": true_header,
            "false_positive": false_positive,
            "sha256_exact_match": hash_match,
            "independent_parser_accepted": parser_success,
            "content_equivalent": content_match,
            "parser_error": parser_note,
        }
        details.append(row)
        grouped[str(row["scenario"])].append(row)
        if index % 10 == 0 or index == len(truths):
            print(f"Completed {index}/{len(truths)} JPEG/PDF scans")

    with (RESULTS_DIR / "sample_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)

    summaries: list[dict[str, object]] = []
    for scenario, rows in sorted(grouped.items()):
        targets = sum(bool(row["target_present"]) for row in rows)
        candidates = sum(bool(row["candidate_found_at_expected_offset"]) for row in rows)
        true_headers = sum(bool(row["true_header_detection"]) for row in rows)
        false_positives = sum(bool(row["false_positive"]) for row in rows)
        parsed = sum(bool(row["independent_parser_accepted"]) for row in rows)
        summaries.append({
            "scenario": scenario,
            "samples": len(rows),
            "true_targets": targets,
            "candidates_found": candidates,
            "true_header_detections": true_headers,
            "false_positives": false_positives,
            "exact_hash_matches": sum(bool(row["sha256_exact_match"]) for row in rows),
            "independent_parser_accepts": parsed,
            "content_equivalent": sum(bool(row["content_equivalent"]) for row in rows),
        })

    with (RESULTS_DIR / "scenario_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    print(f"Sample details:  {RESULTS_DIR / 'sample_details.csv'}")
    print(f"Scenario summary:{RESULTS_DIR / 'scenario_summary.csv'}")


if __name__ == "__main__":
    main()
