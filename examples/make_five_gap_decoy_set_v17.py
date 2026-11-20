"""Create six-IDAT PNGs with five gaps and fifteen CRC-valid decoys."""

from __future__ import annotations

import csv
import hashlib
import struct
import zlib
from pathlib import Path


EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES / "experiment_set_v17"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
V13_SOURCE_DIR = EXAMPLES / "experiment_set_v13" / "sources"
SAMPLE_COUNT = 10
IMAGE_OFFSET = 512
TRAILING_BYTES = 512
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SCENARIOS = ("baseline", "five_gaps_simple", "five_gaps_with_decoys")
GAP_LENGTHS = (64, 128, 256, 512, 1024)
DECOYS_PER_GAP = (1, 2, 3, 4, 5)


def _chunk(chunk_type: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)


def _six_idat_png(source: bytes) -> tuple[bytes, list[bytes], bytes]:
    ihdr_end = len(PNG_SIGNATURE) + 25
    first_length = struct.unpack_from(">I", source, ihdr_end)[0]
    first_start = ihdr_end + 8
    first_end = ihdr_end + 12 + first_length
    second_length = struct.unpack_from(">I", source, first_end)[0]
    second_start = first_end + 8
    second_end = first_end + 12 + second_length
    compressed = source[first_start : first_start + first_length] + source[second_start : second_start + second_length]
    cuts = [(len(compressed) * index) // 6 for index in range(7)]
    idat_chunks = [
        _chunk(b"IDAT", compressed[cuts[index] : cuts[index + 1]])
        for index in range(6)
    ]
    if any(cuts[index] == cuts[index + 1] for index in range(6)):
        raise ValueError("Compressed PNG stream is too short to split into six IDAT chunks")
    prefix = PNG_SIGNATURE + source[len(PNG_SIGNATURE) : ihdr_end]
    return prefix, idat_chunks, source[second_end:]


def _gap(length: int, decoy_count: int, sample_index: int, gap_index: int) -> bytes:
    decoys = [
        _chunk(b"IDAT", f"BADZLIB-{sample_index}-{gap_index}-{number}".encode("ascii"))
        for number in range(1, decoy_count + 1)
    ]
    prefix = b"\xA5" * 8
    used = len(prefix) + sum(len(chunk) for chunk in decoys)
    if used >= length:
        raise ValueError(f"Decoys do not fit in the {length}-byte gap")
    return prefix + b"".join(decoys) + b"\xA5" * (length - used)


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
        png_prefix, idat_chunks, iend = _six_idat_png(original)
        source_png = png_prefix + b"".join(idat_chunks) + iend
        (SOURCE_DIR / source_name).write_bytes(source_png)
        source_hash = hashlib.sha256(source_png).hexdigest()

        for scenario in SCENARIOS:
            if scenario == "baseline":
                gaps = [b""] * 5
                decoy_counts = (0, 0, 0, 0, 0)
            elif scenario == "five_gaps_simple":
                gaps = [b"\xA5" * length for length in GAP_LENGTHS]
                decoy_counts = (0, 0, 0, 0, 0)
            else:
                gaps = [
                    _gap(length, count, sample_index, index)
                    for index, (length, count) in enumerate(zip(GAP_LENGTHS, DECOYS_PER_GAP), start=1)
                ]
                decoy_counts = DECOYS_PER_GAP

            raw_png = png_prefix + idat_chunks[0]
            for index in range(5):
                raw_png += gaps[index] + idat_chunks[index + 1]
            raw_png += iend
            image_name = f"{scenario}_sample_{sample_index:02d}.img"
            image_data = bytearray(IMAGE_OFFSET + len(raw_png) + TRAILING_BYTES)
            image_data[IMAGE_OFFSET : IMAGE_OFFSET + len(raw_png)] = raw_png
            (IMAGE_DIR / image_name).write_bytes(image_data)
            row: dict[str, object] = {
                "image_filename": image_name,
                "scenario": scenario,
                "sample_index": sample_index,
                "image_offset": IMAGE_OFFSET,
                "source_filename": source_name,
                "source_size_bytes": len(source_png),
                "source_sha256": source_hash,
            }
            row.update({f"gap{index + 1}_bytes": len(gaps[index]) for index in range(5)})
            row.update({f"decoys_gap{index + 1}": decoy_counts[index] for index in range(5)})
            rows.append(row)

    with (ROOT / "ground_truth.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Independent PNG sources: {SAMPLE_COUNT}")
    print(f"Scenarios:               {len(SCENARIOS)}")
    print(f"Raw images:              {len(rows)}")
    print("IDAT chunks per source:  6")
    print("Decoy condition:         1 + 2 + 3 + 4 + 5 CRC-valid decoys across five gaps")
    print(f"Images:                  {IMAGE_DIR}")
    print(f"Ground truth:            {ROOT / 'ground_truth.csv'}")


if __name__ == "__main__":
    main()
