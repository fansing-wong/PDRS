"""Index CRC-valid chunks once, then backtrack with zlib EOF pruning."""

from __future__ import annotations

import bisect
import csv
import hashlib
import statistics
import struct
import time
import zlib
from collections import defaultdict
from io import BytesIO
from pathlib import Path

from PIL import Image

from run_chunk_aligned_fragment_set_v11 import MAX_GAP_BYTES, PNG_SIGNATURE, _parse_chunk


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v17"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
V17_DETAILS = ROOT / "results_five_gap_backtracking" / "sample_details.csv"
V19_DETAILS = ROOT / "results_zlib_eof_pruning" / "sample_details.csv"
RESULTS_DIR = ROOT / "results_indexed_zlib_search"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _decode_pixels(data: bytes) -> tuple[str, tuple[int, int], bytes]:
    with Image.open(BytesIO(data)) as image:
        image.load()
        return image.mode, image.size, image.tobytes()


def _indexed_reassemble(data: bytes) -> tuple[tuple[int, bytes, list[int]] | None, dict[str, int]]:
    stats = {
        "indexed_crc_chunks": 0,
        "visited_nodes": 0,
        "idat_candidates": 0,
        "zlib_rejected_branches": 0,
        "incomplete_zlib_paths": 0,
        "pillow_checks": 0,
        "pillow_rejected_paths": 0,
    }
    chunk_index: dict[int, tuple[bytes, bytes, int]] = {}
    for offset in range(max(0, len(data) - 11)):
        parsed = _parse_chunk(data, offset)
        if parsed is not None and parsed[0] in {b"IDAT", b"IEND"}:
            chunk_index[offset] = parsed
    chunk_offsets = sorted(chunk_index)
    stats["indexed_crc_chunks"] = len(chunk_offsets)

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
            direct = chunk_index.get(cursor)
            choices: list[tuple[int, tuple[bytes, bytes, int], int]] = []
            if direct is not None:
                choices.append((cursor, direct, 0))
            else:
                last_start = min(cursor + MAX_GAP_BYTES, len(data) - 12)
                index = bisect.bisect_right(chunk_offsets, cursor)
                while index < len(chunk_offsets) and chunk_offsets[index] <= last_start:
                    candidate_start = chunk_offsets[index]
                    choices.append((candidate_start, chunk_index[candidate_start], candidate_start - cursor))
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

    search_from = 0
    while True:
        start = data.find(PNG_SIGNATURE, search_from)
        if start < 0:
            return None, stats
        recovered = search_at(start)
        if recovered is not None:
            return (start, recovered[0], recovered[1]), stats
        search_from = start + len(PNG_SIGNATURE)


def main() -> None:
    if not V17_DETAILS.is_file() or not V19_DETAILS.is_file():
        raise SystemExit("V17/V19 results are missing. Run the earlier reassembly scripts first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True)
    v17 = {row["image_filename"]: row for row in _read_csv(V17_DETAILS) if row["scenario"] == "five_gaps_with_decoys"}
    v19 = {row["image_filename"]: row for row in _read_csv(V19_DETAILS)}
    truths = [row for row in _read_csv(ROOT / "ground_truth.csv") if row["scenario"] == "five_gaps_with_decoys"]
    detail_rows: list[dict[str, object]] = []

    for index, truth in enumerate(truths, start=1):
        image_name = truth["image_filename"]
        data = (IMAGE_DIR / image_name).read_bytes()
        source = (SOURCE_DIR / truth["source_filename"]).read_bytes()
        started = time.perf_counter()
        recovered, stats = _indexed_reassemble(data)
        v20_time = time.perf_counter() - started
        rebuilt = recovered[1] if recovered else b""
        rebuilt_hash = hashlib.sha256(rebuilt).hexdigest() if recovered else ""
        pixels_equal = False
        decoded = False
        if recovered:
            try:
                pixels_equal = _decode_pixels(rebuilt) == _decode_pixels(source)
                decoded = True
            except Exception:
                pass
            (RESULTS_DIR / f"{Path(image_name).stem}_indexed.png").write_bytes(rebuilt)
        v17_time = float(v17[image_name]["validated_runtime_seconds"])
        v19_time = float(v19[image_name]["v19_zlib_eof_pruning_seconds"])
        detail_rows.append({
            "image_filename": image_name,
            "v17_full_backtracking_seconds": f"{v17_time:.6f}",
            "v19_zlib_eof_pruning_seconds": f"{v19_time:.6f}",
            "v20_indexed_zlib_search_seconds": f"{v20_time:.6f}",
            "speedup_vs_v17": f"{v17_time / v20_time:.2f}" if v20_time else "inf",
            "speedup_vs_v19": f"{v19_time / v20_time:.2f}" if v20_time else "inf",
            **stats,
            "exact_source_hash": rebuilt_hash == truth["source_sha256"],
            "pillow_decoded": decoded,
            "pixels_equal_source": pixels_equal,
        })
        print(f"Completed {index}/{len(truths)}: {image_name} (indexed {v20_time:.3f}s)", flush=True)

    with (RESULTS_DIR / "sample_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(detail_rows[0]))
        writer.writeheader()
        writer.writerows(detail_rows)

    v17_times = [float(row["v17_full_backtracking_seconds"]) for row in detail_rows]
    v19_times = [float(row["v19_zlib_eof_pruning_seconds"]) for row in detail_rows]
    v20_times = [float(row["v20_indexed_zlib_search_seconds"]) for row in detail_rows]
    summary = [{
        "samples": len(detail_rows),
        "v17_mean_seconds": f"{statistics.mean(v17_times):.6f}",
        "v19_mean_seconds": f"{statistics.mean(v19_times):.6f}",
        "v20_mean_seconds": f"{statistics.mean(v20_times):.6f}",
        "mean_speedup_vs_v17": f"{statistics.mean(v17_times) / statistics.mean(v20_times):.2f}",
        "mean_speedup_vs_v19": f"{statistics.mean(v19_times) / statistics.mean(v20_times):.2f}",
        "mean_indexed_crc_chunks": f"{statistics.mean(int(row['indexed_crc_chunks']) for row in detail_rows):.1f}",
        "mean_visited_nodes": f"{statistics.mean(int(row['visited_nodes']) for row in detail_rows):.1f}",
        "zlib_error_branches_rejected": sum(int(row["zlib_rejected_branches"]) for row in detail_rows),
        "incomplete_zlib_paths_rejected": sum(int(row["incomplete_zlib_paths"]) for row in detail_rows),
        "pillow_checks_total": sum(int(row["pillow_checks"]) for row in detail_rows),
        "pillow_rejected_paths_total": sum(int(row["pillow_rejected_paths"]) for row in detail_rows),
        "all_exact_hashes": sum(bool(row["exact_source_hash"]) for row in detail_rows),
        "all_pillow_decoded": sum(bool(row["pillow_decoded"]) for row in detail_rows),
        "all_pixels_equal": sum(bool(row["pixels_equal_source"]) for row in detail_rows),
    }]
    with (RESULTS_DIR / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    print(f"Sample details: {RESULTS_DIR / 'sample_details.csv'}")
    print(f"Summary:        {RESULTS_DIR / 'summary.csv'}")


if __name__ == "__main__":
    main()
