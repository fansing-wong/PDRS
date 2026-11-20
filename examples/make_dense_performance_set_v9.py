"""Create independent, fully written raw images for a size-scaling benchmark."""

from __future__ import annotations

import csv
import hashlib
import random
from pathlib import Path


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v9"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = EXAMPLES / "experiment_set_v6" / "sources"
SAMPLE_SOURCES = (
    ("jpeg", SOURCE_DIR / "sample_01.jpeg"),
    ("png", EXAMPLES / "experiment_set_v4" / "sources" / "rgb8_small.png"),
    ("pdf", SOURCE_DIR / "sample_01.pdf"),
)
IMAGE_SIZES_MIB = (1, 16, 64)
INDEPENDENT_IMAGES_PER_SIZE = 3
CHUNK_SIZE = 1024 * 1024


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {ROOT}")
    for fmt, source in SAMPLE_SOURCES:
        if not source.is_file():
            raise SystemExit(f"Required source fixture is missing: {source}")

    IMAGE_DIR.mkdir(parents=True)
    source_data = [(fmt, path.name, path.read_bytes()) for fmt, path in SAMPLE_SOURCES]
    rows: list[dict[str, object]] = []

    for size_mib in IMAGE_SIZES_MIB:
        image_size = size_mib * 1024 * 1024
        for sample_index in range(1, INDEPENDENT_IMAGES_PER_SIZE + 1):
            image_name = f"raw_{size_mib:03d}MiB_sample_{sample_index:02d}.img"
            image_path = IMAGE_DIR / image_name
            seed = size_mib * 100 + sample_index
            rng = random.Random(seed)

            # Write nonzero deterministic filler across the entire image.
            with image_path.open("wb") as handle:
                remaining = image_size
                while remaining:
                    block_size = min(CHUNK_SIZE, remaining)
                    handle.write(rng.randbytes(block_size))
                    remaining -= block_size

            fractions = (0.10, 0.50, 0.90)
            with image_path.open("r+b") as handle:
                for (fmt, source_name, content), fraction in zip(source_data, fractions):
                    offset = int(image_size * fraction)
                    if offset + len(content) >= image_size:
                        raise ValueError(f"Fixture does not fit in {image_name}: {source_name}")
                    handle.seek(offset)
                    handle.write(content)
                    rows.append({
                        "image_filename": image_name,
                        "image_size_bytes": image_size,
                        "image_size_mib": size_mib,
                        "sample_index": sample_index,
                        "random_seed": seed,
                        "format": fmt,
                        "source_filename": source_name,
                        "expected_offset": offset,
                        "source_size_bytes": len(content),
                        "source_sha256": hashlib.sha256(content).hexdigest(),
                    })

    with (ROOT / "ground_truth.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    total_images = len(IMAGE_SIZES_MIB) * INDEPENDENT_IMAGES_PER_SIZE
    print(f"Raw images: {total_images} ({INDEPENDENT_IMAGES_PER_SIZE} per size: 1, 16, 64 MiB)")
    print(f"Known files: {len(source_data)} per image (JPEG, PNG, PDF)")
    print(f"Images:      {IMAGE_DIR}")
    print(f"Ground truth:{ROOT / 'ground_truth.csv'}")


if __name__ == "__main__":
    main()
