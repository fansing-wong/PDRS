"""Cross-check recovered v3 candidates using Pillow as an independent decoder."""

from __future__ import annotations

import csv
from pathlib import Path

try:
    from PIL import Image
except ImportError as error:
    raise SystemExit(
        "Pillow is not installed. Run: .venv/Scripts/python.exe -m pip install 'Pillow>=10'"
    ) from error


ROOT = Path(__file__).resolve().parent / "experiment_set_v3"
SOURCE_DIR = ROOT / "sources"
RECOVERY_DIR = ROOT / "results_png_decode_validation"
OUTPUT_DIR = ROOT / "pillow_cross_validation"


def decode_png(path: Path) -> tuple[str, tuple[int, int], bytes]:
    """Fully decode an image and return its format, dimensions, and pixel bytes."""
    with Image.open(path) as image:
        image.load()
        return image.format or "unknown", image.size, image.tobytes()


def main() -> None:
    truth_path = ROOT / "ground_truth.csv"
    if not truth_path.is_file() or not (RECOVERY_DIR / "scenario_summary.csv").is_file():
        raise SystemExit("V3 data and 0.3 validation results must exist before cross-validation.")
    if OUTPUT_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {OUTPUT_DIR}")

    OUTPUT_DIR.mkdir(parents=True)
    with truth_path.open(newline="", encoding="utf-8") as handle:
        truths = list(csv.DictReader(handle))

    details: list[dict[str, object]] = []
    for truth in truths:
        scenario = truth["scenario"]
        sample_id = truth["sample_id"]
        target_present = truth["target_present"].lower() == "true"
        manifest_path = RECOVERY_DIR / scenario / sample_id / "manifest.csv"
        with manifest_path.open(newline="", encoding="utf-8") as handle:
            candidates = list(csv.DictReader(handle))

        candidate_path = RECOVERY_DIR / scenario / sample_id / candidates[0]["filename"] if candidates else None
        source_path = SOURCE_DIR / f"{sample_id}.png"
        pillow_success = False
        pixel_match = False
        pillow_format = ""
        dimensions = ""
        error_note = ""

        if candidate_path is not None:
            try:
                pillow_format, image_size, candidate_pixels = decode_png(candidate_path)
                dimensions = f"{image_size[0]}x{image_size[1]}"
                pillow_success = pillow_format == "PNG"
                if target_present and pillow_success:
                    source_format, source_size, source_pixels = decode_png(source_path)
                    pixel_match = (
                        source_format == "PNG"
                        and source_size == image_size
                        and source_pixels == candidate_pixels
                    )
            except Exception as error:  # Pillow raises format-specific exceptions.
                error_note = f"{type(error).__name__}: {error}"

        details.append({
            "scenario": scenario,
            "sample_id": sample_id,
            "target_present": target_present,
            "candidate_emitted": candidate_path is not None,
            "pillow_decoded_as_png": pillow_success,
            "dimensions": dimensions,
            "decoded_pixels_match_source": pixel_match,
            "decode_error": error_note,
        })

    with (OUTPUT_DIR / "sample_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)

    summaries: list[dict[str, object]] = []
    for scenario in sorted({str(row["scenario"]) for row in details}):
        rows = [row for row in details if row["scenario"] == scenario]
        targets = sum(bool(row["target_present"]) for row in rows)
        decoded = sum(bool(row["pillow_decoded_as_png"]) for row in rows)
        exact_pixels = sum(bool(row["decoded_pixels_match_source"]) for row in rows)
        summaries.append({
            "scenario": scenario,
            "samples": len(rows),
            "target_samples": targets,
            "pillow_png_decode_successes": decoded,
            "pixel_exact_matches": exact_pixels,
            "decoys_rejected_by_decoder": len(rows) - decoded if targets == 0 else "N/A",
        })

    with (OUTPUT_DIR / "scenario_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)

    print(f"Sample details:  {OUTPUT_DIR / 'sample_details.csv'}")
    print(f"Scenario summary:{OUTPUT_DIR / 'scenario_summary.csv'}")


if __name__ == "__main__":
    main()
