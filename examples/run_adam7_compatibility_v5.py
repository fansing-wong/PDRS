"""Compare PDRS and Pillow on valid PNG controls and Adam7 files."""

from __future__ import annotations

import csv
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

try:
    from PIL import Image
except ImportError as error:
    raise SystemExit("Pillow is required. Install it with: .venv/Scripts/python.exe -m pip install 'Pillow>=10'") from error


ROOT = Path(__file__).resolve().parent / "experiment_set_v5"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
RESULTS_DIR = ROOT / "results_adam7_compatibility"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _decode(path: Path) -> tuple[str, str, tuple[int, int], bytes]:
    with Image.open(path) as image:
        image.load()
        return image.format or "unknown", image.mode, image.size, image.tobytes()


def main() -> None:
    truth_path = ROOT / "ground_truth.csv"
    if not truth_path.is_file():
        raise SystemExit("Dataset not found. Run make_adam7_compatibility_set_v5.py first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True)

    details: list[dict[str, object]] = []
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    truths = _read_csv(truth_path)
    for index, truth in enumerate(truths, start=1):
        output_dir = RESULTS_DIR / truth["kind"] / truth["sample_id"]
        run = subprocess.run(
            [sys.executable, "-m", "pdrs.cli", str(IMAGE_DIR / truth["image_filename"]), str(output_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode != 0:
            raise RuntimeError(f"PDRS scan failed for {truth['sample_id']}:\n{run.stderr}")
        manifest = _read_csv(output_dir / "manifest.csv")
        candidate = next((row for row in manifest if int(row["offset"]) == int(truth["expected_offset"])), None)
        structure_valid = candidate is not None and candidate["format_valid"].lower() == "true"
        hash_match = candidate is not None and candidate["sha256"] == truth["source_sha256"]
        pillow_success = False
        pixel_match = False
        error_note = ""
        if candidate is not None:
            try:
                source_decoded = _decode(SOURCE_DIR / truth["source_filename"])
                recovered_decoded = _decode(output_dir / candidate["filename"])
                pillow_success = recovered_decoded[0] == "PNG"
                pixel_match = source_decoded == recovered_decoded
            except Exception as error:
                error_note = f"{type(error).__name__}: {error}"

        row = {
            "sample_id": truth["sample_id"],
            "kind": truth["kind"],
            "width": truth["width"],
            "height": truth["height"],
            "interlace_flag": truth["interlace_flag"],
            "candidate_found": candidate is not None,
            "pdrs_structure_valid": structure_valid,
            "sha256_exact_match": hash_match,
            "pillow_decoded": pillow_success,
            "decoded_pixels_and_mode_match": pixel_match,
            "validation_note": "" if candidate is None else candidate["validation_note"],
            "decode_error": error_note,
        }
        details.append(row)
        grouped[str(row["kind"])].append(row)
        if index % 5 == 0 or index == len(truths):
            print(f"Completed {index}/{len(truths)} PNG scans")

    with (RESULTS_DIR / "sample_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)

    summaries: list[dict[str, object]] = []
    for kind, rows in sorted(grouped.items()):
        summaries.append({
            "kind": kind,
            "samples": len(rows),
            "candidate_detections": sum(bool(row["candidate_found"]) for row in rows),
            "pdrs_structure_valid": sum(bool(row["pdrs_structure_valid"]) for row in rows),
            "sha256_exact_matches": sum(bool(row["sha256_exact_match"]) for row in rows),
            "pillow_decoded": sum(bool(row["pillow_decoded"]) for row in rows),
            "decoded_pixel_matches": sum(bool(row["decoded_pixels_and_mode_match"]) for row in rows),
            "rejected_by_pdrs": sum(not bool(row["pdrs_structure_valid"]) for row in rows),
        })
    with (RESULTS_DIR / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    print(f"Sample details: {RESULTS_DIR / 'sample_details.csv'}")
    print(f"Summary:        {RESULTS_DIR / 'summary.csv'}")


if __name__ == "__main__":
    main()
