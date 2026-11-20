"""Build PNG fragments separated between valid IDAT chunks for reassembly research."""

from __future__ import annotations

import csv
import hashlib
import random
import struct
import zlib
from pathlib import Path


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v11"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
SAMPLE_COUNT = 10
IMAGE_OFFSET = 512
TRAILING_BYTES = 512
GAPS = (("baseline", 0), ("gap_64", 64), ("gap_512", 512), ("gap_4096", 4096))
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(chunk_type: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)


def _make_png_parts(seed: int) -> tuple[bytes, bytes, bytes]:
    width = 64
    height = 48
    rng = random.Random(seed)
    scanlines = bytearray()
    for _ in range(height):
        scanlines.append(0)  # PNG filter type None
        scanlines.extend(rng.randbytes(width * 3))
    compressed = zlib.compress(bytes(scanlines), level=6)
    split = len(compressed) // 2
    if split == 0 or split == len(compressed):
        raise ValueError("Compressed PNG data was too short to split into two IDAT chunks")

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    prefix = PNG_SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", compressed[:split])
    suffix = _chunk(b"IDAT", compressed[split:]) + _chunk(b"IEND", b"")
    return prefix, suffix, prefix + suffix


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {ROOT}")
    IMAGE_DIR.mkdir(parents=True)
    SOURCE_DIR.mkdir(parents=True)
    rows: list[dict[str, object]] = []

    for sample_index in range(1, SAMPLE_COUNT + 1):
        prefix, suffix, source_png = _make_png_parts(seed=1100 + sample_index)
        source_name = f"multi_idat_{sample_index:02d}.png"
        source_path = SOURCE_DIR / source_name
        source_path.write_bytes(source_png)
        source_hash = hashlib.sha256(source_png).hexdigest()

        for scenario, gap_bytes in GAPS:
            image_name = f"{scenario}_sample_{sample_index:02d}.img"
            raw_payload = prefix + (b"\xA5" * gap_bytes) + suffix
            image_data = bytearray(IMAGE_OFFSET + len(raw_payload) + TRAILING_BYTES)
            image_data[IMAGE_OFFSET : IMAGE_OFFSET + len(raw_payload)] = raw_payload
            (IMAGE_DIR / image_name).write_bytes(image_data)
            rows.append({
                "image_filename": image_name,
                "scenario": scenario,
                "sample_index": sample_index,
                "gap_bytes": gap_bytes,
                "image_offset": IMAGE_OFFSET,
                "source_filename": source_name,
                "source_size_bytes": len(source_png),
                "embedded_size_bytes": len(raw_payload),
                "source_sha256": source_hash,
                "split_location": "between two consecutive CRC-valid IDAT chunks",
            })

    with (ROOT / "ground_truth.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Independent PNG sources: {SAMPLE_COUNT}")
    print(f"Fragment scenarios:      {len(GAPS)}")
    print(f"Raw images:              {len(rows)}")
    print(f"Images:                  {IMAGE_DIR}")
    print(f"Sources:                 {SOURCE_DIR}")
    print(f"Ground truth:            {ROOT / 'ground_truth.csv'}")


if __name__ == "__main__":
    main()
