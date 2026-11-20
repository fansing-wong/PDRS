"""Run V11 chunk-aware reassembly against gap-size and within-chunk controls."""

from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from pathlib import Path

from pdrs.carve import carve_image
from run_chunk_aligned_fragment_set_v11 import _decode_pixels, _reassemble_image


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v12"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
RESULTS_DIR = ROOT / "results_boundary_limits"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    truth_path = ROOT / "ground_truth.csv"
    if not truth_path.is_file():
        raise SystemExit("Dataset not found. Run make_fragment_boundary_limit_set_v12.py first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True)
    candidate_root = RESULTS_DIR / "pdrs_candidates"
    reconstructed_root = RESULTS_DIR / "reassembled"
    reconstructed_root.mkdir()

    sample_rows: list[dict[str, object]] = []
    for truth in _read_csv(truth_path):
        image_name = truth["image_filename"]
        image_path = IMAGE_DIR / image_name
        source_path = SOURCE_DIR / truth["source_filename"]
        pdrs_rows = carve_image(image_path, candidate_root / Path(image_name).stem)
        expected_offset = int(truth["image_offset"])
        pdrs_candidate = next((
            row for row in pdrs_rows
            if row["format"] == "png" and int(row["offset"]) == expected_offset
        ), None)

        recovered = _reassemble_image(image_path.read_bytes())
        recovered_bytes = recovered[1] if recovered is not None else b""
        recovered_hash = hashlib.sha256(recovered_bytes).hexdigest() if recovered is not None else ""
        exact_hash = recovered_hash == truth["source_sha256"]
        recovered_path = reconstructed_root / f"{Path(image_name).stem}.png"
        if recovered is not None:
            recovered_path.write_bytes(recovered_bytes)

        pillow_decoded = False
        pixel_equal = False
        if recovered is not None:
            try:
                pixel_equal = _decode_pixels(recovered_bytes) == _decode_pixels(source_path.read_bytes())
                pillow_decoded = True
            except Exception:
                pillow_decoded = False

        sample_rows.append({
            "image_filename": image_name,
            "scenario": truth["scenario"],
            "sample_index": int(truth["sample_index"]),
            "gap_bytes": int(truth["gap_bytes"]),
            "gap_location": truth["gap_location"],
            "first_idat_payload_bytes": int(truth["first_idat_payload_bytes"]),
            "pdrs_candidate_found": pdrs_candidate is not None,
            "pdrs_candidate_count": len(pdrs_rows),
            "pdrs_complete_boundary": pdrs_candidate["complete_boundary"] if pdrs_candidate else False,
            "pdrs_format_valid": pdrs_candidate["format_valid"] if pdrs_candidate else False,
            "pdrs_exact_source_hash": pdrs_candidate is not None and pdrs_candidate["sha256"] == truth["source_sha256"],
            "reassembly_found": recovered is not None,
            "reassembly_gap_count": len(recovered[2]) if recovered is not None else 0,
            "reassembly_gap_bytes_removed": sum(recovered[2]) if recovered is not None else 0,
            "reassembled_exact_source_hash": exact_hash,
            "pillow_decoded": pillow_decoded,
            "decoded_pixels_equal_source": pixel_equal,
        })

    with (RESULTS_DIR / "sample_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(sample_rows[0]))
        writer.writeheader()
        writer.writerows(sample_rows)

    by_scenario: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in sample_rows:
        by_scenario[str(row["scenario"])].append(row)
    summaries: list[dict[str, object]] = []
    for scenario, rows in by_scenario.items():
        summaries.append({
            "scenario": scenario,
            "samples": len(rows),
            "gap_bytes": rows[0]["gap_bytes"],
            "gap_location": rows[0]["gap_location"],
            "pdrs_candidates_found": sum(bool(row["pdrs_candidate_found"]) for row in rows),
            "pdrs_complete_boundaries": sum(bool(row["pdrs_complete_boundary"]) for row in rows),
            "pdrs_format_valid": sum(bool(row["pdrs_format_valid"]) for row in rows),
            "pdrs_exact_source_hashes": sum(bool(row["pdrs_exact_source_hash"]) for row in rows),
            "reassembly_successes": sum(bool(row["reassembly_found"]) for row in rows),
            "reassembled_exact_source_hashes": sum(bool(row["reassembled_exact_source_hash"]) for row in rows),
            "pillow_decoded": sum(bool(row["pillow_decoded"]) for row in rows),
            "decoded_pixels_equal_source": sum(bool(row["decoded_pixels_equal_source"]) for row in rows),
        })
    with (RESULTS_DIR / "scenario_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)

    print(f"Sample details:  {RESULTS_DIR / 'sample_details.csv'}")
    print(f"Scenario summary:{RESULTS_DIR / 'scenario_summary.csv'}")
    print(f"Reconstructed PNGs: {reconstructed_root}")
    print("Reassembly gap search limit: 4096 bytes")


if __name__ == "__main__":
    main()
