"""Create a valid FAT32 partition image for the read-only inspector demo."""

from __future__ import annotations

import struct
import uuid
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "fat32_structure_demo"
IMAGE = ROOT / "mbr_fat32_demo.img"
GPT_IMAGE = ROOT / "gpt_partition_demo.img"
GPT_4K_IMAGE = ROOT / "gpt_4k_demo.img"
SECTOR_SIZE = 512
PARTITION_START_LBA = 2048
RESERVED_SECTORS = 32
FAT_COUNT = 2
SECTORS_PER_FAT = 512
DATA_CLUSTERS = 65_525
TOTAL_VOLUME_SECTORS = RESERVED_SECTORS + FAT_COUNT * SECTORS_PER_FAT + DATA_CLUSTERS
IMAGE_SECTORS = PARTITION_START_LBA + TOTAL_VOLUME_SECTORS + 32


def _fat32_boot_sector() -> bytes:
    boot = bytearray(SECTOR_SIZE)
    boot[0:3] = b"\xeb\x58\x90"
    boot[3:11] = b"MSWIN4.1"
    struct.pack_into("<H", boot, 11, SECTOR_SIZE)
    boot[13] = 1
    struct.pack_into("<H", boot, 14, RESERVED_SECTORS)
    boot[16] = FAT_COUNT
    struct.pack_into("<H", boot, 17, 0)
    struct.pack_into("<H", boot, 19, 0)
    boot[21] = 0xF8
    struct.pack_into("<H", boot, 22, 0)
    struct.pack_into("<H", boot, 24, 63)
    struct.pack_into("<H", boot, 26, 255)
    struct.pack_into("<I", boot, 28, PARTITION_START_LBA)
    struct.pack_into("<I", boot, 32, TOTAL_VOLUME_SECTORS)
    struct.pack_into("<I", boot, 36, SECTORS_PER_FAT)
    struct.pack_into("<H", boot, 40, 0)
    struct.pack_into("<H", boot, 42, 0)
    struct.pack_into("<I", boot, 44, 2)
    struct.pack_into("<H", boot, 48, 1)
    struct.pack_into("<H", boot, 50, 6)
    boot[64] = 0x80
    boot[66] = 0x29
    struct.pack_into("<I", boot, 67, 0x50445253)
    boot[71:82] = b"PDRS DEMO  "
    boot[82:90] = b"FAT32   "
    boot[510:512] = b"\x55\xaa"
    return bytes(boot)


def _fsinfo_sector() -> bytes:
    sector = bytearray(SECTOR_SIZE)
    struct.pack_into("<I", sector, 0, 0x41615252)
    struct.pack_into("<I", sector, 484, 0x61417272)
    struct.pack_into("<I", sector, 488, DATA_CLUSTERS - 1)
    struct.pack_into("<I", sector, 492, 3)
    sector[510:512] = b"\x55\xaa"
    return bytes(sector)


def _mbr_sector() -> bytes:
    sector = bytearray(SECTOR_SIZE)
    entry = 446
    sector[entry] = 0
    sector[entry + 4] = 0x0C
    struct.pack_into("<II", sector, entry + 8, PARTITION_START_LBA, TOTAL_VOLUME_SECTORS)
    sector[510:512] = b"\x55\xaa"
    return bytes(sector)


def _fat_sector() -> bytes:
    sector = bytearray(SECTOR_SIZE)
    struct.pack_into("<III", sector, 0, 0x0FFFFFF8, 0x0FFFFFFF, 0x0FFFFFFF)
    return bytes(sector)


def _gpt_entry_array(first_lba: int = 2048, last_lba: int = 3000) -> bytes:
    entries = bytearray(128 * 128)
    entry = bytearray(128)
    entry[:16] = uuid.UUID("ebd0a0a2-b9e5-4433-87c0-68b6b72699c7").bytes_le
    entry[16:32] = uuid.UUID("a2d0b91d-5b64-4df3-a624-75ca5b7d3e90").bytes_le
    struct.pack_into("<QQQ", entry, 32, first_lba, last_lba, 0)
    entry[56:128] = "PDRS GPT DEMO".encode("utf-16le").ljust(72, b"\0")
    entries[:128] = entry
    return bytes(entries)


def _gpt_header(
    current_lba: int,
    backup_lba: int,
    entries_lba: int,
    entries_crc: int,
    *,
    sector_size: int = SECTOR_SIZE,
    first_usable_lba: int = 34,
    last_usable_lba: int = 4062,
) -> bytes:
    header = bytearray(sector_size)
    header[:8] = b"EFI PART"
    struct.pack_into("<II", header, 8, 0x00010000, 92)
    struct.pack_into("<I", header, 20, 0)
    struct.pack_into(
        "<QQQQ", header, 24, current_lba, backup_lba, first_usable_lba, last_usable_lba
    )
    header[56:72] = uuid.UUID("345e1e64-28a1-45c9-84d2-9cc5807ff2d2").bytes_le
    struct.pack_into("<QIII", header, 72, entries_lba, 128, 128, entries_crc)
    struct.pack_into("<I", header, 16, zlib.crc32(header[:92]) & 0xFFFFFFFF)
    return bytes(header)


def _write_gpt_demo() -> None:
    total_sectors = 4096
    entries = _gpt_entry_array()
    entries_crc = zlib.crc32(entries) & 0xFFFFFFFF
    protective_mbr = bytearray(SECTOR_SIZE)
    protective_mbr[446 + 4] = 0xEE
    struct.pack_into("<II", protective_mbr, 446 + 8, 1, total_sectors - 1)
    protective_mbr[510:512] = b"\x55\xaa"

    with GPT_IMAGE.open("wb") as handle:
        handle.truncate(total_sectors * SECTOR_SIZE)
        handle.seek(0)
        handle.write(protective_mbr)
        handle.seek(SECTOR_SIZE)
        handle.write(_gpt_header(1, total_sectors - 1, 2, entries_crc))
        handle.seek(2 * SECTOR_SIZE)
        handle.write(entries)
        backup_entries_lba = total_sectors - 33
        handle.seek(backup_entries_lba * SECTOR_SIZE)
        handle.write(entries)
        handle.seek((total_sectors - 1) * SECTOR_SIZE)
        handle.write(_gpt_header(total_sectors - 1, 1, backup_entries_lba, entries_crc))


def _write_gpt_4k_demo() -> None:
    sector_size = 4096
    total_sectors = 256
    backup_entries_lba = total_sectors - 5
    entries = _gpt_entry_array(first_lba=16, last_lba=220)
    entries_crc = zlib.crc32(entries) & 0xFFFFFFFF
    protective_mbr = bytearray(SECTOR_SIZE)
    protective_mbr[446 + 4] = 0xEE
    struct.pack_into("<II", protective_mbr, 446 + 8, 1, total_sectors - 1)
    protective_mbr[510:512] = b"\x55\xaa"

    with GPT_4K_IMAGE.open("wb") as handle:
        handle.truncate(total_sectors * sector_size)
        handle.seek(0)
        handle.write(protective_mbr)
        handle.seek(sector_size)
        handle.write(
            _gpt_header(
                1, total_sectors - 1, 2, entries_crc,
                sector_size=sector_size, first_usable_lba=6, last_usable_lba=250,
            )
        )
        handle.seek(2 * sector_size)
        handle.write(entries)
        handle.seek(backup_entries_lba * sector_size)
        handle.write(entries)
        handle.seek((total_sectors - 1) * sector_size)
        handle.write(
            _gpt_header(
                total_sectors - 1, 1, backup_entries_lba, entries_crc,
                sector_size=sector_size, first_usable_lba=6, last_usable_lba=250,
            )
        )


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing demo directory: {ROOT}")
    ROOT.mkdir(parents=True)
    image_size = IMAGE_SECTORS * SECTOR_SIZE
    with IMAGE.open("wb") as handle:
        handle.truncate(image_size)
        handle.seek(0)
        handle.write(_mbr_sector())
        volume_start = PARTITION_START_LBA * SECTOR_SIZE
        boot = _fat32_boot_sector()
        handle.seek(volume_start)
        handle.write(boot)
        handle.seek(volume_start + SECTOR_SIZE)
        handle.write(_fsinfo_sector())
        handle.seek(volume_start + 6 * SECTOR_SIZE)
        handle.write(boot)
        handle.seek(volume_start + 7 * SECTOR_SIZE)
        handle.write(_fsinfo_sector())
        first_fat = volume_start + RESERVED_SECTORS * SECTOR_SIZE
        handle.seek(first_fat)
        handle.write(_fat_sector())
        handle.seek(first_fat + SECTORS_PER_FAT * SECTOR_SIZE)
        handle.write(_fat_sector())
    _write_gpt_demo()
    _write_gpt_4k_demo()
    print(f"Synthetic image: {IMAGE}")
    print(f"GPT image:       {GPT_IMAGE}")
    print(f"4Kn GPT image:   {GPT_4K_IMAGE}")
    print(f"FAT32 size:      {image_size:,} bytes; GPT sizes: {GPT_IMAGE.stat().st_size:,}, {GPT_4K_IMAGE.stat().st_size:,} bytes")
    print("Contains an MBR FAT32 volume plus 512-byte and 4096-byte GPT samples.")
    print("No files or directory entries are included.")


if __name__ == "__main__":
    main()
