"""Compare full-decode backtracking with incremental zlib branch pruning."""

from __future__ import annotations

import csv
import hashlib
import statistics
import struct
import time
import zlib
from io import BytesIO
from pathlib import Path

from PIL import Image

from run_chunk_aligned_fragment_set_v11 import MAX_GAP_BYTES, PNG_SIGNATURE, _parse_chunk


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v17"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
INPUT_DETAILS = ROOT / "results_five_gap_backtracking" / "sample_details.csv"
RESULTS_DIR = ROOT / "results_zlib_pruning_comparison"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _decode_pixels(data: bytes) -> tuple[str, tuple[int, int], bytes]:
    with Image.open(BytesIO(data)) as image:
        image.load()
        return image.mode, image.size, image.tobytes()


def _validated_reassemble_with_pruning(
    data: bytes,
    require_complete_zlib_stream: bool = False,
) -> tuple[tuple[int, bytes, list[int]] | None, dict[str, int]]:
    stats = {"visited_nodes": 0, "idat_candidates": 0, "zlib_rejected_branches": 0, "incomplete_zlib_paths": 0, "pillow_checks": 0, "pillow_rejected_paths": 0}

    def _search_at(start: int) -> tuple[bytes, list[int]] | None:
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
                    if require_complete_zlib_stream and not inflater.eof:
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
            return None, stats
        recovered = _search_at(start)
        if recovered is not None:
            return (start, recovered[0], recovered[1]), stats
        search_position = start + len(PNG_SIGNATURE)


def main() -> None:
    if not INPUT_DETAILS.is_file():
        raise SystemExit("V17 results are missing. Run run_five_gap_decoy_set_v17.py first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True)
    old_rows = {
        row["image_filename"]: row
        for row in _read_csv(INPUT_DETAILS)
        if row["scenario"] == "five_gaps_with_decoys"
    }
    truth_rows = [
        row for row in _read_csv(ROOT / "ground_truth.csv")
        if row["scenario"] == "five_gaps_with_decoys"
    ]
    detail_rows: list[dict[str, object]] = []

    for index, truth in enumerate(truth_rows, start=1):
        image_name = truth["image_filename"]
        data = (IMAGE_DIR / image_name).read_bytes()
        source = (SOURCE_DIR / truth["source_filename"]).read_bytes()
        started = time.perf_counter()
        recovered, stats = _validated_reassemble_with_pruning(data)
        pruned_time = time.perf_counter() - started
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
            (RESULTS_DIR / f"{Path(image_name).stem}_pruned.png").write_bytes(rebuilt)
        old = old_rows[image_name]
        old_time = float(old["validated_runtime_seconds"])
        detail_rows.append({
            "image_filename": image_name,
            "full_backtracking_runtime_seconds": old["validated_runtime_seconds"],
            "zlib_pruned_runtime_seconds": f"{pruned_time:.6f}",
            "speedup_vs_full_backtracking": f"{old_time / pruned_time:.2f}" if pruned_time else "inf",
            **stats,
            "recovered": recovered is not None,
            "exact_source_hash": rebuilt_hash == truth["source_sha256"],
            "pillow_decoded": decoded,
            "pixels_equal_source": pixels_equal,
        })
        print(f"Completed {index}/{len(truth_rows)}: {image_name} (pruned {pruned_time:.3f}s)", flush=True)

    with (RESULTS_DIR / "sample_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(detail_rows[0]))
        writer.writeheader()
        writer.writerows(detail_rows)

    old_times = [float(row["full_backtracking_runtime_seconds"]) for row in detail_rows]
    pruned_times = [float(row["zlib_pruned_runtime_seconds"]) for row in detail_rows]
    summary = [{
        "samples": len(detail_rows),
        "full_backtracking_mean_seconds": f"{statistics.mean(old_times):.6f}",
        "zlib_pruned_mean_seconds": f"{statistics.mean(pruned_times):.6f}",
        "mean_speedup": f"{statistics.mean(old_times) / statistics.mean(pruned_times):.2f}",
        "zlib_rejected_branches_total": sum(int(row["zlib_rejected_branches"]) for row in detail_rows),
        "pillow_checks_total": sum(int(row["pillow_checks"]) for row in detail_rows),
        "pillow_rejected_paths_total": sum(int(row["pillow_rejected_paths"]) for row in detail_rows),
        "all_exact_hashes": sum(bool(row["exact_source_hash"]) for row in detail_rows),
        "all_pillow_decoded": sum(bool(row["pillow_decoded"]) for row in detail_rows),
        "all_pixels_equal": sum(bool(row["pixels_equal_source"]) for row in detail_rows),
        "mean_visited_nodes": f"{statistics.mean(int(row['visited_nodes']) for row in detail_rows):.1f}",
    }]
    with (RESULTS_DIR / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)

    print(f"Sample details: {RESULTS_DIR / 'sample_details.csv'}")
    print(f"Summary:        {RESULTS_DIR / 'summary.csv'}")


if __name__ == "__main__":
    main()
