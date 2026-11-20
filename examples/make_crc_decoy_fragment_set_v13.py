"""Create PNG gap images containing a CRC-valid but invalid-IDAT decoy."""

from __future__ import annotations

import csv
import hashlib
import struct
import zlib
from pathlib import Path


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v13"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
V11_SOURCE_DIR = EXAMPLES / "experiment_set_v11" / "sources"
SAMPLE_COUNT = 10
IMAGE_OFFSET = 512
TRAILING_BYTES = 512
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SCENARIOS = ("baseline", "simple_gap_64", "decoy_chunk_gap_64")


def _chunk(chunk_type: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {ROOT}")
    for sample_index in range(1, SAMPLE_COUNT + 1):
        source = V11_SOURCE_DIR / f"multi_idat_{sample_index:02d}.png"
        if not source.is_file():
            raise SystemExit(f"Required V11 source is missing: {source}")

    IMAGE_DIR.mkdir(parents=True)
    SOURCE_DIR.mkdir(parents=True)
    rows: list[dict[str, object]] = []

    for sample_index in range(1, SAMPLE_COUNT + 1):
        source_name = f"multi_idat_{sample_index:02d}.png"
        source_path = V11_SOURCE_DIR / source_name
        source_png = source_path.read_bytes()
        (SOURCE_DIR / source_name).write_bytes(source_png)
        source_hash = hashlib.sha256(source_png).hexdigest()

        ihdr_end = len(PNG_SIGNATURE) + 25
        first_idat_length = struct.unpack_from(">I", source_png, ihdr_end)[0]
        first_idat_end = ihdr_end + 12 + first_idat_length
        prefix = source_png[:first_idat_end]
        suffix = source_png[first_idat_end:]
        decoy_chunk = _chunk(b"IDAT", b"not-a-zlib")
        gap_prefix = b"\xA5" * 8
        gap_suffix = b"\xA5" * (64 - len(gap_prefix) - len(decoy_chunk))
        decoy_gap = gap_prefix + decoy_chunk + gap_suffix
        if len(decoy_gap) != 64:
            raise ValueError("CRC-valid decoy gap must be exactly 64 bytes")

        for scenario in SCENARIOS:
            if scenario == "baseline":
                raw_png = source_png
                gap = b""
            elif scenario == "simple_gap_64":
                gap = b"\xA5" * 64
                raw_png = prefix + gap + suffix
            else:
                gap = decoy_gap
                raw_png = prefix + gap + suffix

            image_name = f"{scenario}_sample_{sample_index:02d}.img"
            image_data = bytearray(IMAGE_OFFSET + len(raw_png) + TRAILING_BYTES)
            image_data[IMAGE_OFFSET : IMAGE_OFFSET + len(raw_png)] = raw_png
            (IMAGE_DIR / image_name).write_bytes(image_data)
            rows.append({
                "image_filename": image_name,
                "scenario": scenario,
                "sample_index": sample_index,
                "gap_bytes": len(gap),
                "decoy_chunk_bytes": len(decoy_chunk) if scenario == "decoy_chunk_gap_64" else 0,
                "image_offset": IMAGE_OFFSET,
                "source_filename": source_name,
                "source_size_bytes": len(source_png),
                "source_sha256": source_hash,
            })

    with (ROOT / "ground_truth.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Independent PNG sources: {SAMPLE_COUNT}")
    print(f"Scenarios:               {len(SCENARIOS)}")
    print(f"Raw images:              {len(rows)}")
    print(f"CRC-valid decoy chunk:   {len(decoy_chunk)} bytes inside a 64-byte gap")
    print(f"Images:                  {IMAGE_DIR}")
    print(f"Ground truth:            {ROOT / 'ground_truth.csv'}")


if __name__ == "__main__":
    main()
