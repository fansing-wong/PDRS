"""Preserve a deleted-directory FAT link in a generated PDRS synthetic image."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

SECTOR_SIZE = 512
DELETED_DIRECTORY_CLUSTER = 30
FAT32_EOC = 0x0FFFFFFF


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-dir", type=Path, required=True)
    root = parser.parse_args().demo_dir.expanduser().resolve()
    image_path = root / "images" / "fat32_deleted_root.img"
    truth_path = root / "ground_truth.csv"
    if not image_path.is_file() or not truth_path.is_file():
        raise SystemExit("Expected a generated PDRS FAT32 demo with images/ and ground_truth.csv.")

    with image_path.open("r+b") as handle:
        mbr = handle.read(SECTOR_SIZE)
        if mbr[510:512] != b"\x55\xaa":
            raise SystemExit("Refusing to modify an image without the expected synthetic MBR signature.")
        partition_lba = struct.unpack_from("<I", mbr, 454)[0]
        volume_offset = partition_lba * SECTOR_SIZE
        handle.seek(volume_offset)
        boot = handle.read(SECTOR_SIZE)
        if boot[71:82] != b"PDRS DEMO  " or boot[510:512] != b"\x55\xaa":
            raise SystemExit("Refusing to modify an image without the PDRS synthetic FAT32 marker.")
        bytes_per_sector = struct.unpack_from("<H", boot, 11)[0]
        reserved_sectors = struct.unpack_from("<H", boot, 14)[0]
        fat_start = volume_offset + reserved_sectors * bytes_per_sector
        fat_entry_offset = fat_start + DELETED_DIRECTORY_CLUSTER * 4
        handle.seek(fat_entry_offset)
        current = struct.unpack("<I", handle.read(4))[0] & 0x0FFFFFFF
        if current not in (0, FAT32_EOC):
            raise SystemExit(
                f"Refusing to replace unexpected FAT entry for cluster {DELETED_DIRECTORY_CLUSTER}: {current}."
            )
        if current == 0:
            handle.seek(fat_entry_offset)
            handle.write(struct.pack("<I", FAT32_EOC))

    print(f"Synthetic deleted-directory chain now ends at cluster {DELETED_DIRECTORY_CLUSTER}.")
    print(f"Image: {image_path}")


if __name__ == "__main__":
    main()
