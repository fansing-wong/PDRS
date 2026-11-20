"""Create zero-filled raw images of increasing size with known JPEG/PNG/PDF samples."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v8"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = EXAMPLES / "experiment_set_v6" / "sources"
SAMPLE_SOURCES = (
    ("jpeg", SOURCE_DIR / "sample_01.jpeg"),
    ("png", EXAMPLES / "experiment_set_v4" / "sources" / "rgb8_small.png"),
    ("pdf", SOURCE_DIR / "sample_01.pdf"),
)
IMAGE_SIZES_MIB = (1, 16, 64)


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {ROOT}\nMove it aside or use a fresh project copy.")
    for fmt, source in SAMPLE_SOURCES:
        if not source.is_file():
            raise SystemExit(f"Required source fixture is missing: {source}")
    IMAGE_DIR.mkdir(parents=True)
    source_data = [(fmt, path.name, path.read_bytes()) for fmt, path in SAMPLE_SOURCES]
    rows: list[dict[str, object]] = []

    for size_mib in IMAGE_SIZES_MIB:
        image_size = size_mib * 1024 * 1024
        image_path = IMAGE_DIR / f"raw_{size_mib:03d}MiB.img"
        with image_path.open("wb") as handle:
            handle.truncate(image_size)  # extend to a zero-filled image

        # Space files apart and spread them through each image.
        fractions = (0.10, 0.50, 0.90)
        with image_path.open("r+b") as handle:
            for (fmt, source_name, content), fraction in zip(source_data, fractions):
                offset = int(image_size * fraction)
                if offset + len(content) >= image_size:
                    raise ValueError(f"Fixture does not fit in {image_path.name}: {source_name}")
                handle.seek(offset)
                handle.write(content)
                rows.append({
                    "image_filename": image_path.name,
                    "image_size_bytes": image_size,
                    "image_size_mib": size_mib,
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
    print(f"Raw images: {len(IMAGE_SIZES_MIB)} ({', '.join(map(str, IMAGE_SIZES_MIB))} MiB)")
    print(f"Known files: {len(source_data)} per image (JPEG, PNG, PDF)")
    print(f"Images:      {IMAGE_DIR}")
    print(f"Ground truth:{ROOT / 'ground_truth.csv'}")


if __name__ == "__main__":
    main()
