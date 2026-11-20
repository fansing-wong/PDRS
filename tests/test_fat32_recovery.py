from __future__ import annotations

import hashlib
import struct
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from pdrs.fat32_recovery import recover_deleted_fat32


SECTOR_SIZE = 512
TOTAL_SECTORS = 70000
RESERVED_SECTORS = 32
SECTORS_PER_FAT = 550
ROOT_CLUSTER = 2
FILE_CLUSTER = 10
FAT_START_SECTOR = RESERVED_SECTORS
DATA_START_SECTOR = RESERVED_SECTORS + SECTORS_PER_FAT


def make_deleted_fat32_image(path: Path) -> tuple[bytes, int]:
    payload = (b"Synthetic deleted FAT32 file for PDRS recovery experiment.\r\n" * 16)
    image_size = (TOTAL_SECTORS + 1) * SECTOR_SIZE
    with path.open("wb") as handle:
        handle.truncate(image_size)

    mbr = bytearray(SECTOR_SIZE)
    entry = 446
    mbr[entry + 4] = 0x0C
    struct.pack_into("<II", mbr, entry + 8, 1, TOTAL_SECTORS)
    mbr[510:512] = b"\x55\xaa"
    with path.open("r+b") as handle:
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

        fat_offset = SECTOR_SIZE + FAT_START_SECTOR * SECTOR_SIZE
        handle.seek(fat_offset)
        fat = bytearray(SECTORS_PER_FAT * SECTOR_SIZE)
        struct.pack_into("<I", fat, 0, 0x0FFFFFF8)
        struct.pack_into("<I", fat, 4, 0x0FFFFFFF)
        struct.pack_into("<I", fat, ROOT_CLUSTER * 4, 0x0FFFFFFF)
        # FILE_CLUSTER is free, as expected after deletion; PDRS will assume contiguous data.
        handle.write(fat)

        root_offset = SECTOR_SIZE + DATA_START_SECTOR * SECTOR_SIZE
        deleted_entry = bytearray(32)
        deleted_entry[0] = 0xE5
        deleted_entry[1:8] = b"ESTFILE"
        deleted_entry[8:11] = b"TXT"
        deleted_entry[11] = 0x20
        struct.pack_into("<H", deleted_entry, 26, FILE_CLUSTER)
        struct.pack_into("<I", deleted_entry, 28, len(payload))
        handle.seek(root_offset)
        handle.write(deleted_entry)

        # An intact short entry is a negative control: recovery must ignore it.
        active_entry = bytearray(32)
        active_entry[0:8] = b"ACTIVE  "
        active_entry[8:11] = b"TXT"
        active_entry[11] = 0x20
        struct.pack_into("<H", active_entry, 26, FILE_CLUSTER + 4)
        struct.pack_into("<I", active_entry, 28, len(payload))
        handle.write(active_entry)

        data_offset = SECTOR_SIZE + (DATA_START_SECTOR + FILE_CLUSTER - 2) * SECTOR_SIZE
        handle.seek(data_offset)
        handle.write(payload)
    return payload, data_offset


class Fat32RecoveryTests(unittest.TestCase):
    def test_recovers_deleted_root_short_entry_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fat32_deleted.img"
            payload, expected_offset = make_deleted_fat32_image(image)
            before_hash = hashlib.sha256(image.read_bytes()).hexdigest()
            output = root / "recovered"

            result = recover_deleted_fat32(image, output)

            self.assertEqual(result.deleted_entries_seen, 1)
            self.assertEqual(len(result.rows), 1)
            self.assertTrue(all(row["filename"].startswith("deleted_") for row in result.rows))
            row = result.rows[0]
            self.assertEqual(row["offset"], expected_offset)
            self.assertEqual(row["format"], "txt")
            self.assertTrue(row["filename"].endswith(".txt"))
            self.assertIsNone(row["format_valid"])
            self.assertEqual((output / str(row["filename"])).read_bytes(), payload)
            self.assertEqual(row["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), before_hash)

    def test_respects_aggregate_recovery_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fat32_deleted.img"
            make_deleted_fat32_image(image)
            with patch("pdrs.fat32_recovery.MAX_TOTAL_RECOVERED_BYTES", 10):
                result = recover_deleted_fat32(image, root / "recovered")
            self.assertEqual(result.rows, [])
            self.assertTrue(any("total-recovery safety limit" in item for item in result.warnings))

    def test_rejects_image_without_fat32_volume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "not_fat32.img"
            image.write_bytes(b"\0" * 512)
            with self.assertRaisesRegex(ValueError, "No supported FAT32"):
                recover_deleted_fat32(image, root / "out")

    def test_requires_empty_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fat32_deleted.img"
            make_deleted_fat32_image(image)
            output = root / "out"
            output.mkdir()
            (output / "keep.txt").write_text("do not overwrite", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                recover_deleted_fat32(image, output)
            self.assertEqual((output / "keep.txt").read_text(encoding="utf-8"), "do not overwrite")


if __name__ == "__main__":
    unittest.main()
