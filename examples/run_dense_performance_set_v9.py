"""Benchmark end-to-end scans of independent, fully written raw images."""

from __future__ import annotations

import csv
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "experiment_set_v9"
IMAGE_DIR = ROOT / "images"
RESULTS_DIR = ROOT / "results_dense_performance_5"
TRIALS_PER_IMAGE = 5


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    truth_path = ROOT / "ground_truth.csv"
    if not truth_path.is_file():
        raise SystemExit("Dataset not found. Run make_dense_performance_set_v9.py first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True)

    truth_by_image: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _read_csv(truth_path):
        truth_by_image[row["image_filename"]].append(row)

    image_names = sorted(
        truth_by_image,
        key=lambda name: (
            int(truth_by_image[name][0]["image_size_mib"]),
            int(truth_by_image[name][0]["sample_index"]),
        ),
    )
    run_rows: list[dict[str, object]] = []
    total_runs = len(image_names) * TRIALS_PER_IMAGE
    run_number = 0

    for image_name in image_names:
        truth_rows = truth_by_image[image_name]
        image_size_bytes = int(truth_rows[0]["image_size_bytes"])
        image_size_mib = int(truth_rows[0]["image_size_mib"])
        image_path = IMAGE_DIR / image_name
        expected_offsets = {int(row["expected_offset"]) for row in truth_rows}

        for trial in range(1, TRIALS_PER_IMAGE + 1):
            run_number += 1
            output_dir = RESULTS_DIR / image_name.removesuffix(".img") / f"trial_{trial:02d}"
            started = time.perf_counter()
            result = subprocess.run(
                [sys.executable, "-m", "pdrs.cli", str(image_path), str(output_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            elapsed = time.perf_counter() - started
            if result.returncode != 0:
                raise RuntimeError(f"Scan failed for {image_name}, trial {trial}:\n{result.stderr}")

            manifest = _read_csv(output_dir / "manifest.csv")
            expected_detections = 0
            exact_matches = 0
            for truth in truth_rows:
                expected_offset = int(truth["expected_offset"])
                candidate = next((
                    row for row in manifest
                    if int(row["offset"]) == expected_offset and row["format"] == truth["format"]
                ), None)
                if candidate is not None:
                    expected_detections += 1
                    if candidate["sha256"] == truth["source_sha256"]:
                        exact_matches += 1

            unexpected_candidates = sum(
                1 for row in manifest if int(row["offset"]) not in expected_offsets
            )
            throughput = image_size_bytes / (1024 * 1024) / elapsed
            run_rows.append({
                "image_size_mib": image_size_mib,
                "image_filename": image_name,
                "sample_index": int(truth_rows[0]["sample_index"]),
                "trial": trial,
                "runtime_seconds": f"{elapsed:.6f}",
                "end_to_end_mib_per_second": f"{throughput:.6f}",
                "candidate_count": len(manifest),
                "unexpected_candidates": unexpected_candidates,
                "expected_file_detections": expected_detections,
                "exact_hash_matches": exact_matches,
            })
            print(
                f"Completed {run_number}/{total_runs}: {image_name}, "
                f"trial {trial}/{TRIALS_PER_IMAGE} ({elapsed:.3f}s)"
            )

    with (RESULTS_DIR / "run_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(run_rows[0]))
        writer.writeheader()
        writer.writerows(run_rows)

    summaries: list[dict[str, object]] = []
    for size_mib in sorted({int(row["image_size_mib"]) for row in run_rows}):
        rows = [row for row in run_rows if int(row["image_size_mib"]) == size_mib]
        times = [float(row["runtime_seconds"]) for row in rows]
        rates = [float(row["end_to_end_mib_per_second"]) for row in rows]
        summaries.append({
            "image_size_mib": size_mib,
            "independent_images": len({row["image_filename"] for row in rows}),
            "trials_per_image": TRIALS_PER_IMAGE,
            "total_scans": len(rows),
            "mean_runtime_seconds": f"{statistics.mean(times):.6f}",
            "median_runtime_seconds": f"{statistics.median(times):.6f}",
            "min_runtime_seconds": f"{min(times):.6f}",
            "max_runtime_seconds": f"{max(times):.6f}",
            "mean_end_to_end_mib_per_second": f"{statistics.mean(rates):.6f}",
            "mean_candidate_count": f"{statistics.mean(int(row['candidate_count']) for row in rows):.3f}",
            "unexpected_candidates": sum(int(row["unexpected_candidates"]) for row in rows),
            "expected_file_detections": sum(int(row["expected_file_detections"]) for row in rows),
            "expected_file_checks": len(rows) * len(truth_by_image[rows[0]["image_filename"]]),
            "exact_hash_matches": sum(int(row["exact_hash_matches"]) for row in rows),
            "exact_hash_checks": len(rows) * len(truth_by_image[rows[0]["image_filename"]]),
        })

    with (RESULTS_DIR / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    print(f"Run details: {RESULTS_DIR / 'run_details.csv'}")
    print(f"Summary:     {RESULTS_DIR / 'summary.csv'}")
    print("Timing is end-to-end CLI time; repeated scans may benefit from the operating-system file cache.")


if __name__ == "__main__":
    main()
