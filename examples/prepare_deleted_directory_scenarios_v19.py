"""Prepare bounded synthetic FAT32 deleted-directory edge cases for v0.19."""
from __future__ import annotations

import argparse
import csv
import hashlib
import struct
from pathlib import Path

SECTOR_SIZE = 512
DELETED_DIRECTORY_CLUSTER = 30
SECOND_DIRECTORY_CLUSTER = 42
LONG_NAME_FILE_CLUSTER = 43
FAT32_EOC = 0x0FFFFFFF
LONG_NAME = "Deleted report from cluster chain.txt"
LONG_SHORT_NAME = b"LONGNA~1TXT"


def _cluster_geometry(image_path: Path) -> tuple[int, int, int, int, int, int, int]:
    image_size = image_path.stat().st_size
    with image_path.open("rb") as handle:
        mbr = handle.read(SECTOR_SIZE)
        if len(mbr) != SECTOR_SIZE or mbr[510:512] != b"\x55\xaa":
            raise SystemExit("Refusing to prepare an image without the synthetic MBR marker.")
        partition_lba = struct.unpack_from("<I", mbr, 454)[0]
        partition_sectors = struct.unpack_from("<I", mbr, 458)[0]
        volume_offset = partition_lba * SECTOR_SIZE
        handle.seek(volume_offset)
        boot = handle.read(SECTOR_SIZE)
    if len(boot) != SECTOR_SIZE or boot[71:82] != b"PDRS DEMO  " or boot[510:512] != b"\x55\xaa":
        raise SystemExit("Refusing to prepare an image without the PDRS synthetic FAT32 marker.")

    bytes_per_sector = struct.unpack_from("<H", boot, 11)[0]
    sectors_per_cluster = boot[13]
    reserved_sectors = struct.unpack_from("<H", boot, 14)[0]
    fat_count = boot[16]
    sectors_per_fat = struct.unpack_from("<I", boot, 36)[0]
    total_sectors = struct.unpack_from("<I", boot, 32)[0]
    if bytes_per_sector != SECTOR_SIZE or sectors_per_cluster not in (1, 2, 4):
        raise SystemExit("Unsupported synthetic FAT32 geometry; expected 512-byte sectors and 1, 2, or 4 sectors per cluster.")
    if reserved_sectors == 0 or fat_count != 1 or sectors_per_fat == 0:
        raise SystemExit("Unexpected synthetic FAT32 table geometry; refusing to edit the image.")
    if partition_sectors == 0 or volume_offset + partition_sectors * SECTOR_SIZE > image_size:
        raise SystemExit("The synthetic partition extends outside the image file.")

    fat_start = volume_offset + reserved_sectors * bytes_per_sector
    fat_bytes = sectors_per_fat * bytes_per_sector
    data_start = fat_start + fat_count * fat_bytes
    cluster_size = bytes_per_sector * sectors_per_cluster
    data_sectors = total_sectors - reserved_sectors - fat_count * sectors_per_fat
    cluster_count = data_sectors // sectors_per_cluster
    required_last = max(SECOND_DIRECTORY_CLUSTER, LONG_NAME_FILE_CLUSTER)
    if required_last >= cluster_count + 2:
        raise SystemExit("Synthetic image is too small for the v0.19 fixture clusters.")
    if data_start + (required_last - 2) * cluster_size + cluster_size > image_size:
        raise SystemExit("Synthetic fixture cluster lies outside the image file.")
    if any(cluster * 4 + 4 > fat_bytes for cluster in (
        DELETED_DIRECTORY_CLUSTER,
        SECOND_DIRECTORY_CLUSTER,
        LONG_NAME_FILE_CLUSTER,
    )):
        raise SystemExit("Fixture FAT entries lie outside the first FAT table.")
    return volume_offset, fat_start, fat_bytes, data_start, cluster_size, cluster_count, image_size


def _cluster_offset(data_start: int, cluster_size: int, cluster: int) -> int:
    return data_start + (cluster - 2) * cluster_size


def _lfn_checksum(short_name: bytes) -> int:
    checksum = 0
    for byte in short_name:
        checksum = (((checksum & 1) << 7) | (checksum >> 1)) + byte
        checksum &= 0xFF
    return checksum


def _deleted_lfn_entries(long_name: str, short_name: bytes) -> list[bytes]:
    encoded = long_name.encode("utf-16le")
    units = list(struct.unpack(f"<{len(encoded) // 2}H", encoded))
    chunks = [units[index : index + 13] for index in range(0, len(units), 13)]
    checksum = _lfn_checksum(short_name)
    entries: list[bytes] = []
    for sequence in range(len(chunks), 0, -1):
        part = list(chunks[sequence - 1])
        if sequence == len(chunks) and len(part) < 13:
            part.append(0)
            part.extend([0xFFFF] * (13 - len(part)))
        part.extend([0xFFFF] * (13 - len(part)))
        raw_units = struct.pack("<13H", *part)
        entry = bytearray(32)
        entry[0] = sequence | (0x40 if sequence == len(chunks) else 0)
        entry[11] = 0x0F
        entry[13] = checksum
        entry[1:11] = raw_units[:10]
        entry[14:26] = raw_units[10:22]
        entry[28:32] = raw_units[22:26]
        entry[0] = 0xE5
        entries.append(bytes(entry))
    return entries


def _append_ground_truth(
    path: Path,
    *,
    source_filename: str,
    target_present: bool,
    expected_offset: int,
    payload: bytes,
) -> None:
    with path.open("r", newline="", encoding="utf-8") as handle:
        fieldnames = csv.DictReader(handle).fieldnames
    if not fieldnames:
        raise SystemExit("Ground Truth CSV is missing its header.")
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writerow({
            "image_filename": "fat32_deleted_root.img",
            "source_filename": source_filename,
            "target_present": str(target_present).lower(),
            "expected_offset": expected_offset,
            "expected_sha256": hashlib.sha256(payload).hexdigest(),
        })


def _prepare_multicluster(image_path: Path, source_dir: Path, truth_path: Path) -> None:
    source = source_dir / "deleted_directory_long_name.txt"
    if source.exists():
        raise SystemExit(f"Refusing to overwrite existing fixture source: {source}")
    payload = (
        b"This report is stored after the deleted directory crosses into its second cluster.\r\n"
        b"Its long-name slots begin at the end of the first cluster.\r\n"
    )
    lfn_entries = _deleted_lfn_entries(LONG_NAME, LONG_SHORT_NAME)
    _, fat_start, fat_bytes, data_start, cluster_size, _, image_size = _cluster_geometry(image_path)
    if len(lfn_entries) != 3 or cluster_size // 32 <= len(lfn_entries) + 1:
        raise SystemExit("The synthetic directory cluster cannot hold the boundary-spanning LFN fixture.")
    directory_offset = _cluster_offset(data_start, cluster_size, DELETED_DIRECTORY_CLUSTER)
    second_directory_offset = _cluster_offset(data_start, cluster_size, SECOND_DIRECTORY_CLUSTER)
    payload_offset = _cluster_offset(data_start, cluster_size, LONG_NAME_FILE_CLUSTER)
    if payload_offset + len(payload) > image_size:
        raise SystemExit("The long-name sample data would extend beyond the synthetic image.")

    with image_path.open("r+b") as handle:
        first_entry = bytearray(32)
        handle.seek(directory_offset)
        first_entry[:] = handle.read(32)
        if first_entry[0] != 0xE5 or first_entry[11] & 0x18:
            raise SystemExit("Expected the v17 deleted regular file at the start of the deleted directory.")

        handle.seek(fat_start + DELETED_DIRECTORY_CLUSTER * 4)
        current_first = struct.unpack("<I", handle.read(4))[0] & 0x0FFFFFFF
        handle.seek(fat_start + SECOND_DIRECTORY_CLUSTER * 4)
        current_tail = struct.unpack("<I", handle.read(4))[0] & 0x0FFFFFFF
        handle.seek(fat_start + LONG_NAME_FILE_CLUSTER * 4)
        current_file = struct.unpack("<I", handle.read(4))[0] & 0x0FFFFFFF
        if current_first != 0 or current_tail != 0 or current_file != 0:
            raise SystemExit("Expected unallocated fixture clusters; refusing to replace existing FAT links.")

        filler = bytearray(32)
        filler[0] = 0xE5
        filler[1:8] = b"FILLER "
        filler[11] = 0x10
        last_slots_start = cluster_size // 32 - len(lfn_entries)
        for slot_index in range(1, last_slots_start):
            handle.seek(directory_offset + slot_index * 32)
            handle.write(filler)
        for relative_slot, entry in enumerate(lfn_entries):
            handle.seek(directory_offset + (last_slots_start + relative_slot) * 32)
            handle.write(entry)

        deleted_file = bytearray(32)
        deleted_file[0] = 0xE5
        deleted_file[1:11] = LONG_SHORT_NAME[1:]
        deleted_file[11] = 0x20
        struct.pack_into("<H", deleted_file, 26, LONG_NAME_FILE_CLUSTER)
        struct.pack_into("<I", deleted_file, 28, len(payload))
        handle.seek(second_directory_offset)
        handle.write(deleted_file)
        handle.seek(payload_offset)
        handle.write(payload)

        handle.seek(fat_start + DELETED_DIRECTORY_CLUSTER * 4)
        handle.write(struct.pack("<I", SECOND_DIRECTORY_CLUSTER))
        handle.seek(fat_start + SECOND_DIRECTORY_CLUSTER * 4)
        handle.write(struct.pack("<I", FAT32_EOC))

    source.write_bytes(payload)
    _append_ground_truth(
        truth_path,
        source_filename=source.name,
        target_present=True,
        expected_offset=payload_offset,
        payload=payload,
    )
    print(f"Prepared two-cluster deleted directory with boundary-spanning LFN: {LONG_NAME}")
    print(f"Second directory cluster: {SECOND_DIRECTORY_CLUSTER}; short entry offset: {second_directory_offset}")


def _prepare_cluster_reuse(image_path: Path, source_dir: Path, truth_path: Path) -> None:
    source = source_dir / "cluster_reuse_active_control.bin"
    if source.exists():
        raise SystemExit(f"Refusing to overwrite existing fixture source: {source}")
    payload = b"This active file reuses the deleted directory's tail cluster.\r\n"
    _, fat_start, fat_bytes, data_start, cluster_size, _, image_size = _cluster_geometry(image_path)
    root_cluster = 2
    root_offset = _cluster_offset(data_start, cluster_size, root_cluster)
    reused_offset = _cluster_offset(data_start, cluster_size, SECOND_DIRECTORY_CLUSTER)
    if reused_offset + len(payload) > image_size:
        raise SystemExit("The cluster-reuse sample would extend beyond the synthetic image.")

    with image_path.open("r+b") as handle:
        handle.seek(fat_start + DELETED_DIRECTORY_CLUSTER * 4)
        current_first = struct.unpack("<I", handle.read(4))[0] & 0x0FFFFFFF
        handle.seek(fat_start + SECOND_DIRECTORY_CLUSTER * 4)
        current_tail = struct.unpack("<I", handle.read(4))[0] & 0x0FFFFFFF
        if current_first != 0 or current_tail != 0:
            raise SystemExit("Expected unallocated fixture clusters; refusing to replace existing FAT links.")

        root_slot = None
        for offset in range(root_offset, root_offset + cluster_size, 32):
            handle.seek(offset)
            if handle.read(1) == b"\x00":
                root_slot = offset
                break
        if root_slot is None:
            raise SystemExit("No free root-directory entry remains for the cluster-reuse control.")

        active_file = bytearray(32)
        active_file[:8] = b"REUSE001"
        active_file[8:11] = b"BIN"
        active_file[11] = 0x20
        struct.pack_into("<H", active_file, 26, SECOND_DIRECTORY_CLUSTER)
        struct.pack_into("<I", active_file, 28, len(payload))
        handle.seek(root_slot)
        handle.write(active_file)
        handle.seek(reused_offset)
        handle.write(payload)
        handle.seek(fat_start + DELETED_DIRECTORY_CLUSTER * 4)
        handle.write(struct.pack("<I", SECOND_DIRECTORY_CLUSTER))
        handle.seek(fat_start + SECOND_DIRECTORY_CLUSTER * 4)
        handle.write(struct.pack("<I", FAT32_EOC))

    source.write_bytes(payload)
    _append_ground_truth(
        truth_path,
        source_filename=source.name,
        target_present=False,
        expected_offset=reused_offset,
        payload=payload,
    )
    print("Prepared a deleted-directory chain whose tail cluster is allocated to an active file.")
    print(f"Reused cluster: {SECOND_DIRECTORY_CLUSTER}; active data offset: {reused_offset}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-dir", type=Path, required=True)
    parser.add_argument("--scenario", choices=("multi_cluster", "cluster_reuse"), required=True)
    args = parser.parse_args()
    root = args.demo_dir.expanduser().resolve()
    image = root / "images" / "fat32_deleted_root.img"
    sources = root / "sources"
    truth = root / "ground_truth.csv"
    if not image.is_file() or not sources.is_dir() or not truth.is_file():
        raise SystemExit("Generate an isolated v17 synthetic demo before preparing this v19 scenario.")
    if args.scenario == "multi_cluster":
        _prepare_multicluster(image, sources, truth)
    else:
        _prepare_cluster_reuse(image, sources, truth)


if __name__ == "__main__":
    main()
