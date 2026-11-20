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
SUBDIRECTORY_CLUSTER = 12
NESTED_FILE_CLUSTER = 20
DELETED_DIRECTORY_CLUSTER = 30
DELETED_DIRECTORY_FILE_CLUSTER = 40
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
        struct.pack_into("<I", fat, (FILE_CLUSTER + 4) * 4, 0x0FFFFFFF)
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
        active_file_offset = SECTOR_SIZE + (DATA_START_SECTOR + FILE_CLUSTER + 2) * SECTOR_SIZE
        handle.seek(active_file_offset)
        handle.write(payload)
    return payload, data_offset


def add_subdirectory_controls(image_path: Path) -> tuple[bytes, int]:
    nested_payload = b"Deleted in an active FAT32 subdirectory.\r\n" * 20
    decoy_payload = b"Must stay hidden inside a deleted directory.\r\n"
    fat_offset = SECTOR_SIZE + FAT_START_SECTOR * SECTOR_SIZE
    root_offset = SECTOR_SIZE + DATA_START_SECTOR * SECTOR_SIZE

    active_subdirectory = bytearray(32)
    active_subdirectory[:8] = b"SUBDIR  "
    active_subdirectory[11] = 0x10
    struct.pack_into("<H", active_subdirectory, 26, SUBDIRECTORY_CLUSTER)

    deleted_directory = bytearray(32)
    deleted_directory[0] = 0xE5
    deleted_directory[1:8] = b"ELDIR  "
    deleted_directory[11] = 0x10
    struct.pack_into("<H", deleted_directory, 26, DELETED_DIRECTORY_CLUSTER)

    nested_deleted_entry = bytearray(32)
    nested_deleted_entry[0] = 0xE5
    nested_deleted_entry[1:8] = b"ESTNEST"
    nested_deleted_entry[8:11] = b"TXT"
    nested_deleted_entry[11] = 0x20
    struct.pack_into("<H", nested_deleted_entry, 26, NESTED_FILE_CLUSTER)
    struct.pack_into("<I", nested_deleted_entry, 28, len(nested_payload))

    dot_entry = bytearray(32)
    dot_entry[:11] = b".          "
    dot_entry[11] = 0x10
    struct.pack_into("<H", dot_entry, 26, SUBDIRECTORY_CLUSTER)
    dotdot_entry = bytearray(32)
    dotdot_entry[:11] = b"..         "
    dotdot_entry[11] = 0x10
    struct.pack_into("<H", dotdot_entry, 26, ROOT_CLUSTER)

    deleted_directory_file = bytearray(32)
    deleted_directory_file[0] = 0xE5
    deleted_directory_file[1:8] = b"IDDEN  "
    deleted_directory_file[8:11] = b"TXT"
    deleted_directory_file[11] = 0x20
    struct.pack_into("<H", deleted_directory_file, 26, DELETED_DIRECTORY_FILE_CLUSTER)
    struct.pack_into("<I", deleted_directory_file, 28, len(decoy_payload))

    def cluster_offset(cluster: int) -> int:
        return SECTOR_SIZE + (DATA_START_SECTOR + cluster - 2) * SECTOR_SIZE

    with image_path.open("r+b") as handle:
        handle.seek(fat_offset + SUBDIRECTORY_CLUSTER * 4)
        handle.write(struct.pack("<I", 0x0FFFFFFF))
        handle.seek(fat_offset + DELETED_DIRECTORY_CLUSTER * 4)
        handle.write(struct.pack("<I", 0x0FFFFFFF))

        handle.seek(root_offset + 64)
        handle.write(active_subdirectory)
        handle.write(deleted_directory)

        subdirectory_offset = cluster_offset(SUBDIRECTORY_CLUSTER)
        handle.seek(subdirectory_offset)
        handle.write(nested_deleted_entry)
        handle.write(dot_entry)
        handle.write(dotdot_entry)

        handle.seek(cluster_offset(DELETED_DIRECTORY_CLUSTER))
        handle.write(deleted_directory_file)
        handle.seek(cluster_offset(NESTED_FILE_CLUSTER))
        handle.write(nested_payload)
        handle.seek(cluster_offset(DELETED_DIRECTORY_FILE_CLUSTER))
        handle.write(decoy_payload)
    return nested_payload, cluster_offset(NESTED_FILE_CLUSTER)


def _lfn_checksum(short_name: bytes) -> int:
    checksum = 0
    for byte in short_name:
        checksum = (((checksum & 1) << 7) | (checksum >> 1)) + byte
        checksum &= 0xFF
    return checksum


def add_deleted_lfn_to_directory(
    image_path: Path,
    directory_cluster: int,
    long_name: str,
    short_name: bytes,
) -> int:
    encoded = long_name.encode("utf-16le")
    units = list(struct.unpack(f"<{len(encoded) // 2}H", encoded))
    chunks = [units[index : index + 13] for index in range(0, len(units), 13)]
    checksum = _lfn_checksum(short_name)
    slots: list[bytes] = []
    for sequence in range(len(chunks), 0, -1):
        part = list(chunks[sequence - 1])
        if sequence == len(chunks) and len(part) < 13:
            part.append(0)
            part.extend([0xFFFF] * (13 - len(part)))
        entry = bytearray(32)
        entry[0] = sequence | (0x40 if sequence == len(chunks) else 0)
        entry[11] = 0x0F
        entry[12] = 0
        entry[13] = checksum
        struct.pack_into("<H", entry, 26, 0)
        packed_units = part + [0xFFFF] * (13 - len(part))
        flat_units = bytearray(struct.pack("<13H", *packed_units))
        entry[1:11] = flat_units[:10]
        entry[14:26] = flat_units[10:22]
        entry[28:32] = flat_units[22:26]
        entry[0] = 0xE5
        slots.append(bytes(entry))

    directory_offset = SECTOR_SIZE + (DATA_START_SECTOR + directory_cluster - 2) * SECTOR_SIZE
    shift = len(slots) * 32
    with image_path.open("r+b") as handle:
        handle.seek(directory_offset)
        original_cluster = bytearray(handle.read(SECTOR_SIZE))
        shifted = bytearray(SECTOR_SIZE)
        shifted[:shift] = b"".join(slots)
        shifted[shift:] = original_cluster[:-shift]
        handle.seek(directory_offset)
        handle.write(shifted)
    return directory_offset + shift


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
            self.assertEqual(result.directories_scanned, 1)
            self.assertEqual(result.directory_bytes_scanned, SECTOR_SIZE)
            self.assertEqual(len(result.rows), 1)
            self.assertTrue(all(row["filename"].startswith("deleted_") for row in result.rows))
            row = result.rows[0]
            self.assertEqual(row["offset"], expected_offset)
            self.assertEqual(row["format"], "txt")
            self.assertEqual(row["data_layout_status"], "fat_chain_cleared")
            self.assertTrue(row["filename"].endswith(".txt"))
            self.assertIsNone(row["format_valid"])
            self.assertEqual((output / str(row["filename"])).read_bytes(), payload)
            self.assertEqual(row["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), before_hash)

    def test_skips_deleted_file_when_surviving_fat_link_shows_fragmentation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fat32_fragmented_deleted.img"
            make_deleted_fat32_image(image)
            fat_offset = SECTOR_SIZE + FAT_START_SECTOR * SECTOR_SIZE
            with image.open("r+b") as handle:
                # The deleted file needs two clusters. Keep a link to a non-adjacent
                # cluster so contiguous extraction would incorrectly include cluster 11.
                handle.seek(fat_offset + FILE_CLUSTER * 4)
                handle.write(struct.pack("<I", FILE_CLUSTER + 2))
                handle.seek(fat_offset + (FILE_CLUSTER + 2) * 4)
                handle.write(struct.pack("<I", 0x0FFFFFFF))

            output = root / "recovered"
            result = recover_deleted_fat32(image, output)

            self.assertEqual(result.deleted_entries_seen, 1)
            self.assertEqual(result.rows, [])
            self.assertEqual(list(output.iterdir()), [])
            self.assertTrue(any("non-contiguous FAT link" in item for item in result.warnings))

    def test_skips_deleted_file_when_fat_chain_ends_before_declared_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fat32_interrupted_deleted.img"
            make_deleted_fat32_image(image)
            fat_offset = SECTOR_SIZE + FAT_START_SECTOR * SECTOR_SIZE
            with image.open("r+b") as handle:
                # The directory entry declares more than one cluster, but the FAT
                # marks the first cluster as the end of the chain.
                handle.seek(fat_offset + FILE_CLUSTER * 4)
                handle.write(struct.pack("<I", 0x0FFFFFFF))

            output = root / "recovered"
            result = recover_deleted_fat32(image, output)

            self.assertEqual(result.rows, [])
            self.assertEqual(list(output.iterdir()), [])
            self.assertTrue(any("end marker before the declared file size" in item for item in result.warnings))

    def test_recovers_deleted_short_entry_in_active_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fat32_nested_deleted.img"
            root_payload, _ = make_deleted_fat32_image(image)
            nested_payload, nested_offset = add_subdirectory_controls(image)
            output = root / "recovered"

            result = recover_deleted_fat32(image, output)

            self.assertEqual(result.deleted_entries_seen, 2)
            self.assertEqual(len(result.rows), 2)
            self.assertEqual(result.directories_scanned, 2)
            self.assertEqual(result.directory_bytes_scanned, 2 * SECTOR_SIZE)
            nested_row = next(row for row in result.rows if row["offset"] == nested_offset)
            self.assertEqual(nested_row["directory_depth"], 1)
            self.assertNotEqual(nested_payload, root_payload)
            self.assertEqual(
                (output / str(nested_row["filename"])).read_bytes(), nested_payload
            )
            self.assertEqual(nested_row["sha256"], hashlib.sha256(nested_payload).hexdigest())
            self.assertFalse(any(row["sha256"] == hashlib.sha256(
                b"Must stay hidden inside a deleted directory.\r\n"
            ).hexdigest() for row in result.rows))

    def test_reconstructs_deleted_long_filename_from_adjacent_slots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fat32_lfn_deleted.img"
            payload, _ = make_deleted_fat32_image(image)
            long_name = "恢复报告-2026-final.txt"
            entry_offset = add_deleted_lfn_to_directory(
                image, ROOT_CLUSTER, long_name, b"TESTFILETXT"
            )
            result = recover_deleted_fat32(image, root / "recovered")

            self.assertEqual(len(result.rows), 1)
            row = result.rows[0]
            self.assertEqual(row["directory_entry_offset"], entry_offset)
            self.assertEqual(row["original_long_filename"], long_name)
            self.assertEqual(row["long_filename_status"], "reconstructed_unverified")
            self.assertIn("恢复报告-2026-final__p01_entry_", row["filename"])
            self.assertIn("cannot be verified", row["validation_note"])
            self.assertEqual((root / "recovered" / str(row["filename"])).read_bytes(), payload)

    def test_invalid_deleted_lfn_does_not_block_short_entry_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fat32_bad_lfn.img"
            make_deleted_fat32_image(image)
            add_deleted_lfn_to_directory(
                image, ROOT_CLUSTER, "Long-name-sample.txt", b"TESTFILETXT"
            )
            root_offset = SECTOR_SIZE + DATA_START_SECTOR * SECTOR_SIZE
            with image.open("r+b") as handle:
                handle.seek(root_offset + 32 + 13)
                handle.write(b"\x00")

            result = recover_deleted_fat32(image, root / "recovered")

            self.assertEqual(len(result.rows), 1)
            self.assertEqual(result.rows[0]["original_long_filename"], "")
            self.assertEqual(result.rows[0]["long_filename_status"], "invalid")
            self.assertTrue(any("LFN slots" in warning for warning in result.warnings))

    def test_rejects_path_separators_in_reconstructed_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fat32_path_lfn.img"
            make_deleted_fat32_image(image)
            add_deleted_lfn_to_directory(
                image, ROOT_CLUSTER, "..\\escape.txt", b"TESTFILETXT"
            )
            output = root / "recovered"

            result = recover_deleted_fat32(image, output)

            self.assertEqual(len(result.rows), 1)
            self.assertEqual(result.rows[0]["original_long_filename"], "")
            self.assertEqual(result.rows[0]["long_filename_status"], "invalid")
            self.assertEqual([path.name for path in output.iterdir()], [result.rows[0]["filename"]])
            self.assertFalse((root / "escape.txt").exists())

    def test_rejects_bidi_controls_in_reconstructed_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fat32_bidi_lfn.img"
            make_deleted_fat32_image(image)
            add_deleted_lfn_to_directory(
                image, ROOT_CLUSTER, "safe\u202eexe.txt", b"TESTFILETXT"
            )

            result = recover_deleted_fat32(image, root / "recovered")

            self.assertEqual(len(result.rows), 1)
            self.assertEqual(result.rows[0]["original_long_filename"], "")
            self.assertEqual(result.rows[0]["long_filename_status"], "invalid")
            self.assertTrue(result.rows[0]["filename"].startswith("deleted_"))

    def test_reconstructs_deleted_long_filename_in_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fat32_nested_lfn.img"
            make_deleted_fat32_image(image)
            nested_payload, _ = add_subdirectory_controls(image)
            long_name = "nested report-恢复.txt"
            entry_offset = add_deleted_lfn_to_directory(
                image, SUBDIRECTORY_CLUSTER, long_name, b"TESTNESTTXT"
            )

            result = recover_deleted_fat32(image, root / "recovered")

            nested_row = next(row for row in result.rows if row["directory_entry_offset"] == entry_offset)
            self.assertEqual(nested_row["original_long_filename"], long_name)
            self.assertEqual(nested_row["long_filename_status"], "reconstructed_unverified")
            self.assertEqual(
                (root / "recovered" / str(nested_row["filename"])).read_bytes(), nested_payload
            )

    def test_respects_subdirectory_depth_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fat32_nested_deleted.img"
            make_deleted_fat32_image(image)
            add_subdirectory_controls(image)
            with patch("pdrs.fat32_recovery.MAX_DIRECTORY_DEPTH", 0):
                result = recover_deleted_fat32(image, root / "recovered")
            self.assertEqual(result.rows, [])
            self.assertTrue(any("depth limit" in item for item in result.warnings))
            self.assertTrue(any("extraction was skipped" in item for item in result.warnings))

    def test_respects_subdirectory_count_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fat32_nested_deleted.img"
            make_deleted_fat32_image(image)
            add_subdirectory_controls(image)
            with patch("pdrs.fat32_recovery.MAX_DIRECTORY_COUNT", 1):
                result = recover_deleted_fat32(image, root / "recovered")
            self.assertEqual(result.directories_scanned, 1)
            self.assertEqual(result.rows, [])
            self.assertTrue(any("safety limit" in item for item in result.warnings))

    def test_rejects_cyclic_subdirectory_chain_conservatively(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fat32_nested_deleted.img"
            make_deleted_fat32_image(image)
            add_subdirectory_controls(image)
            fat_offset = SECTOR_SIZE + FAT_START_SECTOR * SECTOR_SIZE
            with image.open("r+b") as handle:
                handle.seek(fat_offset + SUBDIRECTORY_CLUSTER * 4)
                handle.write(struct.pack("<I", SUBDIRECTORY_CLUSTER))

            result = recover_deleted_fat32(image, root / "recovered")

            self.assertEqual(result.rows, [])
            self.assertTrue(any("repeated cluster" in item for item in result.warnings))
            self.assertTrue(any("extraction was skipped" in item for item in result.warnings))

    def test_skips_contiguous_range_that_overlaps_active_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "fat32_nested_deleted.img"
            make_deleted_fat32_image(image)
            add_subdirectory_controls(image)
            root_entry_offset = SECTOR_SIZE + DATA_START_SECTOR * SECTOR_SIZE
            with image.open("r+b") as handle:
                handle.seek(root_entry_offset + 28)
                handle.write(struct.pack("<I", 1025))

            result = recover_deleted_fat32(image, root / "recovered")

            self.assertEqual(len(result.rows), 1)
            self.assertEqual(result.rows[0]["directory_depth"], 1)
            self.assertTrue(any("overlaps an active directory cluster" in item for item in result.warnings))

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
