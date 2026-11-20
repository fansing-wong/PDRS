"""Run the updated PNG structure validator on every v2 image once."""

from __future__ import annotations

import csv
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "experiment_set_v2"
IMAGE_DIR = ROOT / "images"
RESULTS_DIR = ROOT / "results_png_validation"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    truth_path = ROOT / "ground_truth.csv"
    if not truth_path.is_file():
        raise SystemExit("Dataset not found. Run make_research_set_v2.py first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")

    truth_rows = _read_csv(truth_path)
    RESULTS_DIR.mkdir(parents=True)
    details: list[dict[str, object]] = []
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)

    for index, truth in enumerate(truth_rows, start=1):
        scenario = truth["scenario"]
        sample_id = truth["sample_id"]
        expected_offset = int(truth["expected_offset"])
        target_present = truth["target_present"].lower() == "true"
        image_path = IMAGE_DIR / truth["image_filename"]
        output_dir = RESULTS_DIR / scenario / sample_id

        started = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, "-m", "pdrs.cli", str(image_path), str(output_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        elapsed = time.perf_counter() - started
        if completed.returncode != 0:
            raise RuntimeError(f"Validation scan failed for {scenario}/{sample_id}:\n{completed.stderr}")

        manifest = _read_csv(output_dir / "manifest.csv")
        true_headers = 0 if not target_present else sum(
            int(candidate["offset"]) == expected_offset for candidate in manifest
        )
        exact_matches = 0 if not target_present else sum(
            candidate["sha256"] == truth["original_sha256"] for candidate in manifest
        )
        valid_candidates = sum(candidate["format_valid"].lower() == "true" for candidate in manifest)
        valid_true_candidates = 0 if not target_present else sum(
            int(candidate["offset"]) == expected_offset and candidate["format_valid"].lower() == "true"
            for candidate in manifest
        )
        false_positives = len(manifest) if not target_present else len(manifest) - true_headers
        false_positive_valid = sum(
            candidate["format_valid"].lower() == "true"
            and (not target_present or int(candidate["offset"]) != expected_offset)
            for candidate in manifest
        )

        row = {
            "scenario": scenario,
            "sample_id": sample_id,
            "candidate_count": len(manifest),
            "true_header_candidates": true_headers,
            "false_positive_candidates": false_positives,
            "format_valid_candidates": valid_candidates,
            "format_valid_true_candidates": valid_true_candidates,
            "false_positive_candidates_marked_valid": false_positive_valid,
            "exact_sha256_matches": exact_matches,
            "runtime_seconds": f"{elapsed:.6f}",
        }
        details.append(row)
        grouped[scenario].append(row)
        if index % 10 == 0 or index == len(truth_rows):
            print(f"Completed {index}/{len(truth_rows)} validation scans")

    with (RESULTS_DIR / "sample_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)

    summaries: list[dict[str, object]] = []
    for scenario, rows in sorted(grouped.items()):
        candidates = sum(int(row["candidate_count"]) for row in rows)
        headers = sum(int(row["true_header_candidates"]) for row in rows)
        false_positives = sum(int(row["false_positive_candidates"]) for row in rows)
        valid = sum(int(row["format_valid_candidates"]) for row in rows)
        valid_true = sum(int(row["format_valid_true_candidates"]) for row in rows)
        fp_valid = sum(int(row["false_positive_candidates_marked_valid"]) for row in rows)
        exact = sum(int(row["exact_sha256_matches"]) for row in rows)
        summaries.append({
            "scenario": scenario,
            "independent_samples": len(rows),
            "candidate_count": candidates,
            "true_header_candidates": headers,
            "false_positive_candidates": false_positives,
            "format_valid_candidates": valid,
            "valid_candidate_precision": "N/A" if valid == 0 else f"{valid_true / valid:.4f}",
            "false_positive_validation_rejections": "N/A" if false_positives == 0 else f"{(false_positives - fp_valid) / false_positives:.4f}",
            "exact_sha256_matches": exact,
            "mean_runtime_seconds": f"{sum(float(row['runtime_seconds']) for row in rows) / len(rows):.6f}",
        })

    with (RESULTS_DIR / "scenario_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)

    print(f"Sample details:  {RESULTS_DIR / 'sample_details.csv'}")
    print(f"Scenario summary:{RESULTS_DIR / 'scenario_summary.csv'}")


if __name__ == "__main__":
    main()
