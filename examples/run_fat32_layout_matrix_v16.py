"""Run the synthetic FAT32 recovery matrix at three cluster sizes."""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path


EXAMPLES = Path(__file__).resolve().parent
GENERATOR = EXAMPLES / "make_fat32_deleted_demo.py"
RUNNER = EXAMPLES / "run_fat32_deleted_demo.py"
DEFAULT_ROOT = EXAMPLES / "fat32_layout_matrix_v16"
SECTORS_PER_CLUSTER = (1, 2, 4)
SECTOR_SIZE = 512


def _read_metric_summary(path: Path) -> dict[str, str]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return {row["metric"]: row["value"] for row in csv.DictReader(handle)}


def _read_layout_counts(path: Path) -> dict[str, int]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return {
            row["data_layout_status"]: int(row["candidate_count"])
            for row in csv.DictReader(handle)
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ROOT)
    root = parser.parse_args().output_dir.expanduser().resolve()
    if root.exists():
        raise SystemExit(f"Refusing to overwrite existing matrix results: {root}")
    root.mkdir(parents=True)

    rows: list[dict[str, str | int]] = []
    for sectors_per_cluster in SECTORS_PER_CLUSTER:
        demo_dir = root / f"spc_{sectors_per_cluster}"
        subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                "--output-dir",
                str(demo_dir),
                "--sectors-per-cluster",
                str(sectors_per_cluster),
            ],
            check=True,
        )
        subprocess.run(
            [sys.executable, str(RUNNER), "--demo-dir", str(demo_dir)],
            check=True,
        )

        metrics = _read_metric_summary(demo_dir / "results" / "evaluation_summary.csv")
        layout_counts = _read_layout_counts(demo_dir / "results" / "data_layout_summary.csv")
        rows.append({
            "sectors_per_cluster": sectors_per_cluster,
            "cluster_size_bytes": sectors_per_cluster * SECTOR_SIZE,
            "image_size_bytes": (demo_dir / "images" / "fat32_deleted_root.img").stat().st_size,
            "expected_present_count": metrics["expected_present_count"],
            "recovered_exact_count": metrics["recovered_exact_count"],
            "expected_absent_count": metrics["expected_absent_count"],
            "false_positive_candidate_count": metrics["false_positive_candidate_count"],
            "candidate_precision": metrics["candidate_precision"],
            "recovery_recall": metrics["recovery_recall"],
            "offset_match_rate": metrics["offset_match_rate"],
            "layout_counts": ";".join(
                f"{name}={count}" for name, count in sorted(layout_counts.items())
            ),
        })

    summary_path = root / "matrix_summary.csv"
    fields = (
        "sectors_per_cluster",
        "cluster_size_bytes",
        "image_size_bytes",
        "expected_present_count",
        "recovered_exact_count",
        "expected_absent_count",
        "false_positive_candidate_count",
        "candidate_precision",
        "recovery_recall",
        "offset_match_rate",
        "layout_counts",
    )
    with summary_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Cluster-size matrix summary: {summary_path}")


if __name__ == "__main__":
    main()
