"""Compare greedy and Pillow-validated backtracking on CRC-valid chunk decoys."""

from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from pathlib import Path

from pdrs.carve import carve_image
from run_chunk_aligned_fragment_set_v11 import (
    MAX_GAP_BYTES,
    PNG_SIGNATURE,
    _decode_pixels,
    _parse_chunk,
    _reassemble_image,
)


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v13"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
RESULTS_DIR = ROOT / "results_decoy_backtracking"


def _validated_at(data: bytes, start: int) -> tuple[bytes, list[int]] | None:
    ihdr = _parse_chunk(data, start + len(PNG_SIGNATURE))
    if ihdr is None or ihdr[0] != b"IHDR" or len(ihdr[1]) != 25:
        return None

    def walk(
        cursor: int,
        output: bytes,
        saw_idat: bool,
        gap_sizes: list[int],
        depth: int,
    ) -> tuple[bytes, list[int]] | None:
        if depth > 64:
            return None
        parsed = _parse_chunk(data, cursor)
        choices: list[tuple[int, tuple[bytes, bytes, int], int]] = []
        if parsed is not None and parsed[0] in {b"IDAT", b"IEND"}:
            choices.append((cursor, parsed, 0))
        else:
            last_start = min(cursor + MAX_GAP_BYTES, len(data) - 12)
            for candidate_start in range(cursor + 1, last_start + 1):
                candidate = _parse_chunk(data, candidate_start)
                if candidate is not None and candidate[0] in {b"IDAT", b"IEND"}:
                    choices.append((candidate_start, candidate, candidate_start - cursor))

        for candidate_start, chunk, skipped in choices:
            chunk_type, chunk_bytes, chunk_end = chunk
            next_gaps = gap_sizes + [skipped] if skipped else gap_sizes
            next_output = output + chunk_bytes
            if chunk_type == b"IDAT":
                recovered = walk(chunk_end, next_output, True, next_gaps, depth + 1)
                if recovered is not None:
                    return recovered
            elif saw_idat and len(chunk_bytes) == 12:
                try:
                    _decode_pixels(next_output)
                except Exception:
                    continue
                return next_output, next_gaps
        return None

    return walk(ihdr[2], PNG_SIGNATURE + ihdr[1], False, [], 0)


def _validated_reassemble(data: bytes) -> tuple[int, bytes, list[int]] | None:
    search_from = 0
    while True:
        start = data.find(PNG_SIGNATURE, search_from)
        if start < 0:
            return None
        recovered = _validated_at(data, start)
        if recovered is not None:
            return start, recovered[0], recovered[1]
        search_from = start + len(PNG_SIGNATURE)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _content_check(data: bytes, source: bytes) -> tuple[bool, bool]:
    try:
        decoded_equal = _decode_pixels(data) == _decode_pixels(source)
        return True, decoded_equal
    except Exception:
        return False, False


def main() -> None:
    truth_path = ROOT / "ground_truth.csv"
    if not truth_path.is_file():
        raise SystemExit("Dataset not found. Run make_crc_decoy_fragment_set_v13.py first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True)
    candidate_root = RESULTS_DIR / "pdrs_candidates"
    output_root = RESULTS_DIR / "reassembled"
    output_root.mkdir()

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

        if greedy is not None:
            (output_root / f"{Path(image_name).stem}_greedy.png").write_bytes(greedy_bytes)
        if validated is not None:
            (output_root / f"{Path(image_name).stem}_validated.png").write_bytes(validated_bytes)

        sample_rows.append({
            "image_filename": image_name,
            "scenario": truth["scenario"],
            "sample_index": int(truth["sample_index"]),
            "gap_bytes": int(truth["gap_bytes"]),
            "decoy_chunk_bytes": int(truth["decoy_chunk_bytes"]),
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
            "gap_bytes": rows[0]["gap_bytes"],
            "decoy_chunk_bytes": rows[0]["decoy_chunk_bytes"],
            "pdrs_format_valid": sum(bool(row["pdrs_format_valid"]) for row in rows),
            "pdrs_exact_source_hashes": sum(bool(row["pdrs_exact_source_hash"]) for row in rows),
            "greedy_reassembly_successes": sum(bool(row["greedy_reassembly_found"]) for row in rows),
            "greedy_exact_source_hashes": sum(bool(row["greedy_exact_source_hash"]) for row in rows),
            "greedy_pillow_decoded": sum(bool(row["greedy_pillow_decoded"]) for row in rows),
            "validated_reassembly_successes": sum(bool(row["validated_reassembly_found"]) for row in rows),
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
    print(f"Reassembled PNGs: {output_root}")
    print("Backtracking accepts a chunk path only when Pillow fully decodes the rebuilt PNG.")


if __name__ == "__main__":
    main()
