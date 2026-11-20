"""Generate synthetic FAT32 root, subdirectory, and deleted-directory controls."""
from __future__ import annotations

import argparse
import csv
import hashlib
import struct
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent / "fat32_deleted_demo_v15"
TOTAL_SECTORS = 70000
SECTOR_SIZE = 512
RESERVED_SECTORS = 32
SECTORS_PER_FAT = 550
DATA_START_SECTOR = RESERVED_SECTORS + SECTORS_PER_FAT
ROOT_CLUSTER = 2
FILE_CLUSTER = 10
SUBDIRECTORY_CLUSTER = 12
NESTED_FILE_CLUSTER = 20
DELETED_DIRECTORY_CLUSTER = 30
DECOY_FILE_CLUSTER = 40
FRAGMENT_FIRST_CLUSTER = 50
FRAGMENT_SECOND_CLUSTER = 53
CONTIGUOUS_DECOY_CLUSTER = 51
INTERRUPTED_FIRST_CLUSTER = 60
INTERRUPTED_DECOY_CLUSTER = 61


def cluster_offset(cluster: int) -> int:
    return SECTOR_SIZE + (DATA_START_SECTOR + cluster - 2) * SECTOR_SIZE


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
        entry[12] = 0
        entry[13] = checksum
        struct.pack_into("<H", entry, 26, 0)
        entry[1:11] = raw_units[:10]
        entry[14:26] = raw_units[10:22]
        entry[28:32] = raw_units[22:26]
        entry[0] = 0xE5
        entries.append(bytes(entry))
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ROOT)
    root = parser.parse_args().output_dir.expanduser().resolve()
    image_dir = root / "images"
    source_dir = root / "sources"
    if root.exists():
        raise SystemExit(f"Refusing to overwrite existing demo set: {root}")
    image_dir.mkdir(parents=True)
    source_dir.mkdir()
    root_source = source_dir / "deleted_root_sample.txt"
    nested_source = source_dir / "deleted_subdirectory_sample.txt"
    root_payload = (
        b"Synthetic FAT32 deleted-file sample for PDRS.\r\n"
        b"This entry lives in the root directory and its data is contiguous.\r\n"
    ) * 6
    root_short_name = b"ROOTSAMPTXT"
    nested_short_name = b"NESTSAMPTXT"
    nested_payload = (
        b"This deleted entry is in an active FAT32 subdirectory.\r\n"
        b"The original directory remains allocated; file data is contiguous.\r\n"
    ) * 10
    active_payload = b"This intact active file must not be extracted as deleted.\r\n" * 6
    hidden_payload = b"This deleted file is inside a deleted directory and must be ignored.\r\n"
    fragmented_payload = bytes((index * 37 + 11) % 256 for index in range(700))
    interrupted_payload = bytes((index * 19 + 7) % 256 for index in range(700))
    root_source.write_bytes(root_payload)
    nested_source.write_bytes(nested_payload)

    image_path = image_dir / "fat32_deleted_root.img"
    with image_path.open("wb") as handle:
        handle.truncate((TOTAL_SECTORS + 1) * SECTOR_SIZE)
    with image_path.open("r+b") as handle:
        mbr = bytearray(SECTOR_SIZE)
        partition_entry = 446
        mbr[partition_entry + 4] = 0x0C
        struct.pack_into("<II", mbr, partition_entry + 8, 1, TOTAL_SECTORS)
        mbr[510:512] = b"\x55\xaa"
        handle.seek(0)
        handle.write(mbr)

        boot = bytearray(SECTOR_SIZE)
        boot[3:11] = b"MSWIN4.1"
        struct.pack_into("<H", boot, 11, SECTOR_SIZE)
        boot[13] = 1
        struct.pack_into("<H", boot, 14, RESERVED_SECTORS)
        boot[16] = 1
        boot[21] = 0xF8
        struct.pack_into("<I", boot, 32, TOTAL_SECTORS)
        struct.pack_into("<I", boot, 36, SECTORS_PER_FAT)
        struct.pack_into("<I", boot, 44, ROOT_CLUSTER)
        struct.pack_into("<H", boot, 48, 1)
        struct.pack_into("<H", boot, 50, 6)
        struct.pack_into("<I", boot, 67, 0x50445253)
        boot[71:82] = b"PDRS DEMO  "
        boot[82:90] = b"FAT32   "
        boot[510:512] = b"\x55\xaa"
        handle.seek(SECTOR_SIZE)
        handle.write(boot)

        fat = bytearray(SECTORS_PER_FAT * SECTOR_SIZE)
        struct.pack_into("<I", fat, 0, 0x0FFFFFF8)
        struct.pack_into("<I", fat, 4, 0x0FFFFFFF)
        struct.pack_into("<I", fat, ROOT_CLUSTER * 4, 0x0FFFFFFF)
        struct.pack_into("<I", fat, (FILE_CLUSTER + 4) * 4, 0x0FFFFFFF)
        struct.pack_into("<I", fat, SUBDIRECTORY_CLUSTER * 4, 0x0FFFFFFF)
        nested_cluster_count = (len(nested_payload) + SECTOR_SIZE - 1) // SECTOR_SIZE
        for relative_cluster in range(nested_cluster_count - 1):
            struct.pack_into(
                "<I",
                fat,
                (NESTED_FILE_CLUSTER + relative_cluster) * 4,
                NESTED_FILE_CLUSTER + relative_cluster + 1,
            )
        struct.pack_into(
            "<I",
            fat,
            (NESTED_FILE_CLUSTER + nested_cluster_count - 1) * 4,
            0x0FFFFFFF,
        )
        struct.pack_into("<I", fat, FRAGMENT_FIRST_CLUSTER * 4, FRAGMENT_SECOND_CLUSTER)
        struct.pack_into("<I", fat, FRAGMENT_SECOND_CLUSTER * 4, 0x0FFFFFFF)
        struct.pack_into("<I", fat, INTERRUPTED_FIRST_CLUSTER * 4, 0x0FFFFFFF)
        # FILE_CLUSTER remains free, reproducing the common post-delete FAT state.
        handle.seek(SECTOR_SIZE + RESERVED_SECTORS * SECTOR_SIZE)
        handle.write(fat)

        deleted_entry = bytearray(32)
        deleted_entry[0] = 0xE5
        deleted_entry[1:8] = b"OOTSAMP"
        deleted_entry[8:11] = b"TXT"
        deleted_entry[11] = 0x20
        struct.pack_into("<H", deleted_entry, 26, FILE_CLUSTER)
        struct.pack_into("<I", deleted_entry, 28, len(root_payload))
        root_directory_offset = SECTOR_SIZE + DATA_START_SECTOR * SECTOR_SIZE
        handle.seek(root_directory_offset)
        for lfn_entry in _deleted_lfn_entries(root_source.name, root_short_name):
            handle.write(lfn_entry)
        handle.write(deleted_entry)

        # Include an intact directory entry to show that only deleted entries are extracted.
        active_entry = bytearray(32)
        active_entry[0:8] = b"ACTIVE  "
        active_entry[8:11] = b"TXT"
        active_entry[11] = 0x20
        struct.pack_into("<H", active_entry, 26, FILE_CLUSTER + 4)
        struct.pack_into("<I", active_entry, 28, len(active_payload))
        handle.write(active_entry)

        active_subdirectory = bytearray(32)
        active_subdirectory[:8] = b"SUBDIR  "
        active_subdirectory[11] = 0x10
        struct.pack_into("<H", active_subdirectory, 26, SUBDIRECTORY_CLUSTER)
        handle.write(active_subdirectory)

        deleted_directory = bytearray(32)
        deleted_directory[0] = 0xE5
        deleted_directory[1:8] = b"ELDIR  "
        deleted_directory[11] = 0x10
        struct.pack_into("<H", deleted_directory, 26, DELETED_DIRECTORY_CLUSTER)
        handle.write(deleted_directory)

        # This deleted file is deliberately fragmented: the surviving FAT link
        # points from cluster 50 to 53, while cluster 51 contains unrelated bytes.
        fragmented_entry = bytearray(32)
        fragmented_entry[0] = 0xE5
        fragmented_entry[1:8] = b"RAGMENT"
        fragmented_entry[8:11] = b"BIN"
        fragmented_entry[11] = 0x20
        struct.pack_into("<H", fragmented_entry, 26, FRAGMENT_FIRST_CLUSTER)
        struct.pack_into("<I", fragmented_entry, 28, len(fragmented_payload))
        handle.write(fragmented_entry)

        # This entry declares two clusters of data, but its surviving FAT chain
        # ends after the first one. The adjacent cluster is unrelated decoy data.
        interrupted_entry = bytearray(32)
        interrupted_entry[0] = 0xE5
        interrupted_entry[1:8] = b"NTRRUPT"
        interrupted_entry[8:11] = b"BIN"
        interrupted_entry[11] = 0x20
        struct.pack_into("<H", interrupted_entry, 26, INTERRUPTED_FIRST_CLUSTER)
        struct.pack_into("<I", interrupted_entry, 28, len(interrupted_payload))
        handle.write(interrupted_entry)

        nested_deleted_entry = bytearray(32)
        nested_deleted_entry[0] = 0xE5
        nested_deleted_entry[1:8] = b"ESTSAMP"
        nested_deleted_entry[8:11] = b"TXT"
        nested_deleted_entry[11] = 0x20
        struct.pack_into("<H", nested_deleted_entry, 26, NESTED_FILE_CLUSTER)
        struct.pack_into("<I", nested_deleted_entry, 28, len(nested_payload))
        handle.seek(cluster_offset(SUBDIRECTORY_CLUSTER))
        for lfn_entry in _deleted_lfn_entries(nested_source.name, nested_short_name):
            handle.write(lfn_entry)
        handle.write(nested_deleted_entry)

        dot_entry = bytearray(32)
        dot_entry[:11] = b".          "
        dot_entry[11] = 0x10
        struct.pack_into("<H", dot_entry, 26, SUBDIRECTORY_CLUSTER)
        dotdot_entry = bytearray(32)
        dotdot_entry[:11] = b"..         "
        dotdot_entry[11] = 0x10
        struct.pack_into("<H", dotdot_entry, 26, ROOT_CLUSTER)
        handle.write(dot_entry)
        handle.write(dotdot_entry)

        hidden_deleted_entry = bytearray(32)
        hidden_deleted_entry[0] = 0xE5
        hidden_deleted_entry[1:8] = b"IDDEN  "
        hidden_deleted_entry[8:11] = b"TXT"
        hidden_deleted_entry[11] = 0x20
        struct.pack_into("<H", hidden_deleted_entry, 26, DECOY_FILE_CLUSTER)
        struct.pack_into("<I", hidden_deleted_entry, 28, len(hidden_payload))
        handle.seek(cluster_offset(DELETED_DIRECTORY_CLUSTER))
        handle.write(hidden_deleted_entry)

        handle.seek(cluster_offset(FILE_CLUSTER))
        handle.write(root_payload)
        handle.seek(cluster_offset(FILE_CLUSTER + 4))
        handle.write(active_payload)
        handle.seek(cluster_offset(NESTED_FILE_CLUSTER))
        handle.write(nested_payload)
        handle.seek(cluster_offset(DECOY_FILE_CLUSTER))
        handle.write(hidden_payload)
        handle.seek(cluster_offset(FRAGMENT_FIRST_CLUSTER))
        handle.write(fragmented_payload[:SECTOR_SIZE])
        handle.seek(cluster_offset(FRAGMENT_SECOND_CLUSTER))
        handle.write(fragmented_payload[SECTOR_SIZE:])
        handle.seek(cluster_offset(CONTIGUOUS_DECOY_CLUSTER))
        handle.write(b"CONTIGUOUS-DECOY-" * 40)
        handle.seek(cluster_offset(INTERRUPTED_FIRST_CLUSTER))
        handle.write(interrupted_payload[:SECTOR_SIZE])
        handle.seek(cluster_offset(INTERRUPTED_DECOY_CLUSTER))
        handle.write(interrupted_payload[SECTOR_SIZE:])

    truth_path = root / "ground_truth.csv"
    with truth_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("image_filename", "source_filename", "target_present", "expected_offset", "expected_sha256"),
        )
        writer.writeheader()
        writer.writerows((
            {
                "image_filename": image_path.name,
                "source_filename": root_source.name,
                "target_present": "true",
                "expected_offset": cluster_offset(FILE_CLUSTER),
                "expected_sha256": hashlib.sha256(root_payload).hexdigest(),
            },
            {
                "image_filename": image_path.name,
                "source_filename": nested_source.name,
                "target_present": "true",
                "expected_offset": cluster_offset(NESTED_FILE_CLUSTER),
                "expected_sha256": hashlib.sha256(nested_payload).hexdigest(),
            },
            {
                "image_filename": image_path.name,
                "source_filename": "fragmented_control.bin",
                "target_present": "false",
                "expected_offset": cluster_offset(FRAGMENT_FIRST_CLUSTER),
                "expected_sha256": hashlib.sha256(fragmented_payload).hexdigest(),
            },
            {
                "image_filename": image_path.name,
                "source_filename": "interrupted_chain_control.bin",
                "target_present": "false",
                "expected_offset": cluster_offset(INTERRUPTED_FIRST_CLUSTER),
                "expected_sha256": hashlib.sha256(interrupted_payload).hexdigest(),
            },
        ))
    print(f"Synthetic FAT32 image: {image_path}")
    print(f"Root source file:     {root_source}")
    print(f"Nested source file:   {nested_source}")
    print(f"Ground truth:         {truth_path}")
    print(
        "The image tests root/subdirectory deletion, ignores active-file and deleted-directory controls, "
        "and is not a physical disk."
    )


if __name__ == "__main__":
    main()
