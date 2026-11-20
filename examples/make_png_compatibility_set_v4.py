"""Create valid PNG variants with Pillow to measure validator compatibility."""

from __future__ import annotations

import csv
import hashlib
import random
from pathlib import Path

try:
    from PIL import Image
except ImportError as error:
    raise SystemExit("Pillow is required. Install it with: .venv/Scripts/python.exe -m pip install 'Pillow>=10'") from error


ROOT = Path(__file__).resolve().parent / "experiment_set_v4"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"


VARIANTS = (
    ("rgb8_small", "RGB", (16, 8), 6, False),
    ("rgba8", "RGBA", (21, 13), 6, False),
    ("grayscale8", "L", (19, 7), 6, False),
    ("grayscale1", "1", (21, 9), 6, False),
    ("palette8", "P", (33, 17), 6, False),
    ("grayscale16", "I;16", (22, 10), 6, False),
    ("grayscale_alpha8", "LA", (13, 11), 6, False),
    ("rgb8_large_low_compression", "RGB", (128, 64), 1, False),
    ("rgba8_large_high_compression", "RGBA", (96, 64), 9, False),
    ("rgb8_adam7_requested", "RGB", (32, 32), 6, True),
)


def _make_image(name: str, mode: str, size: tuple[int, int]) -> Image.Image:
    rng = random.Random(181000 + len(name) * 97 + size[0] * 13 + size[1])
    image = Image.new(mode, size)
    pixel_count = size[0] * size[1]
    if mode == "P":
        palette = []
        for index in range(256):
            palette.extend(((index * 37) % 256, (index * 73) % 256, (index * 109) % 256))
        image.putpalette(palette)
        image.putdata([rng.randrange(16) for _ in range(pixel_count)])
    elif mode == "1":
        image.putdata([255 if rng.randrange(2) else 0 for _ in range(pixel_count)])
    elif mode == "I;16":
        image.putdata([rng.randrange(65536) for _ in range(pixel_count)])
    else:
        bands = len(image.getbands())
        if bands == 1:
            image.putdata([rng.randrange(256) for _ in range(pixel_count)])
        else:
            for index in range(pixel_count):
                x, y = index % size[0], index // size[0]
                image.putpixel((x, y), tuple(rng.randrange(256) for _ in range(bands)))
    return image


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {ROOT}\nMove it aside or use a fresh project copy.")
    IMAGE_DIR.mkdir(parents=True)
    SOURCE_DIR.mkdir(parents=True)
    rows: list[dict[str, object]] = []

    for name, mode, size, compression, request_interlace in VARIANTS:
        source_path = SOURCE_DIR / f"{name}.png"
        image = _make_image(name, mode, size)
        image.save(source_path, format="PNG", compress_level=compression, interlace=int(request_interlace))
        png_bytes = source_path.read_bytes()
        actual_interlace = png_bytes[28]
        raw_path = IMAGE_DIR / f"{name}.img"
        prefix = f"PDRS-COMPAT-{name}\x00".encode("ascii") + bytes(range(1, 42))
        offset = len(prefix)
        raw_path.write_bytes(prefix + png_bytes + bytes(range(60, 91)))

        with Image.open(source_path) as check:
            check.load()
            decoded_mode = check.mode
            decoded_size = check.size

        rows.append({
            "variant": name,
            "source_filename": source_path.name,
            "image_filename": raw_path.name,
            "mode_after_pillow_decode": decoded_mode,
            "width": decoded_size[0],
            "height": decoded_size[1],
            "compression_level": compression,
            "adam7_requested": request_interlace,
            "interlace_flag_in_png": actual_interlace,
            "expected_offset": offset,
            "source_size_bytes": len(png_bytes),
            "source_sha256": hashlib.sha256(png_bytes).hexdigest(),
        })

    with (ROOT / "ground_truth.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Valid PNG variants: {len(rows)}")
    print(f"Images:      {IMAGE_DIR}")
    print(f"Sources:     {SOURCE_DIR}")
    print(f"Ground truth:{ROOT / 'ground_truth.csv'}")


if __name__ == "__main__":
    main()
