"""Create a deterministic synthetic raw image and ground-truth files for a demo."""

from __future__ import annotations

import csv
import hashlib
import random
import struct
import zlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE_DIR = HERE / "synthetic_sources"
IMAGE_PATH = HERE / "sample.img"
GROUND_TRUTH = HERE / "ground_truth.csv"


def png_chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)


def make_png() -> bytes:
    # Valid 2x2 RGBA PNG: IHDR, compressed scanlines, and IEND.
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0)
    pixels = b"\x00" + b"\xff\x33\x66\xff" * 2 + b"\x00" + b"\x66\xcc\x99\xff" * 2
    return signature + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", zlib.compress(pixels)) + png_chunk(b"IEND", b"")


def make_pdf() -> bytes:
    # Minimal marker-bounded PDF-like document for byte-exact carving exercises.
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        b"2 0 obj\n<< /Length 30 >>\nstream\nSynthetic PDRS sample PDF.\nendstream\nendobj\n"
        b"trailer\n<< /Root 1 0 R >>\nstartxref\n0\n%%EOF\n"
    )


def make_jpeg_marker_sample() -> bytes:
    # Marker-bounded fixture only; it is not intended to be a decodable JPEG.
    return b"\xff\xd8\xff\xe0PDRS-SYNTHETIC-JPEG-FIXTURE\xff\xd9"


def main() -> None:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    fixtures = [
        ("sample_jpeg_marker.jpg", "jpeg", make_jpeg_marker_sample()),
        ("sample.png", "png", make_png()),
        ("sample.pdf", "pdf", make_pdf()),
    ]
    rng = random.Random(20261119)
    image = bytearray(b"PDRS-SYNTHETIC-RAW-IMAGE\x00")
    rows: list[dict[str, object]] = []

    for name, kind, content in fixtures:
        image.extend(bytes(rng.randrange(1, 256) for _ in range(37)))
        offset = len(image)
        image.extend(content)
        path = SOURCE_DIR / name
        path.write_bytes(content)
        rows.append({
            "filename": name,
            "format": kind,
            "offset": offset,
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "format_validity_note": "marker-only fixture; not a decodable JPEG" if kind == "jpeg" else "synthetic sample",
        })

    image.extend(bytes(rng.randrange(1, 256) for _ in range(53)))
    IMAGE_PATH.write_bytes(image)
    with GROUND_TRUTH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Synthetic image: {IMAGE_PATH}")
    print(f"Ground truth:    {GROUND_TRUTH}")
    print(f"Source files:    {SOURCE_DIR}")


if __name__ == "__main__":
    main()
