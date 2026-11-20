"""Measure V22 indexed PNG recovery in reproducible random backgrounds."""

from __future__ import annotations

import csv
import hashlib
import random
import statistics
import time
from pathlib import Path

from run_lazy_indexed_search_v21 import _decode_pixels, _lazy_indexed_reassemble


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v17"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
RESULTS_DIR = ROOT / "results_random_background_scale"
SAMPLE_NAME = "five_gaps_with_decoys_sample_01.img"
RANDOM_SEED = 231119
SIZES_MIB = (1, 16, 64)
REPEATS = 3
EMBED_OFFSET = 512


def _read_truth() -> tuple[dict[str, str], bytes, bytes]:
    truth = next(
        row for row in csv.DictReader((ROOT / "ground_truth.csv").open(encoding="utf-8", newline=""))
        if row["image_filename"] == SAMPLE_NAME
    )
    raw = (IMAGE_DIR / SAMPLE_NAME).read_bytes()
    png = raw[EMBED_OFFSET : len(raw) - 512]
    source = (SOURCE_DIR / truth["source_filename"]).read_bytes()
    return truth, png, source


def main() -> None:
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True)
    truth, png, source = _read_truth()
    random_bytes = random.Random(RANDOM_SEED).randbytes(max(SIZES_MIB) * 1024 * 1024)
    details: list[dict[str, object]] = []

    for size_mib in SIZES_MIB:
        target_size = size_mib * 1024 * 1024
        raw_image = bytearray(random_bytes[:target_size])
        raw_image[EMBED_OFFSET : EMBED_OFFSET + len(png)] = png
        data = bytes(raw_image)
        for trial in range(1, REPEATS + 1):
            started = time.perf_counter()
            recovered, stats = _lazy_indexed_reassemble(data, fast_candidate_probe=True)
            elapsed = time.perf_counter() - started
            rebuilt = recovered[1] if recovered else b""
            exact = bool(recovered) and hashlib.sha256(rebuilt).hexdigest() == truth["source_sha256"]
            pixels_equal = bool(recovered) and _decode_pixels(rebuilt) == _decode_pixels(source)
            if not exact or not pixels_equal:
                raise RuntimeError(f"Recovery verification failed at {size_mib} MiB, trial {trial}")
            details.append({
                "raw_image_size_mib": size_mib,
                "trial": trial,
                "random_seed": RANDOM_SEED,
                "embed_offset": EMBED_OFFSET,
                "elapsed_seconds": f"{elapsed:.6f}",
                "unique_offsets_parsed": stats["unique_offsets_parsed"],
                "indexed_crc_chunks": stats["indexed_crc_chunks"],
                "visited_nodes": stats["visited_nodes"],
                "pillow_checks": stats["pillow_checks"],
                "exact_source_hash": exact,
                "pixels_equal_source": pixels_equal,
            })
            print(f"{size_mib} MiB random image trial {trial}/{REPEATS}: {elapsed:.3f}s", flush=True)

    details_path = RESULTS_DIR / "sample_details.csv"
    with details_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)

    summaries: list[dict[str, object]] = []
    for size_mib in SIZES_MIB:
        rows = [row for row in details if int(row["raw_image_size_mib"]) == size_mib]
        timings = [float(row["elapsed_seconds"]) for row in rows]
        summaries.append({
            "raw_image_size_mib": size_mib,
            "repeats": len(rows),
            "random_seed": RANDOM_SEED,
            "mean_seconds": f"{statistics.mean(timings):.6f}",
            "median_seconds": f"{statistics.median(timings):.6f}",
            "min_seconds": f"{min(timings):.6f}",
            "max_seconds": f"{max(timings):.6f}",
            "all_exact_hashes": sum(bool(row["exact_source_hash"]) for row in rows),
            "all_pixels_equal": sum(bool(row["pixels_equal_source"]) for row in rows),
        })
    summary_path = RESULTS_DIR / "scenario_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    print(f"Sample details: {details_path}")
    print(f"Scenario summary: {summary_path}")
    print(f"Source SHA-256: {truth['source_sha256']}")


if __name__ == "__main__":
    main()
