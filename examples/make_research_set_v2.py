"""Build a paired 10-sample PNG dataset for a stronger carving experiment."""

from __future__ import annotations

import csv
import random
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "experiment_set_v2"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
DIMENSIONS = (8, 16, 24, 32, 48, 64, 80, 96, 112, 128)
SCENARIOS = ("baseline", "truncated", "decoy_signature", "fragmented")


def _chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)


def _make_png(size: int, seed: int) -> bytes:
    rng = random.Random(seed)
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    rows = bytearray()
    for _ in range(size):
        rows.append(0)  # PNG filter type: None
        rows.extend(rng.randrange(256) for _ in range(size * 4))
    return signature + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(rows)) + _chunk(b"IEND", b"")


def _write_image(path: Path, image: bytes) -> None:
    path.write_bytes(image)


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {ROOT}\nMove it aside or use a fresh project copy.")
    IMAGE_DIR.mkdir(parents=True)
    SOURCE_DIR.mkdir(parents=True)
    rows: list[dict[str, object]] = []

    for sample_number, dimension in enumerate(DIMENSIONS, start=1):
        sample_id = f"png_{sample_number:02d}"
        original = _make_png(dimension, 93100 + sample_number)
        (SOURCE_DIR / f"{sample_id}.png").write_bytes(original)

        for scenario in SCENARIOS:
            rng = random.Random(881000 + sample_number * 10 + SCENARIOS.index(scenario))
            prefix = f"PDRS-{scenario}-{sample_id}\x00".encode("ascii")
            leading_filler = bytes(rng.randrange(1, 256) for _ in range(41))
            image = bytearray(prefix + leading_filler)
            offset = len(image)

            if scenario == "baseline":
                image.extend(original)
                included_bytes = len(original)
                target_present = True
                note = "intact contiguous PNG"
            elif scenario == "truncated":
                partial = original[:-12]  # remove PNG IEND chunk
                image.extend(partial)
                included_bytes = len(partial)
                target_present = True
                note = "PNG IEND chunk removed; 31 filler bytes follow"
            elif scenario == "decoy_signature":
                decoy = b"\x89PNG\r\n\x1a\n" + b"not a valid PNG body" + b"\x00\x00\x00\x00IEND\x00\x00\x00\x00"
                image.extend(decoy)
                included_bytes = 0
                target_present = False
                note = "fake PNG signature and IEND marker; no genuine file"
            else:
                split = len(original) // 2
                image.extend(original[:split])
                image.extend(bytes(rng.randrange(1, 256) for _ in range(512)))
                image.extend(original[split:])
                included_bytes = len(original)
                target_present = True
                note = "512 filler bytes inserted inside PNG"

            trailing_filler = bytes(rng.randrange(1, 256) for _ in range(31))
            image.extend(trailing_filler)
            image_path = IMAGE_DIR / f"{scenario}_{sample_id}.img"
            _write_image(image_path, bytes(image))

            rows.append({
                "scenario": scenario,
                "sample_id": sample_id,
                "image_filename": image_path.name,
                "target_present": target_present,
                "expected_offset": offset,
                "original_size_bytes": len(original),
                "included_source_bytes": included_bytes,
                "original_sha256": __import__("hashlib").sha256(original).hexdigest(),
                "image_size_bytes": len(image),
                "scenario_note": note,
            })

    with (ROOT / "ground_truth.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Independent PNG source files: {len(DIMENSIONS)}")
    print(f"Scenario images: {len(rows)} ({len(DIMENSIONS)} samples x {len(SCENARIOS)} scenarios)")
    print(f"Images:      {IMAGE_DIR}")
    print(f"Sources:     {SOURCE_DIR}")
    print(f"Ground truth:{ROOT / 'ground_truth.csv'}")


if __name__ == "__main__":
    main()
