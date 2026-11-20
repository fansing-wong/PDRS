"""Compare CLI end-to-end time with in-process carving on the V9 images."""

from __future__ import annotations

import csv
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from pdrs.carve import carve_image


ROOT = Path(__file__).resolve().parent / "experiment_set_v9"
IMAGE_DIR = ROOT / "images"
RESULTS_DIR = Path(__file__).resolve().parent / "experiment_set_v10" / "results_paired_timing_5"
TRIALS_PER_IMAGE = 5


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _score(rows: list[dict[str, object]], truth_rows: list[dict[str, str]]) -> tuple[int, int, int]:
    expected_offsets = {int(row["expected_offset"]) for row in truth_rows}
    expected_detections = 0
    exact_matches = 0
    for truth in truth_rows:
        candidate = next((
            row for row in rows
            if int(row["offset"]) == int(truth["expected_offset"])
            and row["format"] == truth["format"]
        ), None)
        if candidate is not None:
            expected_detections += 1
            if candidate["sha256"] == truth["source_sha256"]:
                exact_matches += 1
    unexpected = sum(1 for row in rows if int(row["offset"]) not in expected_offsets)
    return expected_detections, exact_matches, unexpected


def _normalize(rows: list[dict[str, object]]) -> list[tuple[int, str, str, str]]:
    return sorted(
        (
            int(row["offset"]),
            str(row["format"]),
            str(row["sha256"]),
            str(row.get("format_valid")),
        )
        for row in rows
    )


def main() -> None:
    truth_path = ROOT / "ground_truth.csv"
    if not truth_path.is_file():
        raise SystemExit("V9 dataset not found. Run make_dense_performance_set_v9.py first.")
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

    paired_rows: list[dict[str, object]] = []
    total_pairs = len(image_names) * TRIALS_PER_IMAGE
    pair_number = 0
    for image_name in image_names:
        truth_rows = truth_by_image[image_name]
        image_path = IMAGE_DIR / image_name
        image_size_mib = int(truth_rows[0]["image_size_mib"])
        sample_index = int(truth_rows[0]["sample_index"])

        for trial in range(1, TRIALS_PER_IMAGE + 1):
            pair_number += 1
            # Alternate which method runs first to balance warm-cache order.
            first_method = "inprocess" if (sample_index + trial) % 2 == 0 else "cli"
            methods = (first_method, "cli" if first_method == "inprocess" else "inprocess")
            measurements: dict[str, dict[str, object]] = {}

            for method in methods:
                output_dir = (
                    RESULTS_DIR / method / image_path.stem / f"trial_{trial:02d}"
                )
                if method == "cli":
                    started = time.perf_counter()
                    result = subprocess.run(
                        [sys.executable, "-m", "pdrs.cli", str(image_path), str(output_dir)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    elapsed = time.perf_counter() - started
                    if result.returncode != 0:
                        raise RuntimeError(
                            f"CLI scan failed for {image_name}, trial {trial}:\n{result.stderr}"
                        )
                    rows: list[dict[str, object]] = [
                        row for row in _read_csv(output_dir / "manifest.csv")
                    ]
                else:
                    started = time.perf_counter()
                    rows = carve_image(image_path, output_dir)
                    elapsed = time.perf_counter() - started

                detected, exact, unexpected = _score(rows, truth_rows)
                measurements[method] = {
                    "runtime": elapsed,
                    "rows": rows,
                    "detected": detected,
                    "exact": exact,
                    "unexpected": unexpected,
                }

            cli = measurements["cli"]
            inprocess = measurements["inprocess"]
            cli_runtime = float(cli["runtime"])
            inprocess_runtime = float(inprocess["runtime"])
            paired_rows.append({
                "image_size_mib": image_size_mib,
                "image_filename": image_name,
                "sample_index": sample_index,
                "trial": trial,
                "first_method": first_method,
                "cli_runtime_seconds": f"{cli_runtime:.6f}",
                "inprocess_runtime_seconds": f"{inprocess_runtime:.6f}",
                "cli_minus_inprocess_seconds": f"{cli_runtime - inprocess_runtime:.6f}",
                "cli_over_inprocess_ratio": f"{cli_runtime / inprocess_runtime:.6f}",
                "cli_candidate_count": len(cli["rows"]),
                "inprocess_candidate_count": len(inprocess["rows"]),
                "cli_unexpected_candidates": cli["unexpected"],
                "inprocess_unexpected_candidates": inprocess["unexpected"],
                "cli_expected_detections": cli["detected"],
                "inprocess_expected_detections": inprocess["detected"],
                "cli_exact_hash_matches": cli["exact"],
                "inprocess_exact_hash_matches": inprocess["exact"],
                "candidate_outputs_equal": _normalize(cli["rows"]) == _normalize(inprocess["rows"]),
            })
            print(f"Completed {pair_number}/{total_pairs}: {image_name}, trial {trial}/{TRIALS_PER_IMAGE}")

    with (RESULTS_DIR / "paired_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(paired_rows[0]))
        writer.writeheader()
        writer.writerows(paired_rows)

    summaries: list[dict[str, object]] = []
    for size_mib in sorted({int(row["image_size_mib"]) for row in paired_rows}):
        rows = [row for row in paired_rows if int(row["image_size_mib"]) == size_mib]
        cli_times = [float(row["cli_runtime_seconds"]) for row in rows]
        inprocess_times = [float(row["inprocess_runtime_seconds"]) for row in rows]
        deltas = [float(row["cli_minus_inprocess_seconds"]) for row in rows]
        ratios = [float(row["cli_over_inprocess_ratio"]) for row in rows]
        summaries.append({
            "image_size_mib": size_mib,
            "independent_images": len({row["image_filename"] for row in rows}),
            "paired_scans": len(rows),
            "mean_cli_runtime_seconds": f"{statistics.mean(cli_times):.6f}",
            "median_cli_runtime_seconds": f"{statistics.median(cli_times):.6f}",
            "mean_inprocess_runtime_seconds": f"{statistics.mean(inprocess_times):.6f}",
            "median_inprocess_runtime_seconds": f"{statistics.median(inprocess_times):.6f}",
            "mean_cli_minus_inprocess_seconds": f"{statistics.mean(deltas):.6f}",
            "median_cli_minus_inprocess_seconds": f"{statistics.median(deltas):.6f}",
            "mean_cli_over_inprocess_ratio": f"{statistics.mean(ratios):.6f}",
            "identical_candidate_outputs": sum(bool(row["candidate_outputs_equal"]) for row in rows),
            "paired_output_checks": len(rows),
        })

    with (RESULTS_DIR / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    print(f"Paired details: {RESULTS_DIR / 'paired_details.csv'}")
    print(f"Summary:        {RESULTS_DIR / 'summary.csv'}")
    print("In-process timing includes carving, validation, hashing, and candidate writes; it excludes CLI startup and manifest serialization.")


if __name__ == "__main__":
    main()
