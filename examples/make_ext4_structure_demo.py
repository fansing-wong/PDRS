"""Create a small synthetic MBR image with ext4 superblock metadata."""
from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "ext4_structure_demo"
IMAGE = ROOT / "ext4_demo.img"


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing demo: {ROOT}")
    sector_size = 512
    partition_sectors = 8192
    image = bytearray((partition_sectors + 1) * sector_size)
    mbr = memoryview(image)[:sector_size]
    mbr[446 + 4] = 0x83
    struct.pack_into("<II", mbr, 446 + 8, 1, partition_sectors)
    mbr[510:512] = b"\x55\xaa"

    superblock_offset = sector_size + 1024
    superblock = memoryview(image)[superblock_offset : superblock_offset + 1024]
    struct.pack_into("<I", superblock, 0, 512)
    struct.pack_into("<I", superblock, 4, 1024)
    struct.pack_into("<I", superblock, 24, 2)
    struct.pack_into("<I", superblock, 32, 32768)
    struct.pack_into("<I", superblock, 40, 1024)
    struct.pack_into("<H", superblock, 56, 0xEF53)
    struct.pack_into("<H", superblock, 58, 1)
    struct.pack_into("<I", superblock, 76, 1)
    struct.pack_into("<H", superblock, 88, 256)
    struct.pack_into("<I", superblock, 96, 0x40)
    superblock[104:120] = bytes.fromhex("123456781234567890abcdef12345678")
    superblock[120:136] = b"PDRS EXT4 DEMO  "

    ROOT.mkdir()
    IMAGE.write_bytes(image)
    print(f"Synthetic ext4 image: {IMAGE}")
    print("The demo contains partition and superblock metadata only; it is not a mountable ext4 filesystem.")


if __name__ == "__main__":
    main()
