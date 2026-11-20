"""Run the 40-image v2 dataset five times and calculate per-scenario metrics."""

from __future__ import annotations

import csv
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "experiment_set_v2"
IMAGE_DIR = ROOT / "images"
RESULTS_DIR = ROOT / "results_10x5"
TRIALS = 5


def _read_ground_truth() -> list[dict[str, str]]:
    with (ROOT / "ground_truth.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    ground_truth_path = ROOT / "ground_truth.csv"
    if not ground_truth_path.is_file():
        raise SystemExit("Dataset not found. Run make_research_set_v2.py first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")

    rows = _read_ground_truth()
    RESULTS_DIR.mkdir(parents=True)
    run_rows: list[dict[str, object]] = []
    total_runs = len(rows) * TRIALS
    run_number = 0

    for truth in rows:
        scenario = truth["scenario"]
        sample_id = truth["sample_id"]
        target_present = truth["target_present"].lower() == "true"
        expected_offset = int(truth["expected_offset"])
        expected_hash = truth["original_sha256"]
        image = IMAGE_DIR / truth["image_filename"]

        for trial in range(1, TRIALS + 1):
            run_number += 1
            output_dir = RESULTS_DIR / scenario / sample_id / f"trial_{trial:02d}"
            command = [sys.executable, "-m", "pdrs.cli", str(image), str(output_dir)]
            started = time.perf_counter()
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            elapsed = time.perf_counter() - started
            if completed.returncode != 0:
                raise RuntimeError(
                    f"Scan failed ({run_number}/{total_runs}): {scenario}/{sample_id}, trial {trial}\n"
                    f"{completed.stdout}\n{completed.stderr}"
                )

            candidates = _read_manifest(output_dir / "manifest.csv")
            true_candidates = 0 if not target_present else sum(
                int(candidate["offset"]) == expected_offset for candidate in candidates
            )
            exact_matches = 0 if not target_present else sum(
                candidate["sha256"] == expected_hash for candidate in candidates
            )
            false_positives = len(candidates) if not target_present else len(candidates) - true_candidates
            run_rows.append({
                "scenario": scenario,
                "sample_id": sample_id,
                "trial": trial,
                "candidate_count": len(candidates),
                "true_header_candidates": true_candidates,
                "false_positive_candidates": false_positives,
                "exact_sha256_matches": exact_matches,
                "boundary_marked_complete": sum(
                    candidate["complete_boundary"].lower() == "true" for candidate in candidates
                ),
                "runtime_seconds": f"{elapsed:.6f}",
            })
            if run_number % 10 == 0 or run_number == total_runs:
                print(f"Completed {run_number}/{total_runs} scans")

    run_fields = list(run_rows[0])
    with (RESULTS_DIR / "run_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=run_fields)
        writer.writeheader()
        writer.writerows(run_rows)

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in run_rows:
        grouped[str(row["scenario"])].append(row)

    summary_rows: list[dict[str, object]] = []
    truth_by_scenario: dict[str, list[dict[str, str]]] = defaultdict(list)
    for truth in rows:
        truth_by_scenario[truth["scenario"]].append(truth)

    for scenario, group in sorted(grouped.items()):
        candidates = sum(int(row["candidate_count"]) for row in group)
        true_candidates = sum(int(row["true_header_candidates"]) for row in group)
        false_positives = sum(int(row["false_positive_candidates"]) for row in group)
        exact_matches = sum(int(row["exact_sha256_matches"]) for row in group)
        target_trials = sum(
            truth["target_present"].lower() == "true" for truth in truth_by_scenario[scenario]
        ) * TRIALS
        times = [float(row["runtime_seconds"]) for row in group]
        summary_rows.append({
            "scenario": scenario,
            "independent_samples": len(truth_by_scenario[scenario]),
            "trials_per_sample": TRIALS,
            "total_candidates": candidates,
            "true_header_candidates": true_candidates,
            "false_positive_candidates": false_positives,
            "candidate_precision": "N/A" if candidates == 0 else f"{true_candidates / candidates:.4f}",
            "header_detection_recall": "N/A" if target_trials == 0 else f"{true_candidates / target_trials:.4f}",
            "exact_recovery_rate": "N/A" if target_trials == 0 else f"{exact_matches / target_trials:.4f}",
            "exact_sha256_matches": exact_matches,
            "mean_runtime_seconds": f"{statistics.mean(times):.6f}",
            "median_runtime_seconds": f"{statistics.median(times):.6f}",
            "min_runtime_seconds": f"{min(times):.6f}",
            "max_runtime_seconds": f"{max(times):.6f}",
        })

    summary_fields = list(summary_rows[0])
    with (RESULTS_DIR / "scenario_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"Run details:     {RESULTS_DIR / 'run_details.csv'}")
    print(f"Scenario summary:{RESULTS_DIR / 'scenario_summary.csv'}")
    print("Timing is end-to-end CLI process time; each scenario uses 10 independent PNGs, 5 trials per image.")


if __name__ == "__main__":
    main()
