"""Test EOF-gated Pillow validation on V17's five-gap decoy images."""

from __future__ import annotations

import csv
import hashlib
import statistics
import time
from io import BytesIO
from pathlib import Path

from PIL import Image

from run_zlib_pruning_comparison_v18 import _validated_reassemble_with_pruning


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v17"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
V17_DETAILS = ROOT / "results_five_gap_backtracking" / "sample_details.csv"
V18_DETAILS = ROOT / "results_zlib_pruning_comparison" / "sample_details.csv"
RESULTS_DIR = ROOT / "results_zlib_eof_pruning"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _decode_pixels(data: bytes) -> tuple[str, tuple[int, int], bytes]:
    with Image.open(BytesIO(data)) as image:
        image.load()
        return image.mode, image.size, image.tobytes()


def main() -> None:
    if not V17_DETAILS.is_file() or not V18_DETAILS.is_file():
        raise SystemExit("V17/V18 results are missing. Run both comparison scripts first.")
    if RESULTS_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing results: {RESULTS_DIR}")
    RESULTS_DIR.mkdir(parents=True)
    v17 = {row["image_filename"]: row for row in _read_csv(V17_DETAILS) if row["scenario"] == "five_gaps_with_decoys"}
    v18 = {row["image_filename"]: row for row in _read_csv(V18_DETAILS)}
    truths = [row for row in _read_csv(ROOT / "ground_truth.csv") if row["scenario"] == "five_gaps_with_decoys"]
    detail_rows: list[dict[str, object]] = []

    for index, truth in enumerate(truths, start=1):
        image_name = truth["image_filename"]
        data = (IMAGE_DIR / image_name).read_bytes()
        source = (SOURCE_DIR / truth["source_filename"]).read_bytes()
        started = time.perf_counter()
        recovered, stats = _validated_reassemble_with_pruning(data, require_complete_zlib_stream=True)
        v19_time = time.perf_counter() - started
        rebuilt = recovered[1] if recovered else b""
        rebuilt_hash = hashlib.sha256(rebuilt).hexdigest() if recovered else ""
        decoded = False
        pixels_equal = False
        if recovered:
            try:
                decoded = True
                pixels_equal = _decode_pixels(rebuilt) == _decode_pixels(source)
            except Exception:
                decoded = False
            (RESULTS_DIR / f"{Path(image_name).stem}_eof_pruned.png").write_bytes(rebuilt)
        v17_time = float(v17[image_name]["validated_runtime_seconds"])
        v18_time = float(v18[image_name]["zlib_pruned_runtime_seconds"])
        detail_rows.append({
            "image_filename": image_name,
            "v17_full_backtracking_seconds": f"{v17_time:.6f}",
            "v18_zlib_pruning_seconds": f"{v18_time:.6f}",
            "v19_zlib_eof_pruning_seconds": f"{v19_time:.6f}",
            "speedup_vs_v17": f"{v17_time / v19_time:.2f}" if v19_time else "inf",
            "speedup_vs_v18": f"{v18_time / v19_time:.2f}" if v19_time else "inf",
            **stats,
            "exact_source_hash": rebuilt_hash == truth["source_sha256"],
            "pillow_decoded": decoded,
            "pixels_equal_source": pixels_equal,
        })
        print(f"Completed {index}/{len(truths)}: {image_name} (EOF-pruned {v19_time:.3f}s)", flush=True)

    with (RESULTS_DIR / "sample_details.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(detail_rows[0]))
        writer.writeheader()
        writer.writerows(detail_rows)

    v17_times = [float(row["v17_full_backtracking_seconds"]) for row in detail_rows]
    v18_times = [float(row["v18_zlib_pruning_seconds"]) for row in detail_rows]
    v19_times = [float(row["v19_zlib_eof_pruning_seconds"]) for row in detail_rows]
    summary = [{
        "samples": len(detail_rows),
        "v17_mean_seconds": f"{statistics.mean(v17_times):.6f}",
        "v18_mean_seconds": f"{statistics.mean(v18_times):.6f}",
        "v19_mean_seconds": f"{statistics.mean(v19_times):.6f}",
        "mean_speedup_vs_v17": f"{statistics.mean(v17_times) / statistics.mean(v19_times):.2f}",
        "mean_speedup_vs_v18": f"{statistics.mean(v18_times) / statistics.mean(v19_times):.2f}",
        "incomplete_zlib_paths_rejected": sum(int(row["incomplete_zlib_paths"]) for row in detail_rows),
        "zlib_error_branches_rejected": sum(int(row["zlib_rejected_branches"]) for row in detail_rows),
        "pillow_checks_total": sum(int(row["pillow_checks"]) for row in detail_rows),
        "pillow_rejected_paths_total": sum(int(row["pillow_rejected_paths"]) for row in detail_rows),
        "mean_visited_nodes": f"{statistics.mean(int(row['visited_nodes']) for row in detail_rows):.1f}",
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
