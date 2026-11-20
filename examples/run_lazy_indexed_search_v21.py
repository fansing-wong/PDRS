"""Cache CRC checks only in reachable PNG search windows and test scale."""

from __future__ import annotations

import bisect
import csv
import hashlib
import statistics
import time
import zlib
from io import BytesIO
from pathlib import Path

from PIL import Image

from run_chunk_aligned_fragment_set_v11 import MAX_CHUNK_BYTES, MAX_GAP_BYTES, PNG_SIGNATURE, _parse_chunk


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v17"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
V17_DETAILS = ROOT / "results_five_gap_backtracking" / "sample_details.csv"
RESULTS_DIR = ROOT / "results_lazy_indexed_search"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _decode_pixels(data: bytes) -> tuple[str, tuple[int, int], bytes]:
    with Image.open(BytesIO(data)) as image:
        image.load()
        return image.mode, image.size, image.tobytes()


def _parse_candidate_chunk(data: bytes, offset: int) -> tuple[bytes, bytes, int] | None:
    if offset < 0 or offset + 12 > len(data):
        return None
    chunk_type = data[offset + 4 : offset + 8]
    if chunk_type not in {b"IDAT", b"IEND"}:
        return None
    length = int.from_bytes(data[offset : offset + 4], "big")
    if length > MAX_CHUNK_BYTES or length > len(data) - offset - 12:
        return None
    end = offset + 12 + length
    chunk_bytes = data[offset:end]
    expected_crc = int.from_bytes(data[end - 4 : end], "big")
    actual_crc = zlib.crc32(chunk_type + data[offset + 8 : end - 4]) & 0xFFFFFFFF
    if actual_crc != expected_crc:
        return None
    return chunk_type, chunk_bytes, end


def _lazy_indexed_reassemble(
    data: bytes,
    fast_candidate_probe: bool = False,
) -> tuple[tuple[int, bytes, list[int]] | None, dict[str, int]]:
    stats = {
        "visited_nodes": 0,
        "unique_offsets_parsed": 0,
        "indexed_crc_chunks": 0,
        "idat_candidates": 0,
        "zlib_rejected_branches": 0,
        "incomplete_zlib_paths": 0,
        "pillow_checks": 0,
        "pillow_rejected_paths": 0,
    }
    parse_cache: dict[int, tuple[bytes, bytes, int] | None] = {}
    candidate_chunks: dict[int, tuple[bytes, bytes, int]] = {}
    candidate_offsets: list[int] = []
    covered_ranges: list[tuple[int, int]] = []

    def parse_at(offset: int) -> tuple[bytes, bytes, int] | None:
        if offset not in parse_cache:
            parser = _parse_candidate_chunk if fast_candidate_probe else _parse_chunk
            parse_cache[offset] = parser(data, offset)
        return parse_cache[offset]

    def index_candidate(offset: int, parsed: tuple[bytes, bytes, int] | None) -> None:
        if parsed is None or parsed[0] not in {b"IDAT", b"IEND"} or offset in candidate_chunks:
            return
        candidate_chunks[offset] = parsed
        bisect.insort(candidate_offsets, offset)

    def mark_covered(start: int, end: int) -> None:
        index = 0
        while index < len(covered_ranges) and covered_ranges[index][1] + 1 < start:
            index += 1
        merged_start, merged_end = start, end
        while index < len(covered_ranges) and covered_ranges[index][0] <= merged_end + 1:
            merged_start = min(merged_start, covered_ranges[index][0])
            merged_end = max(merged_end, covered_ranges[index][1])
            covered_ranges.pop(index)
        covered_ranges.insert(index, (merged_start, merged_end))

    def ensure_indexed(start: int, end: int) -> None:
        if start > end:
            return
        cursor = start
        while cursor <= end:
            containing = next((right for left, right in covered_ranges if left <= cursor <= right), None)
            if containing is not None:
                cursor = containing + 1
                continue
            next_start = min((left for left, _ in covered_ranges if left > cursor), default=end + 1)
            segment_end = min(end, next_start - 1, len(data) - 12)
            if segment_end < cursor:
                return
            for offset in range(cursor, segment_end + 1):
                index_candidate(offset, parse_at(offset))
            mark_covered(cursor, segment_end)
            cursor = segment_end + 1

    def search_at(start: int) -> tuple[bytes, list[int]] | None:
        ihdr = _parse_chunk(data, start + len(PNG_SIGNATURE))
        if ihdr is None or ihdr[0] != b"IHDR" or len(ihdr[1]) != 25:
            return None

        def walk(
            cursor: int,
            output: bytes,
            inflater: zlib.Decompress,
            saw_idat: bool,
            gap_sizes: list[int],
            depth: int,
        ) -> tuple[bytes, list[int]] | None:
            stats["visited_nodes"] += 1
            if depth > 64:
                return None
            direct = parse_at(cursor)
            index_candidate(cursor, direct)
            choices: list[tuple[int, tuple[bytes, bytes, int], int]] = []
            if direct is not None and direct[0] in {b"IDAT", b"IEND"}:
                choices.append((cursor, direct, 0))
            else:
                last_start = min(cursor + MAX_GAP_BYTES, len(data) - 12)
                ensure_indexed(cursor + 1, last_start)
                index = bisect.bisect_right(candidate_offsets, cursor)
                while index < len(candidate_offsets) and candidate_offsets[index] <= last_start:
                    candidate_start = candidate_offsets[index]
                    choices.append((candidate_start, candidate_chunks[candidate_start], candidate_start - cursor))
                    index += 1

            for candidate_start, chunk, skipped in choices:
                chunk_type, chunk_bytes, chunk_end = chunk
                next_gaps = gap_sizes + [skipped] if skipped else gap_sizes
                next_output = output + chunk_bytes
                if chunk_type == b"IDAT":
                    stats["idat_candidates"] += 1
                    next_inflater = inflater.copy()
                    try:
                        next_inflater.decompress(chunk_bytes[8:-4])
                    except zlib.error:
                        stats["zlib_rejected_branches"] += 1
                        continue
                    recovered = walk(chunk_end, next_output, next_inflater, True, next_gaps, depth + 1)
                    if recovered is not None:
                        return recovered
                elif saw_idat and len(chunk_bytes) == 12:
                    if not inflater.eof:
                        stats["incomplete_zlib_paths"] += 1
                        continue
                    stats["pillow_checks"] += 1
                    try:
                        _decode_pixels(next_output)
                    except Exception:
                        stats["pillow_rejected_paths"] += 1
                        continue
                    return next_output, next_gaps
            return None

        return walk(ihdr[2], PNG_SIGNATURE + ihdr[1], zlib.decompressobj(), False, [], 0)

    search_position = 0
    while True:
        start = data.find(PNG_SIGNATURE, search_position)
        if start < 0:
            stats["unique_offsets_parsed"] = len(parse_cache)
            stats["indexed_crc_chunks"] = len(candidate_offsets)
            return None, stats
        recovered = search_at(start)
        if recovered is not None:
            stats["unique_offsets_parsed"] = len(parse_cache)
            stats["indexed_crc_chunks"] = len(candidate_offsets)
            return (start, recovered[0], recovered[1]), stats
        search_position = start + len(PNG_SIGNATURE)


def main() -> None:
    if not V17_DETAILS.is_file():
        raise SystemExit("V17 results are missing. Run run_five_gap_decoy_set_v17.py first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True)
    source_details = {row["image_filename"]: row for row in _read_csv(V17_DETAILS)}
    truths = [row for row in _read_csv(ROOT / "ground_truth.csv") if row["scenario"] == "five_gaps_with_decoys"]
    details: list[dict[str, object]] = []
    for index, truth in enumerate(truths, start=1):
        image_name = truth["image_filename"]
        data = (IMAGE_DIR / image_name).read_bytes()
        source = (SOURCE_DIR / truth["source_filename"]).read_bytes()
        started = time.perf_counter()
        recovered, stats = _lazy_indexed_reassemble(data)
        elapsed = time.perf_counter() - started
        rebuilt = recovered[1] if recovered else b""
        digest = hashlib.sha256(rebuilt).hexdigest() if recovered else ""
        pixels_equal = bool(recovered) and _decode_pixels(rebuilt) == _decode_pixels(source)
        detail = {
            "image_filename": image_name,
            "v17_full_backtracking_seconds": source_details[image_name]["validated_runtime_seconds"],
            "v20_full_index_seconds": "0.988780",
            "v21_lazy_index_seconds": f"{elapsed:.6f}",
            "speedup_vs_v17": f"{float(source_details[image_name]['validated_runtime_seconds']) / elapsed:.2f}" if elapsed else "inf",
            **stats,
            "exact_source_hash": digest == truth["source_sha256"],
            "pixels_equal_source": pixels_equal,
        }
        details.append(detail)
        if recovered:
            (RESULTS_DIR / f"{Path(image_name).stem}_lazy_indexed.png").write_bytes(rebuilt)
        print(f"Completed {index}/{len(truths)}: {image_name} ({elapsed:.3f}s)", flush=True)

    with (RESULTS_DIR / "sample_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)

    pad_source_name = truths[0]["image_filename"]
    pad_truth = truths[0]
    pad_base = (IMAGE_DIR / pad_source_name).read_bytes()
    pad_source = (SOURCE_DIR / pad_truth["source_filename"]).read_bytes()
    pad_rows: list[dict[str, object]] = []
    for size_mib in (1, 16, 64):
        target_bytes = size_mib * 1024 * 1024
        if len(pad_base) > target_bytes:
            raise ValueError("Base image is larger than the requested padded size")
        padded = pad_base + bytes(target_bytes - len(pad_base))
        started = time.perf_counter()
        recovered, stats = _lazy_indexed_reassemble(padded)
        elapsed = time.perf_counter() - started
        rebuilt = recovered[1] if recovered else b""
        digest = hashlib.sha256(rebuilt).hexdigest() if recovered else ""
        pixels_equal = bool(recovered) and _decode_pixels(rebuilt) == _decode_pixels(pad_source)
        pad_rows.append({
            "raw_image_size_mib": size_mib,
            "elapsed_seconds": f"{elapsed:.6f}",
            **stats,
            "exact_source_hash": digest == pad_truth["source_sha256"],
            "pixels_equal_source": pixels_equal,
        })
        print(f"Padded image {size_mib} MiB: {elapsed:.3f}s", flush=True)
    with (RESULTS_DIR / "padded_scale_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(pad_rows[0]))
        writer.writeheader()
        writer.writerows(pad_rows)

    times = [float(row["v21_lazy_index_seconds"]) for row in details]
    summary = [{
        "five_gap_samples": len(details),
        "mean_v21_seconds": f"{statistics.mean(times):.6f}",
        "max_v21_seconds": f"{max(times):.6f}",
        "mean_speedup_vs_v17": f"{statistics.mean(float(row['v17_full_backtracking_seconds']) for row in details) / statistics.mean(times):.2f}",
        "mean_unique_offsets_parsed": f"{statistics.mean(int(row['unique_offsets_parsed']) for row in details):.1f}",
        "mean_visited_nodes": f"{statistics.mean(int(row['visited_nodes']) for row in details):.1f}",
        "pillow_checks_total": sum(int(row["pillow_checks"]) for row in details),
        "all_exact_hashes": sum(bool(row["exact_source_hash"]) for row in details),
        "all_pixels_equal": sum(bool(row["pixels_equal_source"]) for row in details),
    }]
    with (RESULTS_DIR / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    print(f"Sample details: {RESULTS_DIR / 'sample_details.csv'}")
    print(f"Padded scale:   {RESULTS_DIR / 'padded_scale_details.csv'}")
    print(f"Summary:        {RESULTS_DIR / 'summary.csv'}")


if __name__ == "__main__":
    main()
