"""Create a tiny BMP carving demo image and its ground-truth record."""

from __future__ import annotations

import csv
import hashlib
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "bmp_demo_set"
IMAGE = ROOT / "bmp_demo.img"
SOURCE = ROOT / "source.bmp"
GROUND_TRUTH = ROOT / "ground_truth.csv"
BMP_OFFSET = 64


def make_bmp24() -> bytes:
    width, height, bits_per_pixel = 2, 2, 24
    row_stride = ((width * bits_per_pixel + 31) // 32) * 4
    pixels = bytes((0, 0, 255, 0, 255, 0, 0, 0, 255, 0, 0, 255, 255, 255, 0, 0))
    file_size = 14 + 40 + len(pixels)
    file_header = b"BM" + struct.pack("<IHHI", file_size, 0, 0, 54)
    dib_header = struct.pack(
        "<IiiHHIIiiII",
        40,
        width,
        height,
        1,
        bits_per_pixel,
        0,
        row_stride * height,
        2835,
        2835,
        0,
        0,
    )
    return file_header + dib_header + pixels


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing demo directory: {ROOT}")
    ROOT.mkdir(parents=True)
    bmp = make_bmp24()
    prefix = bytearray(BMP_OFFSET)
    decoy = b"PDRS BMP demo; invalid BM"
    prefix[: len(decoy)] = decoy
    IMAGE.write_bytes(bytes(prefix) + bmp + b"\x00" * 32)
    SOURCE.write_bytes(bmp)
    with GROUND_TRUTH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("image_filename", "source_filename", "expected_offset", "source_sha256"),
        )
        writer.writeheader()
        writer.writerow(
            {
                "image_filename": IMAGE.name,
                "source_filename": SOURCE.name,
                "expected_offset": BMP_OFFSET,
                "source_sha256": hashlib.sha256(bmp).hexdigest(),
            }
        )
    print(f"Synthetic image: {IMAGE}")
    print(f"Source BMP:      {SOURCE}")
    print(f"Ground truth:    {GROUND_TRUTH}")
    print(f"Expected offset: {BMP_OFFSET}")


if __name__ == "__main__":
    main()
