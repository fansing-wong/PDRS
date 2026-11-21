"""Run one v0.21 active-reuse or invalid-chain synthetic scenario."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent
PROJECT_ROOT = EXAMPLES.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pdrs.evaluation import evaluate_ground_truth, load_ground_truth, write_evaluation
from pdrs.fat32_recovery import recover_deleted_fat32
from pdrs.manifest import write_manifest
from prepare_deleted_directory_scenarios_v21 import SCENARIOS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-dir", type=Path, required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--results-dir", type=Path)
    args = parser.parse_args()
    demo = args.demo_dir.expanduser().resolve()
    image = demo / "images" / "fat32_deleted_root.img"
    truth_path = demo / "ground_truth.csv"
    results = (args.results_dir or demo / f"results_{args.scenario}_v21").expanduser().resolve()
    if not image.is_file() or not truth_path.is_file():
        raise SystemExit("Synthetic image or Ground Truth is missing; run the v21 fixture preparer first.")
    if results.exists():
        raise SystemExit(f"Refusing to overwrite existing scenario results: {results}")

    records = load_ground_truth(truth_path, image.name)
    results.mkdir(parents=True)
    result = recover_deleted_fat32(
        image,
        results,
        reassemble_fragmented=True,
        scan_deleted_directories=True,
    )
    manifest = write_manifest(results, result.rows)
    evaluation = evaluate_ground_truth(records, result.rows)
    comparison, summary = write_evaluation(results, evaluation)

    details_path = results / "deleted_directory_details.csv"
    detail_fields = (
        "filename",
        "parent_deleted_directory",
        "parent_directory_cluster",
        "directory_cluster",
        "directory_entry_offset",
        "original_long_filename",
        "long_filename_status",
        "sha256",
    )
    with details_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=detail_fields)
        writer.writeheader()
        for row in result.rows:
            if row["parent_deleted_directory"]:
                writer.writerow({key: row.get(key, "") for key in detail_fields})

    status_counts: dict[str, int] = {}
    for detail in evaluation.details:
        status = str(detail["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    overlap_warnings = sum(
        "overlaps active or already scanned cluster" in warning
        for warning in result.warnings
    )
    invalid_chain_warnings = sum(
        "directory chain contains" in warning
        for warning in result.warnings
    )
    metrics = {
        "scenario": args.scenario,
        "directories_scanned": result.directories_scanned,
        "deleted_directory_candidates": sum(bool(row["parent_deleted_directory"]) for row in result.rows),
        "overlap_warnings": overlap_warnings,
        "invalid_chain_warnings": invalid_chain_warnings,
        "correctly_absent_ground_truth_count": status_counts.get("correctly_absent", 0),
        "unexpected_recovery_count": status_counts.get("unexpected_recovery", 0),
        "false_positive_candidate_count": evaluation.summary["false_positive_candidate_count"],
    }
    metrics_path = results / "scenario_metrics.csv"
    with metrics_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("metric", "value"))
        writer.writerows(metrics.items())
    if result.warnings:
        (results / "recovery_warnings.txt").write_text(
            "\n".join(result.warnings) + "\n", encoding="utf-8"
        )

    print(f"Scenario: {args.scenario}")
    print(f"Directories scanned: {result.directories_scanned}")
    print(f"Recovered candidates: {len(result.rows)}")
    print(
        "Ground Truth exact: "
        f"{evaluation.summary['recovered_exact_count']}/{evaluation.summary['expected_present_count']}"
    )
    print(f"Deleted-directory candidates: {metrics['deleted_directory_candidates']}")
    print(f"Overlap warnings: {overlap_warnings}; invalid-chain warnings: {invalid_chain_warnings}")
    print(f"False-positive candidates: {evaluation.summary['false_positive_candidate_count']}")
    print(f"Manifest: {manifest}")
    print(f"Comparison: {comparison}")
    print(f"Summary: {summary}")
    print(f"Scenario metrics: {metrics_path}")
    for warning in result.warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
