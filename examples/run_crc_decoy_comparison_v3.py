"""Evaluate current PNG structure/CRC validation against stronger decoys."""

from __future__ import annotations

import csv
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "experiment_set_v3"
IMAGE_DIR = ROOT / "images"
RESULTS_DIR = ROOT / "results_png_decode_validation"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    ground_truth_path = ROOT / "ground_truth.csv"
    if not ground_truth_path.is_file():
        raise SystemExit("Dataset not found. Run make_crc_decoy_set_v3.py first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")

    truths = _read_csv(ground_truth_path)
    RESULTS_DIR.mkdir(parents=True)
    details: list[dict[str, object]] = []
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)

    for index, truth in enumerate(truths, start=1):
        scenario = truth["scenario"]
        sample_id = truth["sample_id"]
        target_present = truth["target_present"].lower() == "true"
        expected_offset = int(truth["expected_offset"])
        expected_hash = truth["original_sha256"]
        output_dir = RESULTS_DIR / scenario / sample_id
        started = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-m", "pdrs.cli", str(IMAGE_DIR / truth["image_filename"]), str(output_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        elapsed = time.perf_counter() - started
        if result.returncode != 0:
            raise RuntimeError(f"Scan failed for {scenario}/{sample_id}:\n{result.stderr}")

        with (output_dir / "manifest.csv").open(newline="", encoding="utf-8") as handle:
            candidates = list(csv.DictReader(handle))
        true_headers = 0 if not target_present else sum(
            int(row["offset"]) == expected_offset for row in candidates
        )
        exact_hashes = 0 if not target_present else sum(
            row["sha256"] == expected_hash for row in candidates
        )
        structure_valid = sum(row["format_valid"].lower() == "true" for row in candidates)
        valid_true_headers = 0 if not target_present else sum(
            int(row["offset"]) == expected_offset and row["format_valid"].lower() == "true"
            for row in candidates
        )
        false_positive_candidates = len(candidates) if not target_present else len(candidates) - true_headers
        false_positive_valid = sum(
            row["format_valid"].lower() == "true"
            and (not target_present or int(row["offset"]) != expected_offset)
            for row in candidates
        )
        row = {
            "scenario": scenario,
            "sample_id": sample_id,
            "candidate_count": len(candidates),
            "true_header_candidates": true_headers,
            "false_positive_candidates": false_positive_candidates,
            "structure_valid_candidates": structure_valid,
            "structure_valid_true_candidates": valid_true_headers,
            "false_positive_candidates_marked_valid": false_positive_valid,
            "exact_sha256_matches": exact_hashes,
            "runtime_seconds": f"{elapsed:.6f}",
        }
        details.append(row)
        grouped[scenario].append(row)
        if index % 10 == 0 or index == len(truths):
            print(f"Completed {index}/{len(truths)} scans")

    with (RESULTS_DIR / "sample_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)

    summaries: list[dict[str, object]] = []
    for scenario, rows in sorted(grouped.items()):
        candidates = sum(int(row["candidate_count"]) for row in rows)
        true_headers = sum(int(row["true_header_candidates"]) for row in rows)
        false_positives = sum(int(row["false_positive_candidates"]) for row in rows)
        valid = sum(int(row["structure_valid_candidates"]) for row in rows)
        valid_true = sum(int(row["structure_valid_true_candidates"]) for row in rows)
        fp_valid = sum(int(row["false_positive_candidates_marked_valid"]) for row in rows)
        hashes = sum(int(row["exact_sha256_matches"]) for row in rows)
        summaries.append({
            "scenario": scenario,
            "independent_samples": len(rows),
            "candidate_count": candidates,
            "true_header_candidates": true_headers,
            "false_positive_candidates": false_positives,
            "structure_valid_candidates": valid,
            "structure_valid_candidate_precision": "N/A" if valid == 0 else f"{valid_true / valid:.4f}",
            "false_positive_rejection_rate": "N/A" if false_positives == 0 else f"{(false_positives - fp_valid) / false_positives:.4f}",
            "exact_sha256_matches": hashes,
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
