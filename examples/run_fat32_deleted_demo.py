"""Run and evaluate the synthetic FAT32 deleted-entry demonstration."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pdrs.evaluation import evaluate_ground_truth, load_ground_truth, write_evaluation
from pdrs.fat32_recovery import recover_deleted_fat32
from pdrs.manifest import write_manifest

DEFAULT_ROOT = Path(__file__).resolve().parent / "fat32_deleted_demo"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-dir", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--results-dir", type=Path)
    args = parser.parse_args()
    root = args.demo_dir.expanduser().resolve()
    image = root / "images" / "fat32_deleted_root.img"
    truth = root / "ground_truth.csv"
    results = (args.results_dir or root / "results").expanduser().resolve()

    if not image.is_file() or not truth.is_file():
        raise SystemExit("Demo is missing; run make_fat32_deleted_demo.py first.")
    if results.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {results}")
    results.mkdir(parents=True)
    result = recover_deleted_fat32(image, results)
    manifest = write_manifest(results, result.rows)
    evaluation = evaluate_ground_truth(load_ground_truth(truth, image.name), result.rows)
    comparison, summary = write_evaluation(results, evaluation)
    recovered_by_name = {str(row["filename"]): row for row in result.rows}
    name_comparison_path = results / "lfn_name_comparison.csv"
    name_matches = 0
    with name_comparison_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "expected_long_filename",
                "recovered_filename",
                "recovered_long_filename",
                "name_match",
            ),
        )
        writer.writeheader()
        for detail in evaluation.details:
            recovered = recovered_by_name.get(str(detail["recovered_filename"]))
            expected_name = Path(str(detail["source_filename"])).name
            recovered_name = str(recovered["original_long_filename"]) if recovered else ""
            name_match = recovered_name.casefold() == expected_name.casefold()
            name_matches += int(name_match)
            writer.writerow({
                "expected_long_filename": expected_name,
                "recovered_filename": str(detail["recovered_filename"]),
                "recovered_long_filename": recovered_name,
                "name_match": name_match,
            })
    if result.warnings:
        (results / "recovery_warnings.txt").write_text(
            "\n".join(result.warnings) + "\n", encoding="utf-8"
        )
    print(f"Deleted short entries examined: {result.deleted_entries_seen}")
    print(f"Directories scanned:            {result.directories_scanned}")
    print(f"Recovered candidates: {len(result.rows)}")
    print(f"LFN exact name matches: {name_matches}/{len(evaluation.details)}")
    for row in result.rows:
        name = row["original_long_filename"] or row["filename"]
        print(f"Recovered name:      {name}")
    print(
        "Exact Ground Truth:  "
        f"{evaluation.summary['recovered_exact_count']}/{evaluation.summary['expected_present_count']}"
    )
    print(f"Candidate precision: {evaluation.summary['candidate_precision']}")
    print(f"False-positive candidates: {evaluation.summary['false_positive_candidate_count']}")
    print(f"Manifest:            {manifest}")
    print(f"Comparison:          {comparison}")
    print(f"Summary:             {summary}")
    print(f"Name comparison:     {name_comparison_path}")
    for warning in result.warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
