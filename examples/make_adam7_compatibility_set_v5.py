"""Generate valid non-interlaced controls and manually encoded Adam7 PNGs."""

from __future__ import annotations

import csv
import hashlib
import random
import struct
import zlib
from pathlib import Path

try:
    from PIL import Image
except ImportError as error:
    raise SystemExit("Pillow is required. Install it with: .venv/Scripts/python.exe -m pip install 'Pillow>=10'") from error


ROOT = Path(__file__).resolve().parent / "experiment_set_v5"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
DIMENSIONS = ((8, 13), (16, 17), (24, 21), (32, 27), (48, 35), (64, 43), (80, 51), (96, 59), (112, 67), (128, 75))
ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def _chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)


def _make_adam7_png(width: int, height: int, seed: int) -> bytes:
    rng = random.Random(seed)
    pixels = [bytes(rng.randrange(256) for _ in range(4)) for _ in range(width * height)]
    scanlines = bytearray()
    for start_x, start_y, step_x, step_y in ADAM7:
        xs = list(range(start_x, width, step_x))
        for y in range(start_y, height, step_y):
            if not xs:
                continue
            scanlines.append(0)  # No filter; each Adam7 pass has independent rows.
            for x in xs:
                scanlines.extend(pixels[y * width + x])

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 1)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(scanlines))
        + _chunk(b"IEND", b"")
    )


def _make_control_png(width: int, height: int, seed: int) -> bytes:
    rng = random.Random(seed)
    image = Image.new("RGBA", (width, height))
    for index in range(width * height):
        x, y = index % width, index // width
        image.putpixel((x, y), tuple(rng.randrange(256) for _ in range(4)))
    path = SOURCE_DIR / f"temporary_{width}x{height}.png"
    image.save(path, format="PNG")
    data = path.read_bytes()
    path.unlink()
    return data


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {ROOT}\nMove it aside or use a fresh project copy.")
    IMAGE_DIR.mkdir(parents=True)
    SOURCE_DIR.mkdir(parents=True)
    rows: list[dict[str, object]] = []

    for index, (width, height) in enumerate(DIMENSIONS, start=1):
        sample_id = f"adam7_{index:02d}"
        control = _make_control_png(width, height, 204000 + index)
        adam7 = _make_adam7_png(width, height, 205000 + index)
        source_path = SOURCE_DIR / f"{sample_id}.png"
        raw_path = IMAGE_DIR / f"{sample_id}.img"

        with Image.open(__import__("io").BytesIO(adam7)) as decoded:
            decoded.load()
            if decoded.size != (width, height) or decoded.mode != "RGBA":
                raise ValueError(f"Pillow could not decode generated Adam7 sample {sample_id} as expected")

        # Paired entries use same-size valid controls and Adam7 files.
        for kind, png_data in (("control", control), ("adam7", adam7)):
            name = f"{sample_id}_{kind}"
            source = SOURCE_DIR / f"{name}.png"
            source.write_bytes(png_data)
            png_info = png_data[28]
            prefix = f"PDRS-ADAM7-{name}\x00".encode("ascii") + bytes(range(1, 42))
            offset = len(prefix)
            image_path = IMAGE_DIR / f"{name}.img"
            image_path.write_bytes(prefix + png_data + bytes(range(60, 91)))
            rows.append({
                "sample_id": name,
                "kind": kind,
                "source_filename": source.name,
                "image_filename": image_path.name,
                "width": width,
                "height": height,
                "interlace_flag": png_info,
                "expected_offset": offset,
                "source_size_bytes": len(png_data),
                "source_sha256": hashlib.sha256(png_data).hexdigest(),
            })

    with (ROOT / "ground_truth.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Valid PNG images: {len(rows)} (10 controls + 10 Adam7 samples)")
    print(f"Images:      {IMAGE_DIR}")
    print(f"Sources:     {SOURCE_DIR}")
    print(f"Ground truth:{ROOT / 'ground_truth.csv'}")


if __name__ == "__main__":
    main()
