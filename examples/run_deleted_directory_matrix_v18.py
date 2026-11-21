"""Run the deleted-directory FAT32 experiment at three cluster sizes."""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path


EXAMPLES = Path(__file__).resolve().parent
GENERATOR = EXAMPLES / "make_fat32_fragmented_demo_v17.py"
FIXTURE_PREPARER = EXAMPLES / "prepare_deleted_directory_fixture_v18.py"
RUNNER = EXAMPLES / "run_deleted_directory_recovery_v18.py"
DEFAULT_ROOT = EXAMPLES / "fat32_deleted_directory_matrix_v18"
SECTORS_PER_CLUSTER = (1, 2, 4)
SECTOR_SIZE = 512


def _metrics(path: Path) -> dict[str, str]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return {row["metric"]: row["value"] for row in csv.DictReader(handle)}


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
        results_dir = demo_dir / "results_deleted_directory_v18"
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
            [
                sys.executable,
                str(FIXTURE_PREPARER),
                "--demo-dir",
                str(demo_dir),
            ],
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--demo-dir",
                str(demo_dir),
                "--results-dir",
                str(results_dir),
            ],
            check=True,
        )
        summary = _metrics(results_dir / "evaluation_summary.csv")
        with (results_dir / "manifest.csv").open("r", newline="", encoding="utf-8") as handle:
            manifest_rows = list(csv.DictReader(handle))
        orphan_count = sum(row.get("parent_deleted_directory") == "True" for row in manifest_rows)
        rows.append({
            "sectors_per_cluster": sectors_per_cluster,
            "cluster_size_bytes": sectors_per_cluster * SECTOR_SIZE,
            "expected_present_count": summary["expected_present_count"],
            "recovered_exact_count": summary["recovered_exact_count"],
            "expected_absent_count": summary["expected_absent_count"],
            "false_positive_candidate_count": summary["false_positive_candidate_count"],
            "candidate_precision": summary["candidate_precision"],
            "recovery_recall": summary["recovery_recall"],
            "offset_match_rate": summary["offset_match_rate"],
            "deleted_directory_candidates": orphan_count,
        })

    summary_path = root / "matrix_summary.csv"
    fields = (
        "sectors_per_cluster",
        "cluster_size_bytes",
        "expected_present_count",
        "recovered_exact_count",
        "expected_absent_count",
        "false_positive_candidate_count",
        "candidate_precision",
        "recovery_recall",
        "offset_match_rate",
        "deleted_directory_candidates",
    )
    with summary_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Deleted-directory matrix summary: {summary_path}")


if __name__ == "__main__":
    main()
