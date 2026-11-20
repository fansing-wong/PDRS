"""Build positive and negative controls for the V11 PNG chunk-gap reassembler."""

from __future__ import annotations

import csv
import hashlib
import random
import struct
import zlib
from pathlib import Path


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v12"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
SAMPLE_COUNT = 10
IMAGE_OFFSET = 512
TRAILING_BYTES = 512
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SCENARIOS = (
    ("baseline", 0, "none"),
    ("aligned_gap_4096", 4096, "between_idat_chunks"),
    ("aligned_gap_8192", 8192, "between_idat_chunks"),
    ("inside_idat_gap_64", 64, "inside_first_idat_payload"),
)


def _chunk(chunk_type: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)


def _make_png_parts(seed: int) -> tuple[bytes, bytes, bytes, bytes, bytes]:
    width = 128
    height = 96
    rng = random.Random(seed)
    scanlines = bytearray()
    for _ in range(height):
        scanlines.append(0)
        scanlines.extend(rng.randbytes(width * 3))
    compressed = zlib.compress(bytes(scanlines), level=6)
    split = len(compressed) // 2
    first_payload = compressed[:split]
    second_payload = compressed[split:]
    if not first_payload or not second_payload:
        raise ValueError("Compressed PNG stream was too short to split")

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    prefix = PNG_SIGNATURE + _chunk(b"IHDR", ihdr)
    first_idat = _chunk(b"IDAT", first_payload)
    suffix = _chunk(b"IDAT", second_payload) + _chunk(b"IEND", b"")
    source_png = prefix + first_idat + suffix
    return prefix, first_idat, suffix, first_payload, source_png


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {ROOT}")
    IMAGE_DIR.mkdir(parents=True)
    SOURCE_DIR.mkdir(parents=True)
    rows: list[dict[str, object]] = []

    for sample_index in range(1, SAMPLE_COUNT + 1):
        prefix, first_idat, suffix, first_payload, source_png = _make_png_parts(1200 + sample_index)
        source_name = f"multi_idat_{sample_index:02d}.png"
        (SOURCE_DIR / source_name).write_bytes(source_png)
        source_hash = hashlib.sha256(source_png).hexdigest()

        for scenario, gap_bytes, gap_location in SCENARIOS:
            if scenario == "inside_idat_gap_64":
                internal_split = len(first_payload) // 2
                first_chunk_header = struct.pack(">I", len(first_payload)) + b"IDAT"
                first_chunk_crc = struct.pack(
                    ">I", zlib.crc32(b"IDAT" + first_payload) & 0xFFFFFFFF
                )
                fragmented_first_idat = (
                    first_chunk_header
                    + first_payload[:internal_split]
                    + (b"\xA5" * gap_bytes)
                    + first_payload[internal_split:]
                    + first_chunk_crc
                )
                raw_png = prefix + fragmented_first_idat + suffix
            elif gap_bytes:
                raw_png = prefix + first_idat + (b"\xA5" * gap_bytes) + suffix
            else:
                raw_png = source_png

            image_name = f"{scenario}_sample_{sample_index:02d}.img"
            image_data = bytearray(IMAGE_OFFSET + len(raw_png) + TRAILING_BYTES)
            image_data[IMAGE_OFFSET : IMAGE_OFFSET + len(raw_png)] = raw_png
            (IMAGE_DIR / image_name).write_bytes(image_data)
            rows.append({
                "image_filename": image_name,
                "scenario": scenario,
                "sample_index": sample_index,
                "gap_bytes": gap_bytes,
                "gap_location": gap_location,
                "image_offset": IMAGE_OFFSET,
                "source_filename": source_name,
                "source_size_bytes": len(source_png),
                "embedded_size_bytes": len(raw_png),
                "first_idat_payload_bytes": len(first_payload),
                "source_sha256": source_hash,
            })

    with (ROOT / "ground_truth.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Independent PNG sources: {SAMPLE_COUNT}")
    print(f"Boundary scenarios:      {len(SCENARIOS)}")
    print(f"Raw images:              {len(rows)}")
    print(f"Images:                  {IMAGE_DIR}")
    print(f"Sources:                 {SOURCE_DIR}")
    print(f"Ground truth:            {ROOT / 'ground_truth.csv'}")


if __name__ == "__main__":
    main()
