"""Create controlled synthetic scenarios for carving evaluation."""

from __future__ import annotations

import csv
import hashlib
import random
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "experiment_set"
IMAGE_DIR = ROOT / "images"


def _chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)


def _png() -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0)
    pixels = b"\x00" + b"\xff\x33\x66\xff" * 2 + b"\x00" + b"\x66\xcc\x99\xff" * 2
    return signature + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(pixels)) + _chunk(b"IEND", b"")


def _record(scenario: str, name: str, kind: str, offset: int, original: bytes, included: int, note: str) -> dict[str, object]:
    return {
        "scenario": scenario,
        "filename": name,
        "format": kind,
        "expected_offset": offset,
        "original_size_bytes": len(original),
        "included_bytes": included,
        "original_sha256": hashlib.sha256(original).hexdigest(),
        "scenario_note": note,
    }


def _write_image(name: str, data: bytes) -> None:
    (IMAGE_DIR / name).write_bytes(data)


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing experiment set: {ROOT}\nMove it aside or choose a fresh copy of the project.")
    IMAGE_DIR.mkdir(parents=True)
    png = _png()
    rng = random.Random(20261120)
    filler = lambda size: bytes(rng.randrange(1, 256) for _ in range(size))

    rows: list[dict[str, object]] = []

    # Baseline: one intact contiguous PNG.
    baseline = b"PDRS-BASELINE\x00" + filler(41)
    baseline_offset = len(baseline)
    baseline += png + filler(31)
    _write_image("baseline.img", baseline)
    rows.append(_record("baseline", "sample.png", "png", baseline_offset, png, len(png), "intact contiguous control"))

    # Truncation: remove the 12-byte IEND chunk.
    partial = png[:-12]
    truncated = b"PDRS-TRUNCATED\x00" + filler(41)
    truncated_offset = len(truncated)
    truncated += partial + filler(31)
    _write_image("truncated.img", truncated)
    rows.append(_record("truncated", "sample.png", "png", truncated_offset, png, len(partial), "IEND chunk removed"))

    # Decoy: plausible signature and end marker, but not a real PDF document.
    decoy = b"PDRS-DECOY\x00" + filler(41)
    decoy_offset = len(decoy)
    decoy += b"%PDF-1.4\nThis is deliberately not a real PDF.\n%%EOF\n" + filler(31)
    _write_image("decoy_signature.img", decoy)
    rows.append(_record("decoy_signature", "no genuine file", "none", decoy_offset, b"", 0, "signature-like text should produce a false positive"))

    # Fragmentation: split the PNG and insert unrelated bytes between its parts.
    split_at = len(png) // 2
    fragmented = b"PDRS-FRAGMENTED\x00" + filler(41)
    fragmented_offset = len(fragmented)
    fragmented += png[:split_at] + filler(512) + png[split_at:] + filler(31)
    _write_image("fragmented.img", fragmented)
    rows.append(_record("fragmented", "sample.png", "png", fragmented_offset, png, len(png), "512 filler bytes inserted inside the PNG"))

    with (ROOT / "ground_truth.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Scenario images: {IMAGE_DIR}")
    print(f"Ground truth:    {ROOT / 'ground_truth.csv'}")
    for filename in ("baseline.img", "truncated.img", "decoy_signature.img", "fragmented.img"):
        print(f" - {IMAGE_DIR / filename}")


if __name__ == "__main__":
    main()
