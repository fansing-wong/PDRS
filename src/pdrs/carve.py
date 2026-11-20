"""Read-only contiguous file carving from raw image files."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import mmap
import sqlite3
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator


MAX_PNG_COMPRESSED_BYTES = 64 * 1024 * 1024
MAX_PNG_DECODED_BYTES = 128 * 1024 * 1024
MAX_SQLITE_CHECK_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class FormatSpec:
    name: str
    extension: str
    header: bytes
    locate_end: Callable[[mmap.mmap, int], int | None]


@dataclass(frozen=True)
class Candidate:
    format: str
    extension: str
    offset: int
    end: int
    complete: bool
    format_valid: bool | None
    validation_note: str

    @property
    def size(self) -> int:
        return self.end - self.offset


def _jpeg_end(image: mmap.mmap, start: int) -> int | None:
    marker = image.find(b"\xff\xd9", start + 2)
    return marker + 2 if marker >= 0 else None


def _png_end(image: mmap.mmap, start: int) -> int | None:
    # IEND chunk is 12 bytes: length, type, CRC. Verify the zero length and chunk type.
    pos = start + 8
    while True:
        pos = image.find(b"IEND", pos)
        if pos < 0:
            return None
        if pos >= 4 and image[pos - 4 : pos] == b"\x00\x00\x00\x00":
            end = pos + 8
            return end if end <= len(image) else None
        pos += 4


def _pdf_end(image: mmap.mmap, start: int) -> int | None:
    marker = image.find(b"%%EOF", start + 5)
    if marker < 0:
        return None
    end = marker + 5
    while end < len(image) and image[end] in b"\r\n\t ":
        end += 1
    return end


def _parse_bmp_header(image: mmap.mmap, start: int) -> tuple[int, int, int, int, int, int, int] | None:
    """Parse supported BMP file/DIB headers and check declared pixel bounds."""
    if start < 0 or start + 26 > len(image) or image[start : start + 2] != b"BM":
        return None
    file_size, reserved1, reserved2, pixel_offset = struct.unpack_from("<IHHI", image, start + 2)
    dib_size = struct.unpack_from("<I", image, start + 14)[0]
    if reserved1 or reserved2 or dib_size not in {12, 40, 52, 56, 108, 124}:
        return None
    header_end = 14 + dib_size
    if start + header_end > len(image) or file_size < header_end or pixel_offset < header_end:
        return None
    if pixel_offset > file_size:
        return None

    if dib_size == 12:
        width, height, planes, bits_per_pixel = struct.unpack_from("<HHHH", image, start + 18)
        compression = 0
        image_size = 0
        colors_used = 0
        palette_entry_size = 3
    else:
        width, height, planes, bits_per_pixel, compression, image_size = struct.unpack_from(
            "<iiHHII", image, start + 18
        )
        colors_used = struct.unpack_from("<I", image, start + 46)[0]
        palette_entry_size = 4

    if width <= 0 or height == 0 or planes != 1 or bits_per_pixel not in {1, 4, 8, 16, 24, 32}:
        return None
    if compression not in {0, 1, 2, 3, 6}:
        return None
    if (compression == 1 and bits_per_pixel != 8) or (compression == 2 and bits_per_pixel != 4):
        return None
    if compression in {3, 6} and bits_per_pixel not in {16, 32}:
        return None
    if compression in {1, 2} and height < 0:
        return None

    minimum_pixel_offset = header_end
    if dib_size == 40 and compression == 3:
        minimum_pixel_offset += 12
    elif dib_size == 40 and compression == 6:
        minimum_pixel_offset += 16
    if bits_per_pixel <= 8:
        palette_count = colors_used or (1 << bits_per_pixel)
        minimum_pixel_offset += palette_count * palette_entry_size
    elif colors_used:
        minimum_pixel_offset += colors_used * 4
    if pixel_offset < minimum_pixel_offset:
        return None

    if compression in {1, 2}:
        if image_size == 0:
            return None
        pixel_bytes = image_size
    else:
        row_stride = ((width * bits_per_pixel + 31) // 32) * 4
        pixel_bytes = row_stride * abs(height)
        if image_size and image_size < pixel_bytes:
            return None
    if image_size and image_size > file_size - pixel_offset:
        return None
    if pixel_offset + pixel_bytes > file_size:
        return None
    return file_size, pixel_offset, dib_size, width, height, bits_per_pixel, compression


def _bmp_end(image: mmap.mmap, start: int) -> int | None:
    parsed = _parse_bmp_header(image, start)
    if parsed is None:
        return None
    end = start + parsed[0]
    return end if end <= len(image) else None


def _validate_bmp(image: mmap.mmap, start: int, end: int) -> tuple[bool, str]:
    parsed = _parse_bmp_header(image, start)
    if parsed is None:
        return False, "BMP file/DIB header or pixel-array bounds are invalid"
    declared_size = parsed[0]
    if start + declared_size != end:
        return False, "BMP candidate is truncated or its boundary differs from bfSize"
    return True, "BMP file/DIB headers, dimensions, and declared pixel-array bounds valid"


def _parse_sqlite_header(image: mmap.mmap, start: int) -> tuple[int, int, bool, int] | None:
    """Read bounded fields from an SQLite database header.

    The returned boolean indicates whether SQLite's in-header page count is
    trustworthy (nonzero and guarded by a matching change counter).
    """
    if start < 0 or start + 100 > len(image):
        return None
    header = image[start : start + 100]
    if header[:16] != b"SQLite format 3\x00":
        return None

    encoded_page_size = struct.unpack_from(">H", header, 16)[0]
    page_size = 65536 if encoded_page_size == 1 else encoded_page_size
    if page_size < 512 or page_size > 65536 or page_size & (page_size - 1):
        return None
    if header[18] not in (1, 2) or header[19] not in (1, 2):
        return None

    reserved_bytes = header[20]
    if page_size - reserved_bytes < 480 or header[21:24] != bytes((64, 32, 32)):
        return None
    if header[72:92] != b"\x00" * 20:
        return None
    schema_format = struct.unpack_from(">I", header, 44)[0]
    text_encoding = struct.unpack_from(">I", header, 56)[0]
    if schema_format > 4 or text_encoding > 3:
        return None

    change_counter = struct.unpack_from(">I", header, 24)[0]
    page_count = struct.unpack_from(">I", header, 28)[0]
    version_valid_for = struct.unpack_from(">I", header, 92)[0]
    size_is_valid = page_count > 0 and change_counter == version_valid_for
    return page_size, page_count, size_is_valid, reserved_bytes


def _sqlite_end(image: mmap.mmap, start: int) -> int | None:
    parsed = _parse_sqlite_header(image, start)
    if parsed is None:
        return None
    page_size, page_count, size_is_valid, _reserved_bytes = parsed
    if not size_is_valid:
        return None
    end = start + page_size * page_count
    return end if end <= len(image) else None


def _validate_sqlite(image: mmap.mmap, start: int, end: int) -> tuple[bool | None, str]:
    """Validate SQLite header, declared page extent, and the page-one B-tree header."""
    parsed = _parse_sqlite_header(image, start)
    if parsed is None:
        return False, "SQLite database header is invalid or truncated"
    page_size, page_count, size_is_valid, reserved_bytes = parsed
    if not size_is_valid:
        return False, "SQLite header page count is not trustworthy"
    declared_size = page_size * page_count
    if end - start != declared_size:
        return False, "SQLite candidate boundary differs from its declared page count"

    usable_size = page_size - reserved_bytes
    if start + page_size > end:
        return False, "SQLite first page exceeds the candidate boundary"
    page_type = image[start + 100]
    if page_type == 0x05:
        btree_header_size = 12
    elif page_type == 0x0D:
        btree_header_size = 8
    else:
        return False, "SQLite page one is not a table B-tree page"

    cell_count = struct.unpack_from(">H", image, start + 103)[0]
    cell_content_start = struct.unpack_from(">H", image, start + 105)[0]
    if cell_content_start == 0:
        cell_content_start = 65536
    pointer_array_end = 100 + btree_header_size + cell_count * 2
    if pointer_array_end > usable_size:
        return False, "SQLite page-one cell pointer array exceeds usable page space"
    if not pointer_array_end <= cell_content_start <= usable_size:
        return False, "SQLite page-one cell content offset is invalid"
    if declared_size > MAX_SQLITE_CHECK_BYTES:
        return None, (
            "SQLite header and page-one B-tree bounds valid; full quick_check skipped "
            f"because database exceeds the {MAX_SQLITE_CHECK_BYTES // (1024 * 1024)} MiB limit"
        )

    connection = sqlite3.connect(":memory:")
    try:
        deserialize = getattr(connection, "deserialize", None)
        if deserialize is None:
            return None, "SQLite full quick_check is unavailable in this Python SQLite build; structural checks passed"
        deserialize(bytes(image[start:end]))
        check = connection.execute("PRAGMA quick_check").fetchone()
        if check is None or check[0] != "ok":
            detail = "no result" if check is None else str(check[0])
            return False, f"SQLite quick_check failed: {detail}"
    except sqlite3.Error as error:
        return False, f"SQLite quick_check rejected candidate: {error}"
    finally:
        connection.close()
    return True, "SQLite header, page-one B-tree bounds, and full quick_check valid"


def _validate_png(image: mmap.mmap, start: int, end: int) -> tuple[bool, str]:
    """Validate a supported non-interlaced PNG, including CRCs and IDAT decoding."""
    if image[start : start + 8] != b"\x89PNG\r\n\x1a\n":
        return False, "PNG signature mismatch"

    position = start + 8
    seen_ihdr = False
    seen_idat = False
    idat_ended = False
    idat_parts: list[bytes] = []
    idat_size = 0
    png_properties: tuple[int, list[tuple[int, int]]] | None = None
    while position + 12 <= end:
        length = struct.unpack(">I", image[position : position + 4])[0]
        chunk_type = image[position + 4 : position + 8]
        data_start = position + 8
        data_end = data_start + length
        chunk_end = data_end + 4
        if chunk_end > end:
            return False, "PNG chunk exceeds candidate boundary"

        stored_crc = struct.unpack(">I", image[data_end:chunk_end])[0]
        actual_crc = zlib.crc32(image[position + 4 : data_end]) & 0xFFFFFFFF
        if stored_crc != actual_crc:
            return False, f"PNG CRC mismatch in {chunk_type.decode('ascii', errors='replace')} chunk"

        if not seen_ihdr:
            if chunk_type != b"IHDR" or length != 13:
                return False, "PNG must begin with a 13-byte IHDR chunk"
            seen_ihdr = True
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", image[data_start:data_end]
            )
            channels_by_color_type = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
            legal_bit_depths = {
                0: {1, 2, 4, 8, 16},
                2: {8, 16},
                3: {1, 2, 4, 8},
                4: {8, 16},
                6: {8, 16},
            }
            if width == 0 or height == 0:
                return False, "PNG dimensions must be nonzero"
            if color_type not in channels_by_color_type or bit_depth not in legal_bit_depths.get(color_type, set()):
                return False, "Unsupported PNG color type or bit depth"
            if compression != 0 or filter_method != 0:
                return False, "Unsupported PNG compression or filter method"
            bits_per_pixel = channels_by_color_type[color_type] * bit_depth
            if interlace == 0:
                pass_layouts = [((width * bits_per_pixel + 7) // 8, height)]
            elif interlace == 1:
                adam7_passes = (
                    (0, 0, 8, 8),
                    (4, 0, 8, 8),
                    (0, 4, 4, 8),
                    (2, 0, 4, 4),
                    (0, 2, 2, 4),
                    (1, 0, 2, 2),
                    (0, 1, 1, 2),
                )
                pass_layouts = []
                for start_x, start_y, step_x, step_y in adam7_passes:
                    pass_width = 0 if width <= start_x else (width - start_x + step_x - 1) // step_x
                    pass_height = 0 if height <= start_y else (height - start_y + step_y - 1) // step_y
                    if pass_width and pass_height:
                        pass_layouts.append(((pass_width * bits_per_pixel + 7) // 8, pass_height))
            else:
                return False, "Unsupported PNG interlace method"
            expected_decoded_size = sum((row_bytes + 1) * pass_height for row_bytes, pass_height in pass_layouts)
            if expected_decoded_size > MAX_PNG_DECODED_BYTES:
                return False, "PNG decoded data exceeds configured validation limit"
            png_properties = (expected_decoded_size, pass_layouts)
        elif chunk_type == b"IHDR":
            return False, "Duplicate PNG IHDR chunk"

        if chunk_type == b"IDAT":
            if idat_ended:
                return False, "PNG IDAT chunks must be consecutive"
            seen_idat = True
            idat_size += length
            if idat_size > MAX_PNG_COMPRESSED_BYTES:
                return False, "PNG compressed data exceeds configured validation limit"
            idat_parts.append(image[data_start:data_end])
        elif seen_idat:
            idat_ended = True

        if chunk_type == b"IEND":
            if length != 0:
                return False, "PNG IEND chunk must have zero length"
            if not seen_ihdr or not seen_idat:
                return False, "PNG is missing required IHDR or IDAT chunk"
            if chunk_end != end:
                return False, "Bytes follow PNG IEND chunk"
            if png_properties is None:
                return False, "PNG IHDR properties unavailable"
            expected_decoded_size, pass_layouts = png_properties
            try:
                decoder = zlib.decompressobj()
                decoded = decoder.decompress(b"".join(idat_parts), expected_decoded_size + 1)
            except zlib.error as error:
                return False, f"PNG IDAT zlib stream invalid: {error}"
            if len(decoded) != expected_decoded_size:
                return False, "PNG IDAT decoded length does not match IHDR dimensions"
            if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                return False, "PNG IDAT zlib stream is incomplete or contains trailing data"
            decoded_offset = 0
            for row_bytes, pass_height in pass_layouts:
                stride = row_bytes + 1
                for _ in range(pass_height):
                    if decoded[decoded_offset] > 4:
                        return False, "PNG scanline contains an invalid filter byte"
                    decoded_offset += stride
            return True, "PNG chunks, CRCs, zlib stream, scanline lengths, and interlace layout valid"

        position = chunk_end

    return False, "PNG IEND chunk not found within candidate boundary"


def _validate_with_optional_parser(
    format_name: str, image: mmap.mmap, start: int, end: int
) -> tuple[bool | None, str]:
    """Use optional independent parsers for JPEG/PDF candidates when installed."""
    if format_name == "jpeg":
        if importlib.util.find_spec("PIL") is None:
            return None, "Install the validation extra to check JPEG structure"
        try:
            from PIL import Image

            with Image.open(io.BytesIO(image[start:end])) as decoded:
                decoded.load()
                if decoded.format != "JPEG":
                    return False, "Image decoder did not identify a JPEG"
            return True, "Pillow fully decoded JPEG candidate"
        except Exception as error:
            return False, f"JPEG decoder rejected candidate: {type(error).__name__}: {error}"

    if format_name == "pdf":
        if importlib.util.find_spec("pypdf") is None:
            return None, "Install the validation extra to check PDF structure"
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(image[start:end]), strict=True)
            page_count = len(reader.pages)
            reader.close()
            return True, f"pypdf parsed PDF candidate ({page_count} page(s))"
        except Exception as error:
            return False, f"PDF parser rejected candidate: {type(error).__name__}: {error}"

    return None, "No format validator registered"


FORMATS = (
    FormatSpec("jpeg", ".jpg", b"\xff\xd8\xff", _jpeg_end),
    FormatSpec("png", ".png", b"\x89PNG\r\n\x1a\n", _png_end),
    FormatSpec("pdf", ".pdf", b"%PDF-", _pdf_end),
    FormatSpec("bmp", ".bmp", b"BM", _bmp_end),
    FormatSpec("sqlite", ".sqlite", b"SQLite format 3\x00", _sqlite_end),
)


def find_candidates(image: mmap.mmap) -> Iterator[Candidate]:
    """Yield candidates in offset order; incomplete candidates extend to image end."""
    found: list[tuple[int, FormatSpec]] = []
    for spec in FORMATS:
        offset = 0
        while True:
            offset = image.find(spec.header, offset)
            if offset < 0:
                break
            if spec.name == "bmp" and _parse_bmp_header(image, offset) is None:
                offset += len(spec.header)
                continue
            if spec.name == "sqlite" and _parse_sqlite_header(image, offset) is None:
                offset += len(spec.header)
                continue
            found.append((offset, spec))
            offset += len(spec.header)

    found.sort(key=lambda item: item[0])
    for index, (start, spec) in enumerate(found):
        boundary = found[index + 1][0] if index + 1 < len(found) else len(image)
        end = spec.locate_end(image, start)
        complete = end is not None and end <= boundary
        candidate_end = end if complete else boundary
        if spec.name == "png":
            format_valid, validation_note = _validate_png(image, start, candidate_end)
        elif spec.name == "bmp":
            format_valid, validation_note = _validate_bmp(image, start, candidate_end)
        elif spec.name == "sqlite":
            format_valid, validation_note = _validate_sqlite(image, start, candidate_end)
        else:
            format_valid, validation_note = _validate_with_optional_parser(
                spec.name, image, start, candidate_end
            )
        yield Candidate(
            spec.name, spec.extension, start, candidate_end, complete,
            format_valid, validation_note,
        )


def sha256(data: memoryview) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()


def carve_image(image_path: Path, output_dir: Path) -> list[dict[str, object]]:
    """Carve a raw image without modifying it and return manifest rows."""
    source = image_path.resolve(strict=True)
    destination = output_dir.resolve()
    if not source.is_file():
        raise ValueError("Input must be a regular image file; physical devices are not supported.")
    if destination == source.parent:
        raise ValueError("Output directory cannot be the source image directory.")
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise FileExistsError("Output directory must be empty to prevent overwriting or mixing runs.")

    rows: list[dict[str, object]] = []
    with source.open("rb") as handle:
        if source.stat().st_size == 0:
            return rows
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as image:
            for number, candidate in enumerate(find_candidates(image), start=1):
                view = memoryview(image)[candidate.offset : candidate.end]
                digest = sha256(view)
                filename = f"{candidate.format}_{candidate.offset:012x}_{number:04d}{candidate.extension}"
                output_path = destination / filename
                try:
                    with output_path.open("xb") as output:
                        output.write(view)
                finally:
                    view.release()
                rows.append({
                    "filename": filename,
                    "format": candidate.format,
                    "offset": candidate.offset,
                    "end_offset_exclusive": candidate.end,
                    "size_bytes": candidate.size,
                    "complete_boundary": candidate.complete,
                    "format_valid": candidate.format_valid,
                    "validation_note": candidate.validation_note,
                    "sha256": digest,
                })
    return rows
