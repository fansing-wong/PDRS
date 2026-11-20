"""Compare PDRS optional JPEG/PDF validation with independent parser outcomes."""

from __future__ import annotations

import csv
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "experiment_set_v6"
IMAGE_DIR = ROOT / "images"
RESULTS_DIR = ROOT / "results_jpeg_pdf_pdrs_validation"
INDEPENDENT_RESULTS = ROOT / "results_jpeg_pdf" / "sample_details.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    truth_path = ROOT / "ground_truth.csv"
    if not truth_path.is_file() or not INDEPENDENT_RESULTS.is_file():
        raise SystemExit("Run the v6 generator and independent-parser experiment first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True)

    independent = {
        (row["scenario"], row["sample_id"]): row["independent_parser_accepted"].lower() == "true"
        for row in _read_csv(INDEPENDENT_RESULTS)
    }
    details: list[dict[str, object]] = []
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)

    for index, truth in enumerate(_read_csv(truth_path), start=1):
        output_dir = RESULTS_DIR / truth["scenario"] / truth["sample_id"]
        result = subprocess.run(
            [sys.executable, "-m", "pdrs.cli", str(IMAGE_DIR / truth["image_filename"]), str(output_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"PDRS scan failed for {truth['scenario']}/{truth['sample_id']}:\n{result.stderr}")
        with (output_dir / "manifest.csv").open(newline="", encoding="utf-8") as handle:
            candidates = list(csv.DictReader(handle))
        candidate = next(
            (row for row in candidates if int(row["offset"]) == int(truth["expected_offset"])),
            None,
        )
        built_in = candidate is not None and candidate["format_valid"].lower() == "true"
        independent_accept = independent[(truth["scenario"], truth["sample_id"])]
        row = {
            "scenario": truth["scenario"],
            "sample_id": truth["sample_id"],
            "target_present": truth["target_present"],
            "candidate_found": candidate is not None,
            "pdrs_format_valid": built_in,
            "independent_parser_accepted": independent_accept,
            "validators_agree": built_in == independent_accept,
            "validation_note": "" if candidate is None else candidate["validation_note"],
        }
        details.append(row)
        grouped[str(row["scenario"])].append(row)
        if index % 10 == 0 or index == 40:
            print(f"Completed {index}/40 built-in validation scans")

    with (RESULTS_DIR / "sample_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)

    summaries: list[dict[str, object]] = []
    for scenario, rows in sorted(grouped.items()):
        summaries.append({
            "scenario": scenario,
            "samples": len(rows),
            "pdrs_format_valid": sum(bool(row["pdrs_format_valid"]) for row in rows),
            "independent_parser_accepts": sum(bool(row["independent_parser_accepted"]) for row in rows),
            "validator_agreements": sum(bool(row["validators_agree"]) for row in rows),
        })
    with (RESULTS_DIR / "scenario_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    print(f"Sample details:  {RESULTS_DIR / 'sample_details.csv'}")
    print(f"Scenario summary:{RESULTS_DIR / 'scenario_summary.csv'}")


if __name__ == "__main__":
    main()
