"""Create valid and checksum-damaged exFAT images for the read-only inspector."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "exfat_structure_demo"
SECTOR_SIZE = 512
PARTITION_START_LBA = 2048
VOLUME_SECTORS = 2048  # Exactly 1 MiB, the minimum exFAT volume size.


def _boot_region() -> bytes:
    region = bytearray(12 * SECTOR_SIZE)
    boot = memoryview(region)[:SECTOR_SIZE]
    boot[0:3] = b"\xeb\x76\x90"
    boot[3:11] = b"EXFAT   "
    struct.pack_into("<Q", boot, 64, PARTITION_START_LBA)
    struct.pack_into("<Q", boot, 72, VOLUME_SECTORS)
    struct.pack_into("<I", boot, 80, 24)  # First FAT follows both 12-sector boot regions.
    struct.pack_into("<I", boot, 84, 16)
    struct.pack_into("<I", boot, 88, 40)
    struct.pack_into("<I", boot, 92, VOLUME_SECTORS - 40)
    struct.pack_into("<I", boot, 96, 2)
    struct.pack_into("<I", boot, 100, 0x50445253)
    struct.pack_into("<H", boot, 104, 0x0100)
    struct.pack_into("<H", boot, 106, 0)
    boot[108] = 9
    boot[109] = 0
    boot[110] = 1
    boot[111] = 0x80
    boot[112] = 0xFF
    boot[510:512] = b"\x55\xaa"

    for sector_index in range(1, 9):
        start = sector_index * SECTOR_SIZE
        region[start + SECTOR_SIZE - 4 : start + SECTOR_SIZE] = b"\x00\x00\x55\xaa"

    checksum = 0
    for index, value in enumerate(region[: 11 * SECTOR_SIZE]):
        if index in (106, 107, 112):
            continue
        checksum = (((checksum << 31) | (checksum >> 1)) + value) & 0xFFFFFFFF
    checksum_sector = 11 * SECTOR_SIZE
    for index in range(checksum_sector, len(region), 4):
        struct.pack_into("<I", region, index, checksum)
    return bytes(region)


def _mbr_sector() -> bytes:
    sector = bytearray(SECTOR_SIZE)
    entry = 446
    sector[entry] = 0
    sector[entry + 4] = 0x07
    struct.pack_into("<II", sector, entry + 8, PARTITION_START_LBA, VOLUME_SECTORS)
    sector[510:512] = b"\x55\xaa"
    return bytes(sector)


def _write_image(path: Path, *, corrupt_main_checksum: bool = False) -> None:
    total_sectors = PARTITION_START_LBA + VOLUME_SECTORS
    main = bytearray(_boot_region())
    backup = _boot_region()
    if corrupt_main_checksum:
        # Change one checksummed byte while preserving the stored checksum.
        main[2 * SECTOR_SIZE + 12] ^= 0x01

    with path.open("wb") as handle:
        handle.truncate(total_sectors * SECTOR_SIZE)
        handle.seek(0)
        handle.write(_mbr_sector())
        volume_offset = PARTITION_START_LBA * SECTOR_SIZE
        handle.seek(volume_offset)
        handle.write(main)
        handle.seek(volume_offset + 12 * SECTOR_SIZE)
        handle.write(backup)


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing demo directory: {ROOT}")
    ROOT.mkdir(parents=True)
    valid_image = ROOT / "valid_exfat.img"
    damaged_image = ROOT / "bad_main_checksum.img"
    _write_image(valid_image)
    _write_image(damaged_image, corrupt_main_checksum=True)
    print(f"Valid exFAT image:       {valid_image}")
    print(f"Bad-checksum exFAT image:{damaged_image}")
    print("Each image contains an MBR partition and empty exFAT boot regions; no files are included.")


if __name__ == "__main__":
    main()
