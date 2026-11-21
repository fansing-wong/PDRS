"""Run multi-cluster, deleted-LFN, and FAT32 cluster-reuse controls."""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path


EXAMPLES = Path(__file__).resolve().parent
GENERATOR = EXAMPLES / "make_fat32_fragmented_demo_v17.py"
PREPARER = EXAMPLES / "prepare_deleted_directory_scenarios_v19.py"
RUNNER = EXAMPLES / "run_deleted_directory_scenario_v19.py"
DEFAULT_ROOT = EXAMPLES / "fat32_deleted_directory_matrix_v19"
SECTOR_SIZE = 512
SECTORS_PER_CLUSTER = (1, 2, 4)
SCENARIOS = ("multi_cluster", "cluster_reuse")


def _metrics(path: Path) -> dict[str, str]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return {row["metric"]: row["value"] for row in csv.DictReader(handle)}


def _manifest_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ROOT)
    root = parser.parse_args().output_dir.expanduser().resolve()
    if root.exists():
        raise SystemExit(f"Refusing to overwrite existing matrix results: {root}")
    root.mkdir(parents=True)

    rows: list[dict[str, str | int]] = []
    for sectors_per_cluster in SECTORS_PER_CLUSTER:
        for scenario in SCENARIOS:
            demo_dir = root / f"spc_{sectors_per_cluster}_{scenario}"
            results_dir = demo_dir / f"results_{scenario}_v19"
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
                    str(PREPARER),
                    "--demo-dir",
                    str(demo_dir),
                    "--scenario",
                    scenario,
                ],
                check=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--demo-dir",
                    str(demo_dir),
                    "--scenario",
                    scenario,
                    "--results-dir",
                    str(results_dir),
                ],
                check=True,
            )
            summary = _metrics(results_dir / "evaluation_summary.csv")
            manifest_rows = _manifest_rows(results_dir / "manifest.csv")
            deleted_rows = [
                row for row in manifest_rows if row.get("parent_deleted_directory") == "True"
            ]
            lfn_rows = [
                row for row in deleted_rows if row.get("original_long_filename")
            ]
            warnings_path = results_dir / "recovery_warnings.txt"
            warning_lines = warnings_path.read_text(encoding="utf-8").splitlines() if warnings_path.exists() else []
            overlap_skips = sum(
                "overlaps active or already scanned cluster" in warning
                for warning in warning_lines
            )
            rows.append({
                "scenario": scenario,
                "sectors_per_cluster": sectors_per_cluster,
                "cluster_size_bytes": sectors_per_cluster * SECTOR_SIZE,
                "expected_present_count": summary["expected_present_count"],
                "recovered_exact_count": summary["recovered_exact_count"],
                "expected_absent_count": summary["expected_absent_count"],
                "false_positive_candidate_count": summary["false_positive_candidate_count"],
                "candidate_precision": summary["candidate_precision"],
                "recovery_recall": summary["recovery_recall"],
                "offset_match_rate": summary["offset_match_rate"],
                "deleted_directory_candidates": len(deleted_rows),
                "reconstructed_long_name_candidates": len(lfn_rows),
                "deleted_directory_overlap_skips": overlap_skips,
            })

    summary_path = root / "matrix_summary.csv"
    fields = (
        "scenario",
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
        "reconstructed_long_name_candidates",
        "deleted_directory_overlap_skips",
    )
    with summary_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Deleted-directory matrix summary: {summary_path}")


if __name__ == "__main__":
    main()
