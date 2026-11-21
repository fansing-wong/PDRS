"""Prepare partial-chain and overwritten-LFN synthetic FAT32 scenarios for v0.20."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

from prepare_deleted_directory_scenarios_v19 import (
    DELETED_DIRECTORY_CLUSTER,
    LONG_NAME,
    LONG_NAME_FILE_CLUSTER,
    LONG_SHORT_NAME,
    SECOND_DIRECTORY_CLUSTER,
    _cluster_geometry,
    _cluster_offset,
    _deleted_lfn_entries,
)


FAT32_EOC = 0x0FFFFFFF
DELETED_DIRECTORY_FILE_CLUSTER = 40
SCENARIOS = ("partial_chain", "lfn_slot_overwritten")


def _fat_value(handle, fat_start: int, cluster: int) -> int:
    handle.seek(fat_start + cluster * 4)
    return struct.unpack("<I", handle.read(4))[0] & 0x0FFFFFFF


def _prepare_partial_chain(image: Path) -> None:
    _, fat_start, _, _, _, _, _ = _cluster_geometry(image)
    with image.open("r+b") as handle:
        first_link = _fat_value(handle, fat_start, DELETED_DIRECTORY_CLUSTER)
        tail_link = _fat_value(handle, fat_start, SECOND_DIRECTORY_CLUSTER)
        if first_link != 0 or tail_link != 0:
            raise SystemExit("Expected free synthetic directory clusters; refusing to replace existing FAT links.")
        handle.seek(fat_start + DELETED_DIRECTORY_CLUSTER * 4)
        handle.write(struct.pack("<I", SECOND_DIRECTORY_CLUSTER))
        # The second cluster remains free: this deliberately makes the chain incomplete.
    print(
        "Prepared a deleted directory with a readable first cluster and a free tail link; "
        "the scanner should skip the entire directory."
    )


def _prepare_overwritten_lfn(image: Path, source_dir: Path) -> None:
    source = source_dir / "deleted_directory_control.txt"
    if not source.is_file():
        raise SystemExit(f"Missing v17 deleted-directory source file: {source}")
    payload = source.read_bytes()
    _, fat_start, _, data_start, cluster_size, _, image_size = _cluster_geometry(image)
    if cluster_size < 4 * 32:
        raise SystemExit("The synthetic directory cluster cannot hold the overwritten-LFN fixture.")
    directory_offset = _cluster_offset(data_start, cluster_size, DELETED_DIRECTORY_CLUSTER)
    data_offset = _cluster_offset(data_start, cluster_size, DELETED_DIRECTORY_FILE_CLUSTER)
    if data_offset + len(payload) > image_size:
        raise SystemExit("The deleted-file payload extends outside the synthetic image.")
    lfn_entries = _deleted_lfn_entries(LONG_NAME, LONG_SHORT_NAME)
    if len(lfn_entries) != 3:
        raise SystemExit("The v0.20 overwritten-LFN fixture expects exactly three deleted LFN slots.")

    with image.open("r+b") as handle:
        first_link = _fat_value(handle, fat_start, DELETED_DIRECTORY_CLUSTER)
        tail_link = _fat_value(handle, fat_start, SECOND_DIRECTORY_CLUSTER)
        if first_link != 0 or tail_link != 0:
            raise SystemExit("Expected free synthetic directory clusters; refusing to replace existing FAT links.")

        handle.seek(directory_offset)
        original_entry = bytearray(handle.read(32))
        original_cluster = (
            (struct.unpack_from("<H", original_entry, 20)[0] & 0x0FFF) << 16
        ) | struct.unpack_from("<H", original_entry, 26)[0]
        original_size = struct.unpack_from("<I", original_entry, 28)[0]
        if original_entry[0] != 0xE5 or original_entry[11] & 0x18:
            raise SystemExit("Expected the v17 deleted regular-file entry at the start of its directory.")
        if original_cluster != DELETED_DIRECTORY_FILE_CLUSTER or original_size != len(payload):
            raise SystemExit("The v17 deleted-directory entry does not match its source payload.")
        handle.seek(data_offset)
        if handle.read(len(payload)) != payload:
            raise SystemExit("The synthetic image payload does not match its source file.")

        overwritten_entry = bytearray(32)
        overwritten_entry[:8] = b"OVERWRTN"
        overwritten_entry[8:11] = b"TXT"
        overwritten_entry[11] = 0x20
        # A zero-length active entry interrupts the deleted LFN run without owning data clusters.
        handle.seek(directory_offset)
        handle.write(lfn_entries[0])
        handle.write(overwritten_entry)
        handle.write(lfn_entries[2])
        handle.write(original_entry)

        handle.seek(fat_start + DELETED_DIRECTORY_CLUSTER * 4)
        handle.write(struct.pack("<I", FAT32_EOC))

    print(f"Prepared a deleted entry with one overwritten LFN slot; target name: {LONG_NAME}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-dir", type=Path, required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    args = parser.parse_args()
    root = args.demo_dir.expanduser().resolve()
    image = root / "images" / "fat32_deleted_root.img"
    source_dir = root / "sources"
    truth = root / "ground_truth.csv"
    if not image.is_file() or not source_dir.is_dir() or not truth.is_file():
        raise SystemExit("Generate an isolated v17 synthetic demo before preparing this v20 scenario.")
    if args.scenario == "partial_chain":
        _prepare_partial_chain(image)
    else:
        _prepare_overwritten_lfn(image, source_dir)


if __name__ == "__main__":
    main()
