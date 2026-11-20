"""Compare greedy and validated backtracking on two-gap, three-IDAT PNGs."""

from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from pathlib import Path

from pdrs.carve import carve_image
from run_chunk_aligned_fragment_set_v11 import _decode_pixels, _reassemble_image
from run_crc_decoy_fragment_set_v13 import _content_check, _validated_reassemble


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v14"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
RESULTS_DIR = ROOT / "results_multi_gap_backtracking_verified"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    truth_path = ROOT / "ground_truth.csv"
    if not truth_path.is_file():
        raise SystemExit("Dataset not found. Run make_multi_gap_decoy_set_v14.py first.")
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
        source = (SOURCE_DIR / truth["source_filename"]).read_bytes()
        pdrs_rows = carve_image(image_path, candidate_root / Path(image_name).stem)
        expected_offset = int(truth["image_offset"])
        pdrs_candidate = next((
            row for row in pdrs_rows
            if row["format"] == "png" and int(row["offset"]) == expected_offset
        ), None)
        raw_image = image_path.read_bytes()
        greedy = _reassemble_image(raw_image)
        validated = _validated_reassemble(raw_image)
        greedy_bytes = greedy[1] if greedy else b""
        validated_bytes = validated[1] if validated else b""
        greedy_decoded, greedy_pixels_equal = _content_check(greedy_bytes, source) if greedy else (False, False)
        validated_decoded, validated_pixels_equal = _content_check(validated_bytes, source) if validated else (False, False)
        greedy_hash = hashlib.sha256(greedy_bytes).hexdigest() if greedy else ""
        validated_hash = hashlib.sha256(validated_bytes).hexdigest() if validated else ""

        if greedy:
            (reconstructed_root / f"{Path(image_name).stem}_greedy.png").write_bytes(greedy_bytes)
        if validated:
            (reconstructed_root / f"{Path(image_name).stem}_validated.png").write_bytes(validated_bytes)

        sample_rows.append({
            "image_filename": image_name,
            "scenario": truth["scenario"],
            "sample_index": int(truth["sample_index"]),
            "gap1_bytes": int(truth["gap1_bytes"]),
            "gap2_bytes": int(truth["gap2_bytes"]),
            "decoys_gap1": int(truth["decoys_gap1"]),
            "decoys_gap2": int(truth["decoys_gap2"]),
            "pdrs_candidate_count": len(pdrs_rows),
            "pdrs_format_valid": pdrs_candidate["format_valid"] if pdrs_candidate else False,
            "pdrs_exact_source_hash": pdrs_candidate is not None and pdrs_candidate["sha256"] == truth["source_sha256"],
            "greedy_reassembly_found": greedy is not None,
            "greedy_exact_source_hash": greedy_hash == truth["source_sha256"],
            "greedy_pillow_decoded": greedy_decoded,
            "greedy_pixels_equal_source": greedy_pixels_equal,
            "validated_reassembly_found": validated is not None,
            "validated_gap_bytes_removed": sum(validated[2]) if validated else 0,
            "validated_exact_source_hash": validated_hash == truth["source_sha256"],
            "validated_pillow_decoded": validated_decoded,
            "validated_pixels_equal_source": validated_pixels_equal,
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
            "gap1_bytes": rows[0]["gap1_bytes"],
            "gap2_bytes": rows[0]["gap2_bytes"],
            "decoys_gap1": rows[0]["decoys_gap1"],
            "decoys_gap2": rows[0]["decoys_gap2"],
            "pdrs_format_valid": sum(bool(row["pdrs_format_valid"]) for row in rows),
            "pdrs_exact_source_hashes": sum(bool(row["pdrs_exact_source_hash"]) for row in rows),
            "greedy_exact_source_hashes": sum(bool(row["greedy_exact_source_hash"]) for row in rows),
            "greedy_pillow_decoded": sum(bool(row["greedy_pillow_decoded"]) for row in rows),
            "validated_exact_source_hashes": sum(bool(row["validated_exact_source_hash"]) for row in rows),
            "validated_pillow_decoded": sum(bool(row["validated_pillow_decoded"]) for row in rows),
            "validated_pixels_equal_source": sum(bool(row["validated_pixels_equal_source"]) for row in rows),
        })
    with (RESULTS_DIR / "scenario_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)

    print(f"Sample details:  {RESULTS_DIR / 'sample_details.csv'}")
    print(f"Scenario summary:{RESULTS_DIR / 'scenario_summary.csv'}")
    print(f"Reconstructed PNGs: {reconstructed_root}")
    print("Validated backtracking accepts paths only after full Pillow decode.")


if __name__ == "__main__":
    main()
