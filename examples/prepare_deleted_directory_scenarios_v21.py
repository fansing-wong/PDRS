"""Prepare reuse, cyclic-chain, and bad-cluster synthetic controls for v0.21."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

from prepare_deleted_directory_scenarios_v19 import (
    DELETED_DIRECTORY_CLUSTER,
    _append_ground_truth,
    _cluster_geometry,
    _cluster_offset,
)


FAT32_EOC = 0x0FFFFFFF
FAT32_BAD_CLUSTER = 0x0FFFFFF7
SECOND_DELETED_DIRECTORY_CLUSTER = 42
SECOND_REUSE_DECOY_CLUSTER = 41
DELETED_DIRECTORY_FILE_CLUSTER = 40
SECOND_DIRECTORY_CLUSTER = 42
SCENARIOS = ("multiple_reuse", "cyclic_chain", "bad_cluster_link")


def _fat_value(handle, fat_start: int, cluster: int) -> int:
    handle.seek(fat_start + cluster * 4)
    return struct.unpack("<I", handle.read(4))[0] & 0x0FFFFFFF


def _short_entry(
    name: bytes,
    extension: bytes,
    *,
    attributes: int,
    first_cluster: int,
    size: int,
    deleted: bool = False,
) -> bytes:
    if len(name) != 8 or len(extension) != 3:
        raise ValueError("FAT32 short names must use exactly 8 base-name and 3 extension bytes.")
    entry = bytearray(32)
    entry[:8] = name
    entry[8:11] = extension
    entry[11] = attributes
    struct.pack_into("<H", entry, 26, first_cluster)
    struct.pack_into("<I", entry, 28, size)
    if deleted:
        entry[0] = 0xE5
    return bytes(entry)


def _first_free_root_slots(handle, root_offset: int, cluster_size: int, count: int) -> list[int]:
    slots: list[int] = []
    for offset in range(root_offset, root_offset + cluster_size, 32):
        handle.seek(offset)
        if handle.read(1) == b"\x00":
            slots.append(offset)
            if len(slots) == count:
                return slots
    raise SystemExit("The synthetic root directory does not have enough free slots for this control.")


def _prepare_multiple_reuse(image: Path, source_dir: Path, truth: Path) -> None:
    hidden_source = source_dir / "deleted_directory_control.txt"
    if not hidden_source.is_file():
        raise SystemExit(f"Missing v17 deleted-directory source: {hidden_source}")
    output_sources = (
        source_dir / "active_cluster_30.bin",
        source_dir / "active_cluster_42.bin",
        source_dir / "cluster_reuse_secondary_decoy.bin",
    )
    existing_source = next((path for path in output_sources if path.exists()), None)
    if existing_source is not None:
        raise SystemExit(f"Refusing to overwrite an existing scenario source: {existing_source}")
    first_decoy = hidden_source.read_bytes()
    second_decoy = b"Second synthetic file decoy inside a reused directory cluster.\r\n"
    data_30 = _short_entry(
        b"DECOY   ", b"BIN", attributes=0x20,
        first_cluster=DELETED_DIRECTORY_FILE_CLUSTER,
        size=len(first_decoy), deleted=True,
    ) + b"\0" * 32
    data_42 = _short_entry(
        b"DECOY   ", b"BIN", attributes=0x20,
        first_cluster=SECOND_REUSE_DECOY_CLUSTER,
        size=len(second_decoy), deleted=True,
    ) + b"\0" * 32
    if len(data_30) > 512 or len(data_42) > 512:
        raise SystemExit("The multiple-reuse controls exceed the smallest supported cluster size.")
    _, fat_start, _, data_start, cluster_size, _, _ = _cluster_geometry(image)
    if cluster_size < max(len(data_30), len(data_42)):
        raise SystemExit("The cluster size is too small for the synthetic active-file payloads.")
    root_offset = _cluster_offset(data_start, cluster_size, 2)
    first_dir_offset = _cluster_offset(data_start, cluster_size, DELETED_DIRECTORY_CLUSTER)
    second_dir_offset = _cluster_offset(data_start, cluster_size, SECOND_DELETED_DIRECTORY_CLUSTER)
    second_decoy_offset = _cluster_offset(data_start, cluster_size, SECOND_REUSE_DECOY_CLUSTER)
    active_source_30 = source_dir / "active_cluster_30.bin"
    active_source_42 = source_dir / "active_cluster_42.bin"
    secondary_source = source_dir / "cluster_reuse_secondary_decoy.bin"
    with image.open("r+b") as handle:
        if _fat_value(handle, fat_start, DELETED_DIRECTORY_CLUSTER) != 0:
            raise SystemExit("Expected the first deleted-directory FAT entry to be free.")
        if _fat_value(handle, fat_start, SECOND_DELETED_DIRECTORY_CLUSTER) != 0:
            raise SystemExit("Expected the second deleted-directory FAT entry to be free.")
        handle.seek(first_dir_offset)
        original_first_entry = handle.read(32)
        original_cluster = struct.unpack_from("<H", original_first_entry, 26)[0]
        if original_first_entry[0] != 0xE5 or original_cluster != DELETED_DIRECTORY_FILE_CLUSTER:
            raise SystemExit("The v17 first deleted directory does not match its expected fixture entry.")

        slots = _first_free_root_slots(handle, root_offset, cluster_size, 3)
        new_deleted_directory = _short_entry(
            b"REUSE2  ", b"   ", attributes=0x10,
            first_cluster=SECOND_DELETED_DIRECTORY_CLUSTER,
            size=0, deleted=True,
        )
        active_30 = _short_entry(
            b"OWNCL030", b"BIN", attributes=0x20,
            first_cluster=DELETED_DIRECTORY_CLUSTER,
            size=len(data_30),
        )
        active_42 = _short_entry(
            b"OWNCL042", b"BIN", attributes=0x20,
            first_cluster=SECOND_DELETED_DIRECTORY_CLUSTER,
            size=len(data_42),
        )
        for offset, entry in zip(slots, (new_deleted_directory, active_30, active_42), strict=True):
            handle.seek(offset)
            handle.write(entry)

        # These active-file payloads deliberately resemble deleted directory entries.
        handle.seek(first_dir_offset)
        handle.write(data_30)
        handle.seek(second_dir_offset)
        handle.write(data_42)
        handle.seek(second_decoy_offset)
        handle.write(second_decoy)
        handle.seek(fat_start + DELETED_DIRECTORY_CLUSTER * 4)
        handle.write(struct.pack("<I", FAT32_EOC))
        handle.seek(fat_start + SECOND_DELETED_DIRECTORY_CLUSTER * 4)
        handle.write(struct.pack("<I", FAT32_EOC))

    active_source_30.write_bytes(data_30)
    active_source_42.write_bytes(data_42)
    secondary_source.write_bytes(second_decoy)
    for source, expected_offset, payload in (
        (active_source_30.name, first_dir_offset, data_30),
        (active_source_42.name, second_dir_offset, data_42),
        (secondary_source.name, second_decoy_offset, second_decoy),
    ):
        _append_ground_truth(
            truth,
            source_filename=source,
            target_present=False,
            expected_offset=expected_offset,
            payload=payload,
        )
    print("Prepared two deleted directories whose clusters are occupied by two active files.")
    print("Each active-file payload contains a directory-entry decoy that must not be recovered.")


def _prepare_invalid_chain(image: Path, scenario: str) -> None:
    _, fat_start, _, _, _, _, _ = _cluster_geometry(image)
    with image.open("r+b") as handle:
        first_link = _fat_value(handle, fat_start, DELETED_DIRECTORY_CLUSTER)
        tail_link = _fat_value(handle, fat_start, SECOND_DIRECTORY_CLUSTER)
        if first_link != 0 or tail_link != 0:
            raise SystemExit("Expected free synthetic directory clusters; refusing to replace existing FAT links.")
        handle.seek(fat_start + DELETED_DIRECTORY_CLUSTER * 4)
        if scenario == "cyclic_chain":
            handle.write(struct.pack("<I", SECOND_DIRECTORY_CLUSTER))
            handle.seek(fat_start + SECOND_DIRECTORY_CLUSTER * 4)
            handle.write(struct.pack("<I", DELETED_DIRECTORY_CLUSTER))
        else:
            handle.write(struct.pack("<I", FAT32_BAD_CLUSTER))
    if scenario == "cyclic_chain":
        print("Prepared a deleted directory with a two-cluster cyclic FAT chain.")
    else:
        print("Prepared a deleted directory whose FAT link points to the bad-cluster marker.")


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
        raise SystemExit("Generate an isolated v17 synthetic demo before preparing this v21 scenario.")
    if args.scenario == "multiple_reuse":
        _prepare_multiple_reuse(image, source_dir, truth)
    else:
        _prepare_invalid_chain(image, args.scenario)


if __name__ == "__main__":
    main()
