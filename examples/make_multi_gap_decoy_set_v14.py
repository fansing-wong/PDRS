"""Create three-IDAT PNGs with two gaps and optional CRC-valid decoys."""

from __future__ import annotations

import csv
import hashlib
import struct
import zlib
from pathlib import Path


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v14"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
V13_SOURCE_DIR = EXAMPLES / "experiment_set_v13" / "sources"
SAMPLE_COUNT = 10
IMAGE_OFFSET = 512
TRAILING_BYTES = 512
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SCENARIOS = ("baseline", "two_gaps_simple", "two_gaps_with_decoys")


def _chunk(chunk_type: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)


def _three_idat_png(source: bytes) -> tuple[bytes, bytes, bytes, bytes]:
    ihdr_end = len(PNG_SIGNATURE) + 25
    first_length = struct.unpack_from(">I", source, ihdr_end)[0]
    first_start = ihdr_end + 8
    first_end = ihdr_end + 12 + first_length
    second_length = struct.unpack_from(">I", source, first_end)[0]
    second_start = first_end + 8
    second_end = first_end + 12 + second_length
    ihdr = source[len(PNG_SIGNATURE) : ihdr_end]
    first_payload = source[first_start : first_start + first_length]
    second_payload = source[second_start : second_start + second_length]
    compressed = first_payload + second_payload
    split1 = len(compressed) // 3
    split2 = (2 * len(compressed)) // 3
    prefix = PNG_SIGNATURE + ihdr
    idat1 = _chunk(b"IDAT", compressed[:split1])
    idat2 = _chunk(b"IDAT", compressed[split1:split2])
    idat3 = _chunk(b"IDAT", compressed[split2:])
    iend = source[second_end:]
    return prefix, idat1, idat2, idat3 + iend


def _gap(length: int, decoy_count: int, sample_index: int, gap_index: int) -> bytes:
    decoys = [
        _chunk(b"IDAT", f"not-zlib-{sample_index}-{gap_index}-{number}".encode("ascii"))
        for number in range(1, decoy_count + 1)
    ]
    padding_before = b"\xA5" * 8
    used = len(padding_before) + sum(len(chunk) for chunk in decoys)
    if used >= length:
        raise ValueError("Decoy chunks do not fit inside the selected gap")
    padding_after = b"\xA5" * (length - used)
    result = padding_before + b"".join(decoys) + padding_after
    if len(result) != length:
        raise ValueError("Gap length did not match its requested size")
    return result


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {ROOT}")
    for sample_index in range(1, SAMPLE_COUNT + 1):
        if not (V13_SOURCE_DIR / f"multi_idat_{sample_index:02d}.png").is_file():
            raise SystemExit("V13 source set is missing. Run the V13 dataset generator first.")

    IMAGE_DIR.mkdir(parents=True)
    SOURCE_DIR.mkdir(parents=True)
    rows: list[dict[str, object]] = []

    for sample_index in range(1, SAMPLE_COUNT + 1):
        source_name = f"multi_idat_{sample_index:02d}.png"
        original = (V13_SOURCE_DIR / source_name).read_bytes()
        prefix, idat1, idat2, idat3_and_iend = _three_idat_png(original)
        source_png = prefix + idat1 + idat2 + idat3_and_iend
        (SOURCE_DIR / source_name).write_bytes(source_png)
        source_hash = hashlib.sha256(source_png).hexdigest()

        for scenario in SCENARIOS:
            if scenario == "baseline":
                gap1 = b""
                gap2 = b""
                decoys_gap1 = 0
                decoys_gap2 = 0
            elif scenario == "two_gaps_simple":
                gap1 = b"\xA5" * 64
                gap2 = b"\xA5" * 128
                decoys_gap1 = 0
                decoys_gap2 = 0
            else:
                gap1 = _gap(64, 1, sample_index, 1)
                gap2 = _gap(128, 2, sample_index, 2)
                decoys_gap1 = 1
                decoys_gap2 = 2

            raw_png = prefix + idat1 + gap1 + idat2 + gap2 + idat3_and_iend
            image_name = f"{scenario}_sample_{sample_index:02d}.img"
            image_data = bytearray(IMAGE_OFFSET + len(raw_png) + TRAILING_BYTES)
            image_data[IMAGE_OFFSET : IMAGE_OFFSET + len(raw_png)] = raw_png
            (IMAGE_DIR / image_name).write_bytes(image_data)
            rows.append({
                "image_filename": image_name,
                "scenario": scenario,
                "sample_index": sample_index,
                "gap1_bytes": len(gap1),
                "gap2_bytes": len(gap2),
                "decoys_gap1": decoys_gap1,
                "decoys_gap2": decoys_gap2,
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
    print("IDAT chunks per source:  3")
    print("Decoy condition:         one and two CRC-valid decoys in separate gaps")
    print(f"Images:                  {IMAGE_DIR}")
    print(f"Ground truth:            {ROOT / 'ground_truth.csv'}")


if __name__ == "__main__":
    main()
