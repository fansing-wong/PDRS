"""Benchmark end-to-end CLI scanning for 1, 16, and 64 MiB raw images."""

from __future__ import annotations

import csv
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "experiment_set_v8"
IMAGE_DIR = ROOT / "images"
RESULTS_DIR = ROOT / "results_performance_5"
TRIALS = 5


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    truth_path = ROOT / "ground_truth.csv"
    if not truth_path.is_file():
        raise SystemExit("Dataset not found. Run make_performance_set_v8.py first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True)

    truth_by_image: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _read_csv(truth_path):
        truth_by_image[row["image_filename"]].append(row)

    run_rows: list[dict[str, object]] = []
    image_names = sorted(truth_by_image, key=lambda name: int(truth_by_image[name][0]["image_size_mib"]))
    total = len(image_names) * TRIALS
    run_number = 0
    for image_name in image_names:
        truth_rows = truth_by_image[image_name]
        image_size_bytes = int(truth_rows[0]["image_size_bytes"])
        image_size_mib = int(truth_rows[0]["image_size_mib"])
        image_path = IMAGE_DIR / image_name
        for trial in range(1, TRIALS + 1):
            run_number += 1
            output_dir = RESULTS_DIR / f"{image_size_mib:03d}MiB" / f"trial_{trial:02d}"
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
            with (output_dir / "manifest.csv").open(newline="", encoding="utf-8") as handle:
                manifest = list(csv.DictReader(handle))

            exact_matches = 0
            detected_formats: set[str] = set()
            for truth in truth_rows:
                expected_offset = int(truth["expected_offset"])
                candidate = next((row for row in manifest if int(row["offset"]) == expected_offset), None)
                if candidate is not None:
                    detected_formats.add(truth["format"])
                    if candidate["sha256"] == truth["source_sha256"]:
                        exact_matches += 1
            throughput = image_size_bytes / (1024 * 1024) / elapsed
            run_rows.append({
                "image_size_mib": image_size_mib,
                "trial": trial,
                "runtime_seconds": f"{elapsed:.6f}",
                "end_to_end_mib_per_second": f"{throughput:.6f}",
                "candidate_count": len(manifest),
                "expected_format_detections": len(detected_formats),
                "exact_hash_matches": exact_matches,
            })
            print(f"Completed {run_number}/{total}: {image_name}, trial {trial}/{TRIALS} ({elapsed:.3f}s)")

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
            "trials": len(rows),
            "mean_runtime_seconds": f"{statistics.mean(times):.6f}",
            "median_runtime_seconds": f"{statistics.median(times):.6f}",
            "min_runtime_seconds": f"{min(times):.6f}",
            "max_runtime_seconds": f"{max(times):.6f}",
            "mean_end_to_end_mib_per_second": f"{statistics.mean(rates):.6f}",
            "candidates_per_run": rows[0]["candidate_count"],
            "exact_matches_per_run": rows[0]["exact_hash_matches"],
        })
    with (RESULTS_DIR / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    print(f"Run details: {RESULTS_DIR / 'run_details.csv'}")
    print(f"Summary:     {RESULTS_DIR / 'summary.csv'}")
    print("Throughput is end-to-end CLI throughput, including Python startup and validation.")


if __name__ == "__main__":
    main()
