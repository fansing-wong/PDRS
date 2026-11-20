"""Run PDRS carving against the synthetic recovery scenario set."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pdrs.carve import carve_image
from pdrs.evaluation import evaluate_ground_truth, load_ground_truth, write_evaluation
from pdrs.manifest import write_manifest

ROOT = Path(__file__).resolve().parent / "recovery_scenario_set_v1"
IMAGE_DIR = ROOT / "images"
TRUTH_PATH = ROOT / "ground_truth.csv"
RESULTS = ROOT / "results"


def main() -> None:
    if not IMAGE_DIR.is_dir() or not TRUTH_PATH.is_file():
        raise SystemExit("Scenario set is missing; run make_recovery_scenario_set_v1.py first.")
    if RESULTS.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS}")
    RESULTS.mkdir()
    summary_rows = []
    for image_path in sorted(IMAGE_DIR.glob("*.img")):
        output = RESULTS / image_path.stem
        output.mkdir()
        rows = carve_image(image_path, output)
        write_manifest(output, rows)
        truth = load_ground_truth(TRUTH_PATH, image_path.name)
        evaluation = evaluate_ground_truth(truth, rows)
        write_evaluation(output, evaluation)
        exact = evaluation.summary["recovered_exact_count"]
        expected = evaluation.summary["expected_present_count"]
        valid = sum(row.get("format_valid") is True for row in rows)
        complete = sum(row.get("complete_boundary") is True for row in rows)
        summary_rows.append({
            "scenario": image_path.stem,
            "candidate_count": len(rows),
            "complete_count": complete,
            "format_valid_count": valid,
            "exact_recovery_count": exact,
            "expected_present_count": expected,
            "recovery_recall": evaluation.summary["recovery_recall"],
            "validation_note": rows[0].get("validation_note", "no candidate") if rows else "no candidate",
        })
        print(f"{image_path.name}: candidates={len(rows)}, exact={exact}/{expected}")

    summary_path = RESULTS / "scenario_summary.csv"
    with summary_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
