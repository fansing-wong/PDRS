"""Repeat V22's padded-image scale control three times per image size."""

from __future__ import annotations

import csv
import hashlib
import statistics
import time
from pathlib import Path

from run_lazy_indexed_search_v21 import _decode_pixels, _lazy_indexed_reassemble


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v17"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
OUTPUT_DIR = ROOT / "results_fast_candidate_index"
SAMPLE_NAME = "five_gaps_with_decoys_sample_01.img"
REPEATS = 3


def main() -> None:
    output_path = OUTPUT_DIR / "padded_scale_repeats.csv"
    if output_path.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {output_path}")
    truth = next(
        row for row in csv.DictReader((ROOT / "ground_truth.csv").open(encoding="utf-8", newline=""))
        if row["image_filename"] == SAMPLE_NAME
    )
    base = (IMAGE_DIR / SAMPLE_NAME).read_bytes()
    source = (SOURCE_DIR / truth["source_filename"]).read_bytes()
    details: list[dict[str, object]] = []

    for size_mib in (1, 16, 64):
        target_bytes = size_mib * 1024 * 1024
        data = base + bytes(target_bytes - len(base))
        for trial in range(1, REPEATS + 1):
            started = time.perf_counter()
            recovered, stats = _lazy_indexed_reassemble(data, fast_candidate_probe=True)
            elapsed = time.perf_counter() - started
            rebuilt = recovered[1] if recovered else b""
            exact = bool(recovered) and hashlib.sha256(rebuilt).hexdigest() == truth["source_sha256"]
            pixels_equal = bool(recovered) and _decode_pixels(rebuilt) == _decode_pixels(source)
            if not exact or not pixels_equal:
                raise RuntimeError(f"Recovery verification failed for the {size_mib} MiB padded image")
            details.append({
                "raw_image_size_mib": size_mib,
                "trial": trial,
                "elapsed_seconds": f"{elapsed:.6f}",
                "unique_offsets_parsed": stats["unique_offsets_parsed"],
                "indexed_crc_chunks": stats["indexed_crc_chunks"],
                "visited_nodes": stats["visited_nodes"],
                "exact_source_hash": exact,
                "pixels_equal_source": pixels_equal,
            })
            print(f"{size_mib} MiB trial {trial}/{REPEATS}: {elapsed:.3f}s", flush=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)

    summary_path = OUTPUT_DIR / "padded_scale_repeat_summary.csv"
    if summary_path.exists():
        raise SystemExit(f"Refusing to overwrite existing summary: {summary_path}")
    summaries: list[dict[str, object]] = []
    for size_mib in (1, 16, 64):
        rows = [row for row in details if int(row["raw_image_size_mib"]) == size_mib]
        timings = [float(row["elapsed_seconds"]) for row in rows]
        summaries.append({
            "raw_image_size_mib": size_mib,
            "repeats": len(rows),
            "mean_seconds": f"{statistics.mean(timings):.6f}",
            "median_seconds": f"{statistics.median(timings):.6f}",
            "min_seconds": f"{min(timings):.6f}",
            "max_seconds": f"{max(timings):.6f}",
            "mean_unique_offsets_parsed": f"{statistics.mean(int(row['unique_offsets_parsed']) for row in rows):.1f}",
            "all_exact_hashes": sum(bool(row["exact_source_hash"]) for row in rows),
            "all_pixels_equal": sum(bool(row["pixels_equal_source"]) for row in rows),
        })
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    print(f"Details: {output_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
