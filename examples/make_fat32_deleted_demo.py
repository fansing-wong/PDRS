"""Generate a synthetic FAT32 image with one deleted root 8.3 file entry."""
from __future__ import annotations

import csv
import hashlib
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "fat32_deleted_demo"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
TOTAL_SECTORS = 70000
SECTOR_SIZE = 512
RESERVED_SECTORS = 32
SECTORS_PER_FAT = 550
DATA_START_SECTOR = RESERVED_SECTORS + SECTORS_PER_FAT
ROOT_CLUSTER = 2
FILE_CLUSTER = 10
IMAGE_OFFSET = SECTOR_SIZE + (DATA_START_SECTOR + FILE_CLUSTER - 2) * SECTOR_SIZE


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing demo set: {ROOT}")
    IMAGE_DIR.mkdir(parents=True)
    SOURCE_DIR.mkdir()
    source_path = SOURCE_DIR / "deleted_sample.txt"
    payload = (
        b"Synthetic FAT32 deleted-file sample for PDRS.\r\n"
        b"Only the root 8.3 directory entry is marked deleted; data is contiguous.\r\n"
    ) * 12
    source_path.write_bytes(payload)

    image_path = IMAGE_DIR / "fat32_deleted_root.img"
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
        # FILE_CLUSTER remains free, reproducing the common post-delete FAT state.
        handle.seek(SECTOR_SIZE + RESERVED_SECTORS * SECTOR_SIZE)
        handle.write(fat)

        deleted_entry = bytearray(32)
        deleted_entry[0] = 0xE5
        deleted_entry[1:8] = b"ELETED "
        deleted_entry[8:11] = b"TXT"
        deleted_entry[11] = 0x20
        struct.pack_into("<H", deleted_entry, 26, FILE_CLUSTER)
        struct.pack_into("<I", deleted_entry, 28, len(payload))
        root_directory_offset = SECTOR_SIZE + DATA_START_SECTOR * SECTOR_SIZE
        handle.seek(root_directory_offset)
        handle.write(deleted_entry)

        # Include an intact directory entry to show that only deleted entries are extracted.
        active_entry = bytearray(32)
        active_entry[0:8] = b"ACTIVE  "
        active_entry[8:11] = b"TXT"
        active_entry[11] = 0x20
        struct.pack_into("<H", active_entry, 26, FILE_CLUSTER + 4)
        struct.pack_into("<I", active_entry, 28, len(payload))
        handle.write(active_entry)

        handle.seek(IMAGE_OFFSET)
        handle.write(payload)

    truth_path = ROOT / "ground_truth.csv"
    with truth_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("image_filename", "source_filename", "target_present", "expected_offset", "expected_sha256"),
        )
        writer.writeheader()
        writer.writerow({
            "image_filename": image_path.name,
            "source_filename": source_path.name,
            "target_present": "true",
            "expected_offset": IMAGE_OFFSET,
            "expected_sha256": hashlib.sha256(payload).hexdigest(),
        })
    print(f"Synthetic FAT32 image: {image_path}")
    print(f"Source file:          {source_path}")
    print(f"Ground truth:         {truth_path}")
    print("This generated image tests a deleted root 8.3 entry and contiguous data; it is not a physical disk.")


if __name__ == "__main__":
    main()
