"""Run one opt-in v0.19 synthetic deleted-directory scenario."""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pdrs.evaluation import evaluate_ground_truth, load_ground_truth, write_evaluation
from pdrs.fat32_recovery import recover_deleted_fat32
from pdrs.manifest import write_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-dir", type=Path, required=True)
    parser.add_argument("--scenario", choices=("multi_cluster", "cluster_reuse"), required=True)
    parser.add_argument("--results-dir", type=Path)
    args = parser.parse_args()
    demo_dir = args.demo_dir.expanduser().resolve()
    image = demo_dir / "images" / "fat32_deleted_root.img"
    truth_path = demo_dir / "ground_truth.csv"
    default_results = demo_dir / f"results_{args.scenario}_v19"
    results = (args.results_dir or default_results).expanduser().resolve()
    if not image.is_file() or not truth_path.is_file():
        raise SystemExit("Synthetic image or Ground Truth is missing; run the v19 fixture preparer first.")
    if results.exists():
        raise SystemExit(f"Refusing to overwrite existing scenario results: {results}")

    records = load_ground_truth(truth_path, image.name)
    if args.scenario == "multi_cluster":
        records = [
            replace(record, target_present=True)
            if record.source_filename == "deleted_directory_control.txt"
            else record
            for record in records
        ]
        expected_name = "deleted_directory_long_name.txt"
    else:
        expected_name = "cluster_reuse_active_control.bin"
    if not any(record.source_filename == expected_name for record in records):
        raise SystemExit(f"Ground Truth does not contain the {args.scenario} scenario record.")

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
    with details_path.open("x", newline="", encoding="utf-8") as handle:
        fields = (
            "filename",
            "parent_deleted_directory",
            "parent_directory_cluster",
            "directory_cluster",
            "directory_entry_offset",
            "original_long_filename",
            "long_filename_status",
            "sha256",
        )
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in result.rows:
            if row["parent_deleted_directory"]:
                writer.writerow({key: row.get(key, "") for key in fields})
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
    print(f"False-positive candidates: {evaluation.summary['false_positive_candidate_count']}")
    print(f"Manifest: {manifest}")
    print(f"Comparison: {comparison}")
    print(f"Summary: {summary}")
    print(f"Deleted-directory details: {details_path}")
    for warning in result.warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
