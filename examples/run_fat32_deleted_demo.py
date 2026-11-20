"""Run and evaluate the synthetic FAT32 deleted-entry demonstration."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pdrs.evaluation import evaluate_ground_truth, load_ground_truth, write_evaluation
from pdrs.fat32_recovery import recover_deleted_fat32
from pdrs.manifest import write_manifest

ROOT = Path(__file__).resolve().parent / "fat32_deleted_demo"
IMAGE = ROOT / "images" / "fat32_deleted_root.img"
TRUTH = ROOT / "ground_truth.csv"
RESULTS = ROOT / "results"


def main() -> None:
    if not IMAGE.is_file() or not TRUTH.is_file():
        raise SystemExit("Demo is missing; run make_fat32_deleted_demo.py first.")
    if RESULTS.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS}")
    RESULTS.mkdir()
    result = recover_deleted_fat32(IMAGE, RESULTS)
    manifest = write_manifest(RESULTS, result.rows)
    evaluation = evaluate_ground_truth(load_ground_truth(TRUTH, IMAGE.name), result.rows)
    comparison, summary = write_evaluation(RESULTS, evaluation)
    if result.warnings:
        (RESULTS / "recovery_warnings.txt").write_text(
            "\n".join(result.warnings) + "\n", encoding="utf-8"
        )
    print(f"Deleted root entries: {result.deleted_entries_seen}")
    print(f"Recovered candidates: {len(result.rows)}")
    print(f"Exact Ground Truth:  {evaluation.summary['recovered_exact_count']}/1")
    print(f"Manifest:            {manifest}")
    print(f"Comparison:          {comparison}")
    print(f"Summary:             {summary}")
    for warning in result.warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
