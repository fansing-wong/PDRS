"""Create valid PNG controls and CRC-consistent, semantically invalid PNG decoys."""

from __future__ import annotations

import csv
import hashlib
import random
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "experiment_set_v3"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
DIMENSIONS = (8, 16, 24, 32, 48, 64, 80, 96, 112, 128)
SCENARIOS = ("valid_control", "crc_consistent_invalid_idat")


def _chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)


def _png(size: int, seed: int) -> bytes:
    rng = random.Random(seed)
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    scanlines = bytearray()
    for _ in range(size):
        scanlines.append(0)
        scanlines.extend(rng.randrange(256) for _ in range(size * 4))
    return signature + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(scanlines)) + _chunk(b"IEND", b"")


def _invalid_deflate_png(size: int) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    # Chunk CRCs are correct, but this payload is not a valid zlib stream.
    invalid_idat = b"PDRS-invalid-deflate-stream"
    return signature + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", invalid_idat) + _chunk(b"IEND", b"")


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {ROOT}\nMove it aside or use a fresh project copy.")
    IMAGE_DIR.mkdir(parents=True)
    SOURCE_DIR.mkdir(parents=True)
    rows: list[dict[str, object]] = []

    for sample_number, dimension in enumerate(DIMENSIONS, start=1):
        sample_id = f"png_{sample_number:02d}"
        valid_png = _png(dimension, 127000 + sample_number)
        (SOURCE_DIR / f"{sample_id}.png").write_bytes(valid_png)

        for scenario in SCENARIOS:
            rng = random.Random(127500 + sample_number * 10 + SCENARIOS.index(scenario))
            prefix = f"PDRS-{scenario}-{sample_id}\x00".encode("ascii")
            image = bytearray(prefix + bytes(rng.randrange(1, 256) for _ in range(41)))
            offset = len(image)
            target_present = scenario == "valid_control"
            if target_present:
                embedded = valid_png
                note = "valid PNG control with compressed scanlines and valid CRCs"
            else:
                embedded = _invalid_deflate_png(dimension)
                note = "valid chunk lengths/order/CRCs, but IDAT is not a valid zlib stream"
            image.extend(embedded)
            image.extend(bytes(rng.randrange(1, 256) for _ in range(31)))

            image_name = f"{scenario}_{sample_id}.img"
            (IMAGE_DIR / image_name).write_bytes(image)
            rows.append({
                "scenario": scenario,
                "sample_id": sample_id,
                "image_filename": image_name,
                "target_present": target_present,
                "expected_offset": offset,
                "dimension": f"{dimension}x{dimension}",
                "original_size_bytes": len(valid_png),
                "original_sha256": hashlib.sha256(valid_png).hexdigest(),
                "embedded_size_bytes": len(embedded),
                "scenario_note": note,
            })

    with (ROOT / "ground_truth.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Independent valid PNG controls: {len(DIMENSIONS)}")
    print(f"CRC-consistent invalid-IDAT decoys: {len(DIMENSIONS)}")
    print(f"Images:      {IMAGE_DIR}")
    print(f"Ground truth:{ROOT / 'ground_truth.csv'}")


if __name__ == "__main__":
    main()
