"""Compare contiguous PNG carving with bounded IDAT-chunk gap reassembly."""

from __future__ import annotations

import csv
import hashlib
import struct
import zlib
from collections import defaultdict
from io import BytesIO
from pathlib import Path

from PIL import Image

from pdrs.carve import carve_image


ROOT = Path(__file__).resolve().parent / "experiment_set_v11"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
RESULTS_DIR = ROOT / "results_chunk_reassembly"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_GAP_BYTES = 4096
MAX_CHUNK_BYTES = 64 * 1024 * 1024


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _parse_chunk(data: bytes, offset: int) -> tuple[bytes, bytes, int] | None:
    if offset < 0 or offset + 12 > len(data):
        return None
    length = struct.unpack_from(">I", data, offset)[0]
    if length > MAX_CHUNK_BYTES or length > len(data) - offset - 12:
        return None
    chunk_type = data[offset + 4 : offset + 8]
    end = offset + 12 + length
    chunk_bytes = data[offset:end]
    expected_crc = struct.unpack_from(">I", data, end - 4)[0]
    actual_crc = zlib.crc32(chunk_type + data[offset + 8 : end - 4]) & 0xFFFFFFFF
    if actual_crc != expected_crc:
        return None
    return chunk_type, chunk_bytes, end


def _reassemble_at(data: bytes, start: int) -> tuple[bytes, list[int]] | None:
    if data[start : start + len(PNG_SIGNATURE)] != PNG_SIGNATURE:
        return None
    ihdr = _parse_chunk(data, start + len(PNG_SIGNATURE))
    if ihdr is None or ihdr[0] != b"IHDR" or len(ihdr[1]) != 25:
        return None

    output = bytearray(PNG_SIGNATURE + ihdr[1])
    cursor = ihdr[2]
    gap_sizes: list[int] = []
    saw_idat = False

    while cursor < len(data):
        parsed = _parse_chunk(data, cursor)
        if parsed is None:
            found: tuple[int, tuple[bytes, bytes, int]] | None = None
            last_start = min(cursor + MAX_GAP_BYTES, len(data) - 12)
            for candidate_start in range(cursor + 1, last_start + 1):
                candidate = _parse_chunk(data, candidate_start)
                if candidate is not None and candidate[0] in {b"IDAT", b"IEND"}:
                    found = (candidate_start, candidate)
                    break
            if found is None:
                return None
            candidate_start, parsed = found
            gap_sizes.append(candidate_start - cursor)
            cursor = candidate_start

        chunk_type, chunk_bytes, chunk_end = parsed
        if chunk_type == b"IDAT":
            output.extend(chunk_bytes)
            saw_idat = True
            cursor = chunk_end
        elif chunk_type == b"IEND":
            if not saw_idat or len(chunk_bytes) != 12:
                return None
            output.extend(chunk_bytes)
            return bytes(output), gap_sizes
        else:
            return None
    return None


def _reassemble_image(image_bytes: bytes) -> tuple[int, bytes, list[int]] | None:
    search_from = 0
    while True:
        start = image_bytes.find(PNG_SIGNATURE, search_from)
        if start < 0:
            return None
        recovered = _reassemble_at(image_bytes, start)
        if recovered is not None:
            recovered_bytes, gap_sizes = recovered
            return start, recovered_bytes, gap_sizes
        search_from = start + len(PNG_SIGNATURE)


def _decode_pixels(png_bytes: bytes) -> tuple[str, tuple[int, int], bytes]:
    with Image.open(BytesIO(png_bytes)) as image:
        image.load()
        return image.mode, image.size, image.tobytes()


def main() -> None:
    truth_path = ROOT / "ground_truth.csv"
    if not truth_path.is_file():
        raise SystemExit("Dataset not found. Run make_chunk_aligned_fragment_set_v11.py first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True)
    carved_root = RESULTS_DIR / "pdrs_candidates"
    reconstructed_root = RESULTS_DIR / "reassembled"
    reconstructed_root.mkdir()

    sample_rows: list[dict[str, object]] = []
    for truth in _read_csv(truth_path):
        image_name = truth["image_filename"]
        source_path = SOURCE_DIR / truth["source_filename"]
        image_path = IMAGE_DIR / image_name
        output_dir = carved_root / Path(image_name).stem
        pdrs_rows = carve_image(image_path, output_dir)
        expected_offset = int(truth["image_offset"])
        candidate = next((
            row for row in pdrs_rows
            if row["format"] == "png" and int(row["offset"]) == expected_offset
        ), None)
        pdrs_hash_match = candidate is not None and candidate["sha256"] == truth["source_sha256"]

        recovered = _reassemble_image(image_path.read_bytes())
        recovered_bytes = recovered[1] if recovered is not None else b""
        recovered_hash = hashlib.sha256(recovered_bytes).hexdigest() if recovered is not None else ""
        reconstructed_exact = recovered_hash == truth["source_sha256"]
        recovered_path = reconstructed_root / f"{Path(image_name).stem}.png"
        if recovered is not None:
            recovered_path.write_bytes(recovered_bytes)

        pillow_decoded = False
        pixel_content_equal = False
        if recovered is not None:
            try:
                pixel_content_equal = _decode_pixels(recovered_bytes) == _decode_pixels(source_path.read_bytes())
                pillow_decoded = True
            except Exception:
                pillow_decoded = False

        sample_rows.append({
            "image_filename": image_name,
            "scenario": truth["scenario"],
            "sample_index": int(truth["sample_index"]),
            "gap_bytes_expected": int(truth["gap_bytes"]),
            "pdrs_candidate_count": len(pdrs_rows),
            "pdrs_candidate_found": candidate is not None,
            "pdrs_complete_boundary": candidate["complete_boundary"] if candidate else False,
            "pdrs_format_valid": candidate["format_valid"] if candidate else False,
            "pdrs_exact_source_hash": pdrs_hash_match,
            "reassembly_found": recovered is not None,
            "reassembly_gap_count": len(recovered[2]) if recovered is not None else 0,
            "reassembly_gap_bytes_removed": sum(recovered[2]) if recovered is not None else 0,
            "reassembled_exact_source_hash": reconstructed_exact,
            "pillow_decoded": pillow_decoded,
            "decoded_pixels_equal_source": pixel_content_equal,
        })

    with (RESULTS_DIR / "sample_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(sample_rows[0]))
        writer.writeheader()
        writer.writerows(sample_rows)

    summaries: list[dict[str, object]] = []
    by_scenario: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in sample_rows:
        by_scenario[str(row["scenario"])].append(row)
    for scenario, rows in by_scenario.items():
        summaries.append({
            "scenario": scenario,
            "samples": len(rows),
            "gap_bytes": rows[0]["gap_bytes_expected"],
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
    print(f"Reassembly gap search limit: {MAX_GAP_BYTES} bytes")


if __name__ == "__main__":
    main()
