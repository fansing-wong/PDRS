from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from pdrs.structure import inspect_image


def make_mbr_fat32_image() -> bytes:
    sector_size = 512
    image = bytearray(64 * sector_size)
    mbr = memoryview(image)[:sector_size]
    mbr[446 + 4] = 0x0C
    struct.pack_into("<II", mbr, 446 + 8, 1, 63)
    mbr[510:512] = b"\x55\xaa"

    boot = memoryview(image)[sector_size : 2 * sector_size]
    boot[3:11] = b"MSWIN4.1"
    struct.pack_into("<H", boot, 11, 512)
    boot[13] = 1
    struct.pack_into("<H", boot, 14, 1)
    boot[16] = 1
    boot[21] = 0xF8
    struct.pack_into("<I", boot, 28, 1)
    struct.pack_into("<I", boot, 32, 63)
    struct.pack_into("<I", boot, 36, 1)
    struct.pack_into("<I", boot, 44, 2)
    struct.pack_into("<H", boot, 48, 1)
    struct.pack_into("<H", boot, 50, 6)
    boot[67:71] = struct.pack("<I", 0x50445253)
    boot[71:82] = b"PDRS TEST  "
    boot[82:90] = b"FAT32   "
    boot[510:512] = b"\x55\xaa"
    return bytes(image)


def make_mbr_ext4_image() -> bytes:
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
    return bytes(image)


class StructureTests(unittest.TestCase):
    def test_reads_mbr_partition_and_fat32_bpb_without_modifying_image(self) -> None:
        image_data = make_mbr_fat32_image()
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "fat32.img"
            image.write_bytes(image_data)
            before = image.read_bytes()

            result = inspect_image(image)

            self.assertEqual(result.partition_table, "MBR")
            self.assertEqual(len(result.partitions), 1)
            self.assertEqual(result.partitions[0].offset_bytes, 512)
            self.assertEqual(len(result.volumes), 1)
            self.assertEqual(result.volumes[0].filesystem, "FAT32")
            self.assertEqual(result.volumes[0].volume_label, "PDRS TEST")
            self.assertEqual(image.read_bytes(), before)
            self.assertTrue(any("directories" in warning for warning in result.warnings))

    def test_reads_ext_superblock_without_modifying_image(self) -> None:
        image_data = make_mbr_ext4_image()
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "ext4.img"
            image.write_bytes(image_data)
            before = image.read_bytes()

            result = inspect_image(image)

            self.assertEqual(result.partition_table, "MBR")
            self.assertEqual(len(result.volumes), 1)
            volume = result.volumes[0]
            self.assertEqual(volume.filesystem, "ext4 (extents feature)")
            self.assertEqual(volume.offset_bytes, 512)
            self.assertEqual(volume.volume_label, "PDRS EXT4 DEMO")
            self.assertEqual(volume.details["block_size_bytes"], 4096)
            self.assertTrue(volume.details["fits_in_image_or_partition"])
            self.assertEqual(image.read_bytes(), before)

    def test_rejects_too_small_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "small.img"
            image.write_bytes(b"\0" * 128)
            with self.assertRaises(ValueError):
                inspect_image(image)


if __name__ == "__main__":
    unittest.main()
