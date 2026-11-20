"""Run each synthetic scenario five times and write timing/accuracy summaries."""

from __future__ import annotations

import csv
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE / "experiment_set"
IMAGE_DIR = ROOT / "images"
RESULTS_DIR = ROOT / "results_repeated_5"
GROUND_TRUTH = ROOT / "ground_truth.csv"
TRIALS = 5
SCENARIOS = ("baseline", "truncated", "decoy_signature", "fragmented")


def read_ground_truth() -> dict[str, dict[str, str]]:
    with GROUND_TRUTH.open(newline="", encoding="utf-8") as handle:
        return {row["scenario"]: row for row in csv.DictReader(handle)}


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    if not GROUND_TRUTH.is_file():
        raise SystemExit("Experiment set not found. Run make_experiment_set.py first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")

    ground_truth = read_ground_truth()
    RESULTS_DIR.mkdir(parents=True)
    summary_rows: list[dict[str, object]] = []

    for scenario in SCENARIOS:
        truth = ground_truth[scenario]
        image = IMAGE_DIR / f"{scenario}.img"
        expected_offset = int(truth["expected_offset"])
        is_decoy = truth["format"] == "none"
        expected_hash = truth["original_sha256"]

        for trial in range(1, TRIALS + 1):
            output_dir = RESULTS_DIR / scenario / f"trial_{trial:02d}"
            command = [sys.executable, "-m", "pdrs.cli", str(image), str(output_dir)]
            started = time.perf_counter()
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            elapsed = time.perf_counter() - started
            if completed.returncode != 0:
                raise RuntimeError(
                    f"Scan failed for {scenario}, trial {trial}:\n{completed.stdout}\n{completed.stderr}"
                )

            manifest = read_manifest(output_dir / "manifest.csv")
            true_candidates = 0 if is_decoy else sum(
                int(row["offset"]) == expected_offset for row in manifest
            )
            exact_hash_matches = 0 if is_decoy else sum(
                row["sha256"] == expected_hash for row in manifest
            )
            false_positives = len(manifest) if is_decoy else len(manifest) - true_candidates
            summary_rows.append({
                "scenario": scenario,
                "trial": trial,
                "candidate_count": len(manifest),
                "true_header_candidates": true_candidates,
                "false_positive_candidates": false_positives,
                "exact_sha256_matches": exact_hash_matches,
                "boundary_marked_complete": sum(row["complete_boundary"].lower() == "true" for row in manifest),
                "runtime_seconds": f"{elapsed:.6f}",
            })
            print(f"{scenario}: trial {trial}/{TRIALS} complete ({elapsed:.4f}s)")

    summary_path = RESULTS_DIR / "benchmark_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"Summary: {summary_path}")
    print("Timing is end-to-end CLI process time, including Python startup and manifest writing.")


if __name__ == "__main__":
    main()
