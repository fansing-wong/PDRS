from __future__ import annotations

import hashlib
import sqlite3
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib
from pathlib import Path

from pdrs.carve import carve_image


def make_bmp24() -> bytes:
    width, height = 2, 2
    row_stride = ((width * 24 + 31) // 32) * 4
    pixels = bytes((0, 0, 255, 0, 255, 0, 0, 0, 255, 0, 0, 255, 255, 255, 0, 0))
    file_size = 54 + len(pixels)
    file_header = b"BM" + struct.pack("<IHHI", file_size, 0, 0, 54)
    dib_header = struct.pack(
        "<IiiHHIIiiII", 40, width, height, 1, 24, 0, row_stride * height, 2835, 2835, 0, 0
    )
    return file_header + dib_header + pixels


def png_chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)


def make_png() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    pixels = zlib.compress(b"\0\xff\x00\x80\xff")
    return b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", pixels) + png_chunk(b"IEND", b"")


def make_sqlite_database(path: Path) -> bytes:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA page_size=1024")
        connection.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO messages (body) VALUES (?)",
            [(f"Synthetic message {number}",) for number in range(20)],
        )
        connection.commit()
    finally:
        connection.close()
    return path.read_bytes()


class CarveTests(unittest.TestCase):
    def test_bmp_is_carved_and_malformed_signature_is_ignored(self) -> None:
        bmp = make_bmp24()
        image_data = b"prefix BM\x00\x00\x00\x00 not a bitmap" + b"x" * 16 + bmp + b"tail"
        expected_offset = image_data.index(bmp)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "disk.img"
            output = root / "out"
            image.write_bytes(image_data)

            rows = carve_image(image, output)

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["format"], "bmp")
            self.assertEqual(row["offset"], expected_offset)
            self.assertTrue(row["complete_boundary"])
            self.assertTrue(row["format_valid"])
            recovered = output / str(row["filename"])
            self.assertEqual(recovered.read_bytes(), bmp)
            self.assertEqual(row["sha256"], hashlib.sha256(bmp).hexdigest())

    def test_truncated_bmp_is_reported_as_incomplete(self) -> None:
        bmp = make_bmp24()
        image_data = b"prefix" + bmp[:-1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "truncated.img"
            output = root / "out"
            image.write_bytes(image_data)

            rows = carve_image(image, output)

            self.assertEqual(len(rows), 1)
            self.assertFalse(rows[0]["complete_boundary"])
            self.assertFalse(rows[0]["format_valid"])

    def test_sqlite_database_is_carved_and_decoy_header_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.sqlite"
            database = make_sqlite_database(source)
            decoy = b"SQLite format 3\x00" + b"\x00" * 128
            image_data = b"prefix" + decoy + b"filler" * 5 + database + b"tail"
            expected_offset = image_data.index(database)
            image = root / "disk.img"
            output = root / "out"
            image.write_bytes(image_data)

            rows = carve_image(image, output)

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["format"], "sqlite")
            self.assertEqual(row["offset"], expected_offset)
            self.assertTrue(row["complete_boundary"])
            self.assertTrue(row["format_valid"])
            recovered = output / str(row["filename"])
            self.assertEqual(recovered.read_bytes(), database)
            self.assertEqual(row["sha256"], hashlib.sha256(database).hexdigest())
            connection = sqlite3.connect(recovered.as_uri() + "?mode=ro", uri=True)
            try:
                self.assertEqual(connection.execute("PRAGMA quick_check").fetchone()[0], "ok")
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM messages").fetchone()[0], 20
                )
            finally:
                connection.close()

    def test_large_sqlite_candidate_reports_deep_check_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = make_sqlite_database(root / "source.sqlite")
            image = root / "large_candidate.img"
            image.write_bytes(b"prefix" + database)

            with patch("pdrs.carve.MAX_SQLITE_CHECK_BYTES", 1):
                rows = carve_image(image, root / "out")

            self.assertEqual(len(rows), 1)
            self.assertIsNone(rows[0]["format_valid"])
            self.assertIn("quick_check skipped", str(rows[0]["validation_note"]))

    def test_damaged_sqlite_btree_fails_quick_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.sqlite"
            database = bytearray(make_sqlite_database(source))
            connection = sqlite3.connect(source)
            try:
                root_page = connection.execute(
                    "SELECT rootpage FROM sqlite_schema WHERE name='messages'"
                ).fetchone()[0]
            finally:
                connection.close()
            page_size = struct.unpack_from(">H", database, 16)[0]
            database[(root_page - 1) * page_size] = 0xFF
            image = root / "damaged.img"
            image.write_bytes(b"prefix" + database)

            rows = carve_image(image, root / "out")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["format"], "sqlite")
            self.assertTrue(rows[0]["complete_boundary"])
            self.assertFalse(rows[0]["format_valid"])
            self.assertIn("quick_check", str(rows[0]["validation_note"]))

    def test_truncated_sqlite_database_is_marked_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = make_sqlite_database(root / "source.sqlite")
            image = root / "truncated.img"
            output = root / "out"
            image.write_bytes(b"x" * 32 + database[:-64])

            rows = carve_image(image, output)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["format"], "sqlite")
            self.assertFalse(rows[0]["complete_boundary"])
            self.assertFalse(rows[0]["format_valid"])

    def test_png_carving_still_validates_crc_and_zlib(self) -> None:
        png = make_png()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "png.img"
            output = root / "out"
            image.write_bytes(b"x" * 64 + png)

            rows = carve_image(image, output)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["format"], "png")
            self.assertTrue(rows[0]["format_valid"])


if __name__ == "__main__":
    unittest.main()
