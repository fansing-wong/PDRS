"""Run multiple-reuse, cyclic-chain, and bad-cluster controls at three sizes."""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent
GENERATOR = EXAMPLES / "make_fat32_fragmented_demo_v17.py"
PREPARER = EXAMPLES / "prepare_deleted_directory_scenarios_v21.py"
RUNNER = EXAMPLES / "run_deleted_directory_scenario_v21.py"
DEFAULT_ROOT = EXAMPLES / "fat32_deleted_directory_matrix_v21"
SCENARIOS = ("multiple_reuse", "cyclic_chain", "bad_cluster_link")
SECTORS_PER_CLUSTER = (1, 2, 4)


def _csv_dict(path: Path) -> dict[str, str]:
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
        for scenario in SCENARIOS:
            demo = root / f"spc_{sectors_per_cluster}_{scenario}"
            results = demo / f"results_{scenario}_v21"
            subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    "--output-dir",
                    str(demo),
                    "--sectors-per-cluster",
                    str(sectors_per_cluster),
                ],
                check=True,
            )
            subprocess.run(
                [sys.executable, str(PREPARER), "--demo-dir", str(demo), "--scenario", scenario],
                check=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--demo-dir",
                    str(demo),
                    "--scenario",
                    scenario,
                    "--results-dir",
                    str(results),
                ],
                check=True,
            )
            evaluation = _csv_dict(results / "evaluation_summary.csv")
            metrics = _csv_dict(results / "scenario_metrics.csv")
            rows.append({
                "scenario": scenario,
                "sectors_per_cluster": sectors_per_cluster,
                "cluster_size_bytes": sectors_per_cluster * 512,
                "expected_present_count": evaluation["expected_present_count"],
                "recovered_exact_count": evaluation["recovered_exact_count"],
                "expected_absent_count": evaluation["expected_absent_count"],
                "false_positive_candidate_count": evaluation["false_positive_candidate_count"],
                "candidate_precision": evaluation["candidate_precision"],
                "recovery_recall": evaluation["recovery_recall"],
                "offset_match_rate": evaluation["offset_match_rate"],
                "directories_scanned": metrics["directories_scanned"],
                "deleted_directory_candidates": metrics["deleted_directory_candidates"],
                "overlap_warnings": metrics["overlap_warnings"],
                "invalid_chain_warnings": metrics["invalid_chain_warnings"],
                "correctly_absent_ground_truth_count": metrics["correctly_absent_ground_truth_count"],
                "unexpected_recovery_count": metrics["unexpected_recovery_count"],
            })

    summary_path = root / "matrix_summary.csv"
    fields = tuple(rows[0]) if rows else ()
    with summary_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Deleted-directory matrix summary: {summary_path}")


if __name__ == "__main__":
    main()
