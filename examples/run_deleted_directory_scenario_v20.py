"""Run one v0.20 partial-chain or overwritten-LFN synthetic scenario."""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import replace
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent
PROJECT_ROOT = EXAMPLES.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(EXAMPLES))

from pdrs.evaluation import evaluate_ground_truth, load_ground_truth, write_evaluation
from pdrs.fat32_recovery import recover_deleted_fat32
from pdrs.manifest import write_manifest
from prepare_deleted_directory_scenarios_v20 import LONG_NAME, SCENARIOS


TARGET_SOURCE = "deleted_directory_control.txt"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-dir", type=Path, required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--results-dir", type=Path)
    args = parser.parse_args()
    demo_dir = args.demo_dir.expanduser().resolve()
    image = demo_dir / "images" / "fat32_deleted_root.img"
    truth_path = demo_dir / "ground_truth.csv"
    results = (args.results_dir or demo_dir / f"results_{args.scenario}_v20").expanduser().resolve()
    if not image.is_file() or not truth_path.is_file():
        raise SystemExit("Synthetic image or Ground Truth is missing; run the v20 fixture preparer first.")
    if results.exists():
        raise SystemExit(f"Refusing to overwrite existing scenario results: {results}")

    records = load_ground_truth(truth_path, image.name)
    target_record = next((record for record in records if record.source_filename == TARGET_SOURCE), None)
    if target_record is None:
        raise SystemExit("Ground Truth does not contain the deleted-directory target control.")
    expected_present = args.scenario == "lfn_slot_overwritten"
    records = [
        replace(record, target_present=expected_present)
        if record.source_filename == TARGET_SOURCE
        else record
        for record in records
    ]

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

    target_detail = next(
        detail for detail in evaluation.details if detail["source_filename"] == TARGET_SOURCE
    )
    target_candidate = next(
        (
            row
            for row in result.rows
            if row["filename"] == target_detail["recovered_filename"]
        ),
        None,
    )
    recovered_long_name = str(target_candidate.get("original_long_filename") or "") if target_candidate else ""
    metrics = {
        "scenario": args.scenario,
        "directories_scanned": result.directories_scanned,
        "deleted_directory_candidates": sum(bool(row["parent_deleted_directory"]) for row in result.rows),
        "target_expected_present": str(expected_present).lower(),
        "target_exact": str(target_detail["status"] == "exact").lower(),
        "expected_long_filename": LONG_NAME if expected_present else "",
        "recovered_long_filename": recovered_long_name,
        "long_filename_exact": str(recovered_long_name == LONG_NAME).lower() if expected_present else "",
        "incomplete_chain_warnings": sum(
            "directory chain contains a free, bad, or reserved cluster" in warning
            for warning in result.warnings
        ),
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
    print(f"Target data exact: {metrics['target_exact']}")
    if expected_present:
        print(f"Expected long name: {LONG_NAME}")
        print(f"Recovered long name: {recovered_long_name or '(none)'}")
    print(f"False-positive candidates: {evaluation.summary['false_positive_candidate_count']}")
    print(f"Manifest: {manifest}")
    print(f"Comparison: {comparison}")
    print(f"Summary: {summary}")
    print(f"Scenario metrics: {metrics_path}")
    for warning in result.warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
