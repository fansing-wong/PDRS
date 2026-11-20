"""Avoid CRC work on non-IDAT bytes in the lazy PNG candidate index."""

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
V17_DETAILS = ROOT / "results_five_gap_backtracking" / "sample_details.csv"
V20_SUMMARY = ROOT / "results_indexed_zlib_search" / "summary.csv"
V21_DETAILS = ROOT / "results_lazy_indexed_search" / "sample_details.csv"
RESULTS_DIR = ROOT / "results_fast_candidate_index"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _run_one(data: bytes, source: bytes) -> tuple[float, object, dict[str, int], bool, bool]:
    started = time.perf_counter()
    recovered, stats = _lazy_indexed_reassemble(data, fast_candidate_probe=True)
    elapsed = time.perf_counter() - started
    rebuilt = recovered[1] if recovered else b""
    digest = hashlib.sha256(rebuilt).hexdigest() if recovered else ""
    pixels_equal = False
    if recovered:
        try:
            pixels_equal = _decode_pixels(rebuilt) == _decode_pixels(source)
        except Exception:
            pixels_equal = False
    return elapsed, recovered, stats, digest == hashlib.sha256(source).hexdigest(), pixels_equal


def main() -> None:
    required = (V17_DETAILS, V20_SUMMARY, V21_DETAILS, ROOT / "ground_truth.csv")
    if any(not path.is_file() for path in required):
        raise SystemExit("V17/V20/V21 results are missing; run the earlier experiments first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True)
    v17 = {row["image_filename"]: row for row in _read_csv(V17_DETAILS) if row["scenario"] == "five_gaps_with_decoys"}
    v21 = {row["image_filename"]: row for row in _read_csv(V21_DETAILS)}
    v20_mean = float(_read_csv(V20_SUMMARY)[0]["v20_mean_seconds"])
    truths = [row for row in _read_csv(ROOT / "ground_truth.csv") if row["scenario"] == "five_gaps_with_decoys"]
    details: list[dict[str, object]] = []

    for index, truth in enumerate(truths, start=1):
        image_name = truth["image_filename"]
        data = (IMAGE_DIR / image_name).read_bytes()
        source = (SOURCE_DIR / truth["source_filename"]).read_bytes()
        elapsed, recovered, stats, exact_hash, pixels_equal = _run_one(data, source)
        if recovered:
            (RESULTS_DIR / f"{Path(image_name).stem}_fast_index.png").write_bytes(recovered[1])
        v17_time = float(v17[image_name]["validated_runtime_seconds"])
        v21_time = float(v21[image_name]["v21_lazy_index_seconds"])
        details.append({
            "image_filename": image_name,
            "v17_seconds": f"{v17_time:.6f}",
            "v20_full_index_mean_seconds": f"{v20_mean:.6f}",
            "v21_lazy_index_seconds": f"{v21_time:.6f}",
            "v22_fast_lazy_index_seconds": f"{elapsed:.6f}",
            "speedup_vs_v17": f"{v17_time / elapsed:.2f}" if elapsed else "inf",
            **stats,
            "exact_source_hash": exact_hash,
            "pixels_equal_source": pixels_equal,
        })
        print(f"Completed {index}/{len(truths)}: {image_name} ({elapsed:.3f}s)", flush=True)

    with (RESULTS_DIR / "sample_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)

    pad_truth = truths[0]
    base = (IMAGE_DIR / pad_truth["image_filename"]).read_bytes()
    source = (SOURCE_DIR / pad_truth["source_filename"]).read_bytes()
    padded_rows: list[dict[str, object]] = []
    for size_mib in (1, 16, 64):
        target = size_mib * 1024 * 1024
        padded = base + bytes(target - len(base))
        elapsed, recovered, stats, exact_hash, pixels_equal = _run_one(padded, source)
        padded_rows.append({
            "raw_image_size_mib": size_mib,
            "elapsed_seconds": f"{elapsed:.6f}",
            **stats,
            "exact_source_hash": exact_hash,
            "pixels_equal_source": pixels_equal,
        })
        print(f"Padded image {size_mib} MiB: {elapsed:.3f}s", flush=True)
    with (RESULTS_DIR / "padded_scale_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(padded_rows[0]))
        writer.writeheader()
        writer.writerows(padded_rows)

    times = [float(row["v22_fast_lazy_index_seconds"]) for row in details]
    summary = [{
        "samples": len(details),
        "v17_mean_seconds": f"{statistics.mean(float(row['v17_seconds']) for row in details):.6f}",
        "v20_full_index_mean_seconds": f"{v20_mean:.6f}",
        "v21_lazy_index_mean_seconds": f"{statistics.mean(float(row['v21_lazy_index_seconds']) for row in details):.6f}",
        "v22_fast_lazy_index_mean_seconds": f"{statistics.mean(times):.6f}",
        "v22_max_seconds": f"{max(times):.6f}",
        "mean_speedup_vs_v17": f"{statistics.mean(float(row['v17_seconds']) for row in details) / statistics.mean(times):.2f}",
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
