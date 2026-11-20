"""Test PDRS PNG acceptance and Pillow pixel equality across valid image variants."""

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


ROOT = Path(__file__).resolve().parent / "experiment_set_v4"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
RESULTS_DIR = ROOT / "results_png_compatibility"


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
        raise SystemExit("Dataset not found. Run make_png_compatibility_set_v4.py first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True)

    details: list[dict[str, object]] = []
    for index, truth in enumerate(_read_csv(truth_path), start=1):
        image_path = IMAGE_DIR / truth["image_filename"]
        output_dir = RESULTS_DIR / truth["variant"]
        run = subprocess.run(
            [sys.executable, "-m", "pdrs.cli", str(image_path), str(output_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode != 0:
            raise RuntimeError(f"PDRS scan failed for {truth['variant']}:\n{run.stderr}")
        manifest = _read_csv(output_dir / "manifest.csv")
        candidate = next((row for row in manifest if int(row["offset"]) == int(truth["expected_offset"])), None)
        structure_valid = candidate is not None and candidate["format_valid"].lower() == "true"
        exact_hash = candidate is not None and candidate["sha256"] == truth["source_sha256"]
        pillow_success = False
        pixel_match = False
        decode_error = ""
        if candidate is not None:
            recovered_path = output_dir / candidate["filename"]
            try:
                source_format, source_mode, source_size, source_pixels = _decode(SOURCE_DIR / truth["source_filename"])
                recovered_format, recovered_mode, recovered_size, recovered_pixels = _decode(recovered_path)
                pillow_success = recovered_format == "PNG"
                pixel_match = (
                    source_format == recovered_format == "PNG"
                    and source_mode == recovered_mode
                    and source_size == recovered_size
                    and source_pixels == recovered_pixels
                )
            except Exception as error:
                decode_error = f"{type(error).__name__}: {error}"

        details.append({
            "variant": truth["variant"],
            "pillow_mode": truth["mode_after_pillow_decode"],
            "dimensions": f"{truth['width']}x{truth['height']}",
            "interlace_flag": truth["interlace_flag_in_png"],
            "candidate_found_at_expected_offset": candidate is not None,
            "pdrs_structure_valid": structure_valid,
            "sha256_exact_match": exact_hash,
            "pillow_decoded_recovery": pillow_success,
            "decoded_pixels_match": pixel_match,
            "validation_note": "" if candidate is None else candidate["validation_note"],
            "pillow_error": decode_error,
        })
        if index % 5 == 0 or index == 10:
            print(f"Completed {index}/10 PNG variants")

    with (RESULTS_DIR / "sample_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)

    summary: dict[str, object] = {
        "valid_samples": len(details),
        "candidate_detections": sum(bool(row["candidate_found_at_expected_offset"]) for row in details),
        "pdrs_structure_valid": sum(bool(row["pdrs_structure_valid"]) for row in details),
        "sha256_exact_matches": sum(bool(row["sha256_exact_match"]) for row in details),
        "pillow_decoded_recoveries": sum(bool(row["pillow_decoded_recovery"]) for row in details),
        "decoded_pixel_matches": sum(bool(row["decoded_pixels_match"]) for row in details),
        "variants_rejected_by_pdrs": sum(not bool(row["pdrs_structure_valid"]) for row in details),
    }
    with (RESULTS_DIR / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary))
        writer.writeheader()
        writer.writerow(summary)
    print(f"Sample details: {RESULTS_DIR / 'sample_details.csv'}")
    print(f"Summary:        {RESULTS_DIR / 'summary.csv'}")


if __name__ == "__main__":
    main()
