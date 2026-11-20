"""Experimental recovery of deleted FAT32 short entries in active directories."""
from __future__ import annotations

import hashlib
import mmap
import stat
import struct
from bisect import bisect_left
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pdrs.structure import ImageStructure, Partition, VolumeInfo, inspect_image

MAX_DIRECTORY_CHAIN_BYTES = 64 * 1024 * 1024
MAX_TOTAL_DIRECTORY_BYTES = 256 * 1024 * 1024
MAX_DIRECTORY_COUNT = 4096
MAX_DIRECTORY_DEPTH = 32
MAX_RECOVERED_FILE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_RECOVERED_BYTES = 1024 * 1024 * 1024
MAX_CANDIDATES = 10000
MAX_WARNINGS = 100
MAX_LFN_ENTRIES = 20
BIDI_CONTROL_CODEPOINTS = {
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    0x2066, 0x2067, 0x2068, 0x2069,
}
FAT32_EOC_MIN = 0x0FFFFFF8
FAT32_BAD_CLUSTER = 0x0FFFFFF7


@dataclass(frozen=True)
class Fat32RecoveryResult:
    rows: list[dict[str, Any]]
    warnings: list[str]
    deleted_entries_seen: int
    directories_scanned: int
    directory_bytes_scanned: int


def _partition_for(volume: VolumeInfo, structure: ImageStructure) -> Partition | None:
    if volume.partition_number is None:
        return None
    return next(
        (partition for partition in structure.partitions if partition.number == volume.partition_number),
        None,
    )


def _fat_entry(image: mmap.mmap, fat_start: int, fat_bytes: int, cluster: int) -> int:
    entry_offset = fat_start + cluster * 4
    if cluster < 0 or entry_offset + 4 > fat_start + fat_bytes:
        raise ValueError("FAT entry lies outside the first FAT table.")
    return struct.unpack_from("<I", image, entry_offset)[0] & 0x0FFFFFFF


def _directory_chain(
    image: mmap.mmap,
    *,
    fat_start: int,
    fat_bytes: int,
    start_cluster: int,
    cluster_count: int,
    cluster_size: int,
) -> list[int]:
    clusters: list[int] = []
    seen: set[int] = set()
    current = start_cluster
    while True:
        if current < 2 or current >= cluster_count + 2 or current in seen:
            raise ValueError("FAT32 directory chain contains an invalid or repeated cluster.")
        if (len(clusters) + 1) * cluster_size > MAX_DIRECTORY_CHAIN_BYTES:
            raise ValueError("FAT32 directory chain exceeds the 64 MiB inspection limit.")
        clusters.append(current)
        seen.add(current)
        next_cluster = _fat_entry(image, fat_start, fat_bytes, current)
        if next_cluster >= FAT32_EOC_MIN:
            break
        if next_cluster in (0, 1, FAT32_BAD_CLUSTER) or next_cluster >= 0x0FFFFFF0:
            raise ValueError("FAT32 directory chain contains a free, bad, or reserved cluster.")
        current = next_cluster
        if len(clusters) > cluster_count:
            raise ValueError("FAT32 directory chain exceeds the declared cluster count.")
    return clusters


def _entry_cluster(entry: bytes) -> int:
    return ((struct.unpack_from("<H", entry, 20)[0] & 0x0FFF) << 16) | struct.unpack_from(
        "<H", entry, 26
    )[0]


def _is_dot_directory(entry: bytes) -> bool:
    return entry[:11].rstrip(b" ") in (b".", b"..")


def _unsafe_filename_character(char: str) -> bool:
    codepoint = ord(char)
    return (
        codepoint < 0x20
        or 0x7F <= codepoint <= 0x9F
        or codepoint in BIDI_CONTROL_CODEPOINTS
        or char in '<>:"/\\|?*'
    )


def _decode_deleted_lfn(slots: list[bytes]) -> tuple[str | None, str]:
    if not slots:
        return None, "not_present"
    if len(slots) > MAX_LFN_ENTRIES:
        return None, "invalid"
    checksum = slots[0][13]
    if any(
        slot[0] != 0xE5
        or slot[11] != 0x0F
        or slot[12] != 0
        or slot[13] != checksum
        or struct.unpack_from("<H", slot, 26)[0] != 0
        for slot in slots
    ):
        return None, "invalid"

    units: list[int] = []
    for slot in reversed(slots):
        for offset, length in ((1, 10), (14, 12), (28, 4)):
            units.extend(struct.unpack_from(f"<{length // 2}H", slot, offset))
    terminators = [index for index, unit in enumerate(units) if unit in (0, 0xFFFF)]
    if terminators:
        end = terminators[0]
        if any(unit not in (0, 0xFFFF) for unit in units[end:]):
            return None, "invalid"
        units = units[:end]
    if not units or len(units) > 255:
        return None, "invalid"
    try:
        name = struct.pack(f"<{len(units)}H", *units).decode("utf-16le", errors="strict")
    except (UnicodeDecodeError, struct.error):
        return None, "invalid"
    if (
        not name
        or name.endswith((" ", "."))
        or any(_unsafe_filename_character(char) for char in name)
    ):
        return None, "invalid"
    return name, "reconstructed_unverified"


def _add_warning(warnings: list[str], message: str) -> None:
    if len(warnings) < MAX_WARNINGS:
        warnings.append(message)
    elif len(warnings) == MAX_WARNINGS:
        warnings.append("Additional recovery warnings were omitted.")


def _extension(entry: bytes) -> str:
    raw = entry[8:11].decode("ascii", errors="ignore").strip().lower()
    if not raw or any(not (char.isalnum() or char in "_$~-") for char in raw):
        return ".bin"
    return f".{raw}"


def _candidate_filename(
    long_name: str | None,
    extension: str,
    partition_number: int,
    entry_offset: int,
) -> str:
    unique_suffix = f"p{partition_number:02d}_entry_{entry_offset:012x}"
    if not long_name:
        return f"deleted_{unique_suffix}{extension}"
    if "." in long_name:
        original_stem, original_extension = long_name.rsplit(".", 1)
    else:
        original_stem, original_extension = long_name, ""

    def _safe_component(value: str) -> str:
        return "".join(
            "_" if _unsafe_filename_character(char) else char
            for char in value
        ).strip(" .")

    safe_stem = _safe_component(original_stem)
    if not safe_stem:
        return f"deleted_{unique_suffix}{extension}"
    safe_stem = safe_stem[:80]
    safe_extension = _safe_component(original_extension)[:20]
    reserved_names = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    reserved_names.update(f"COM{index}" for index in range(1, 10))
    reserved_names.update(f"LPT{index}" for index in range(1, 10))
    if safe_stem.upper() in reserved_names:
        safe_stem = f"_{safe_stem}"
    suffix = f".{safe_extension}" if safe_extension else ""
    return f"{safe_stem}__{unique_suffix}{suffix}"


def _volume_geometry(
    image: mmap.mmap,
    volume: VolumeInfo,
    available_bytes: int,
) -> dict[str, int]:
    offset = volume.offset_bytes
    if offset < 0 or offset + 512 > len(image):
        raise ValueError("FAT32 boot sector lies outside the image.")
    boot = image[offset : offset + 512]
    bytes_per_sector = struct.unpack_from("<H", boot, 11)[0]
    sectors_per_cluster = boot[13]
    reserved_sectors = struct.unpack_from("<H", boot, 14)[0]
    fat_count = boot[16]
    total_sectors = struct.unpack_from("<I", boot, 32)[0]
    sectors_per_fat = struct.unpack_from("<I", boot, 36)[0]
    root_cluster = struct.unpack_from("<I", boot, 44)[0]

    if bytes_per_sector not in (512, 1024, 2048, 4096):
        raise ValueError("Unsupported FAT32 bytes-per-sector value.")
    if sectors_per_cluster == 0 or sectors_per_cluster & (sectors_per_cluster - 1):
        raise ValueError("Invalid FAT32 sectors-per-cluster value.")
    if reserved_sectors == 0 or not 1 <= fat_count <= 4 or sectors_per_fat == 0:
        raise ValueError("FAT32 reserved-sector or FAT geometry is invalid.")
    data_sectors = total_sectors - reserved_sectors - fat_count * sectors_per_fat
    cluster_count = data_sectors // sectors_per_cluster if data_sectors > 0 else 0
    cluster_size = bytes_per_sector * sectors_per_cluster
    volume_bytes = total_sectors * bytes_per_sector
    fat_start = offset + reserved_sectors * bytes_per_sector
    fat_bytes = sectors_per_fat * bytes_per_sector
    data_start = fat_start + fat_count * fat_bytes
    if (
        cluster_count <= 0
        or root_cluster < 2
        or root_cluster >= cluster_count + 2
        or fat_bytes < (cluster_count + 2) * 4
    ):
        raise ValueError("FAT32 root cluster or FAT table capacity is invalid.")
    if volume_bytes > available_bytes or offset + volume_bytes > len(image):
        raise ValueError("The FAT32 volume is incomplete in the selected image; recovery was not attempted.")
    if fat_start + fat_bytes > offset + volume_bytes or data_start > offset + volume_bytes:
        raise ValueError("FAT32 metadata regions lie outside the declared volume.")
    return {
        "bytes_per_sector": bytes_per_sector,
        "sectors_per_cluster": sectors_per_cluster,
        "cluster_size": cluster_size,
        "cluster_count": cluster_count,
        "root_cluster": root_cluster,
        "volume_end": offset + volume_bytes,
        "fat_start": fat_start,
        "fat_bytes": fat_bytes,
        "data_start": data_start,
        "data_end": data_start + cluster_count * cluster_size,
    }


def _recover_volume(
    image: mmap.mmap,
    volume: VolumeInfo,
    available_bytes: int,
    partition_number: int,
    output: Path,
    rows: list[dict[str, Any]],
) -> tuple[int, list[str], int, int]:
    warnings: list[str] = []
    geometry = _volume_geometry(image, volume, available_bytes)
    cluster_size = geometry["cluster_size"]
    deleted_seen = 0
    total_recovered_bytes = sum(int(row["size_bytes"]) for row in rows)
    root_cluster = geometry["root_cluster"]
    pending_directories = deque([(root_cluster, 0)])
    scheduled_starts = {root_cluster}
    scanned_directory_clusters: set[int] = set()
    scanned_directory_count = 0
    total_directory_bytes = 0
    depth_limit_reported = False
    count_limit_reported = False
    candidate_limit_reported = False
    directory_scan_complete = True
    deleted_entries: list[tuple[int, int, int, bytes, str | None, str]] = []

    while pending_directories:
        directory_start, depth = pending_directories.popleft()
        if scanned_directory_count >= MAX_DIRECTORY_COUNT:
            _add_warning(warnings, f"Stopped after the {MAX_DIRECTORY_COUNT}-directory safety limit.")
            directory_scan_complete = False
            break
        try:
            directory_clusters = _directory_chain(
                image,
                fat_start=geometry["fat_start"],
                fat_bytes=geometry["fat_bytes"],
                start_cluster=directory_start,
                cluster_count=geometry["cluster_count"],
                cluster_size=cluster_size,
            )
        except ValueError as error:
            if directory_start == root_cluster:
                raise
            _add_warning(warnings, f"FAT32 subdirectory at cluster {directory_start} was skipped: {error}")
            directory_scan_complete = False
            continue

        directory_bytes = len(directory_clusters) * cluster_size
        if total_directory_bytes + directory_bytes > MAX_TOTAL_DIRECTORY_BYTES:
            _add_warning(warnings, "Stopped before exceeding the 256 MiB total-directory scan limit.")
            directory_scan_complete = False
            break
        overlap = scanned_directory_clusters.intersection(directory_clusters)
        if overlap:
            _add_warning(
                warnings,
                f"FAT32 directory at cluster {directory_start} overlaps an already scanned chain; skipped.",
            )
            directory_scan_complete = False
            continue
        scanned_directory_clusters.update(directory_clusters)
        scanned_directory_count += 1
        total_directory_bytes += directory_bytes

        stop_directory = False
        pending_lfn_slots: list[bytes] = []
        for directory_cluster in directory_clusters:
            directory_offset = geometry["data_start"] + (directory_cluster - 2) * cluster_size
            directory_end = directory_offset + cluster_size
            if directory_offset < geometry["data_start"] or directory_end > geometry["data_end"]:
                if directory_start == root_cluster:
                    raise ValueError("FAT32 root directory cluster lies outside the data region.")
                _add_warning(
                    warnings,
                    f"FAT32 subdirectory at cluster {directory_start} has a cluster outside the data region; skipped.",
                )
                directory_scan_complete = False
                stop_directory = True
                break
            for entry_offset in range(directory_offset, directory_end, 32):
                entry = image[entry_offset : entry_offset + 32]
                first_byte = entry[0]
                if first_byte == 0x00:
                    pending_lfn_slots.clear()
                    stop_directory = True
                    break
                attributes = entry[11]
                if attributes == 0x0F:
                    if first_byte == 0xE5:
                        if len(pending_lfn_slots) <= MAX_LFN_ENTRIES:
                            pending_lfn_slots.append(entry)
                    else:
                        pending_lfn_slots.clear()
                    continue
                if first_byte == 0xE5:
                    if attributes == 0x0F or attributes & 0x18:
                        pending_lfn_slots.clear()
                        continue
                    deleted_seen += 1
                    long_name, long_name_status = _decode_deleted_lfn(pending_lfn_slots)
                    if pending_lfn_slots and long_name_status == "invalid":
                        _add_warning(warnings, f"Deleted LFN slots before entry {entry_offset} were incomplete or invalid.")
                    if len(deleted_entries) < MAX_CANDIDATES:
                        deleted_entries.append((
                            entry_offset,
                            directory_cluster,
                            depth,
                            entry,
                            long_name,
                            long_name_status,
                        ))
                    elif not candidate_limit_reported:
                        _add_warning(warnings, f"Only the first {MAX_CANDIDATES} deleted entries will be considered.")
                        candidate_limit_reported = True
                    pending_lfn_slots.clear()
                    continue

                pending_lfn_slots.clear()
                if attributes == 0x0F or not attributes & 0x10 or attributes & 0x08 or _is_dot_directory(entry):
                    continue
                child_cluster = _entry_cluster(entry)
                if child_cluster < 2 or child_cluster >= geometry["cluster_count"] + 2:
                    _add_warning(
                        warnings,
                        f"Active subdirectory entry at {entry_offset} has an invalid first cluster; skipped.",
                    )
                    directory_scan_complete = False
                    continue
                if depth >= MAX_DIRECTORY_DEPTH:
                    if not depth_limit_reported:
                        _add_warning(warnings, f"Stopped descending at the {MAX_DIRECTORY_DEPTH}-level depth limit.")
                        depth_limit_reported = True
                    directory_scan_complete = False
                    continue
                if child_cluster in scheduled_starts:
                    continue
                if len(scheduled_starts) >= MAX_DIRECTORY_COUNT:
                    if not count_limit_reported:
                        _add_warning(warnings, f"Stopped queuing subdirectories at the {MAX_DIRECTORY_COUNT}-directory safety limit.")
                        count_limit_reported = True
                    directory_scan_complete = False
                    continue
                scheduled_starts.add(child_cluster)
                pending_directories.append((child_cluster, depth + 1))
            if stop_directory:
                break

    if not directory_scan_complete:
        _add_warning(
            warnings,
            "Directory traversal was incomplete; extraction was skipped to avoid reading ranges that may overlap uninspected directory data.",
        )
        return deleted_seen, warnings, scanned_directory_count, total_directory_bytes

    sorted_directory_clusters = sorted(scanned_directory_clusters)
    for entry_offset, directory_cluster, depth, entry, long_name, long_name_status in deleted_entries:
        if len(rows) >= MAX_CANDIDATES:
            _add_warning(warnings, f"Stopped after the {MAX_CANDIDATES}-candidate safety limit.")
            break
        file_size = struct.unpack_from("<I", entry, 28)[0]
        first_cluster = _entry_cluster(entry)
        extension = _extension(entry)
        if file_size > MAX_RECOVERED_FILE_BYTES:
            _add_warning(
                warnings,
                f"Deleted entry at {entry_offset} declares {file_size} bytes, over the 256 MiB per-file limit; skipped.",
            )
            continue
        if total_recovered_bytes + file_size > MAX_TOTAL_RECOVERED_BYTES:
            _add_warning(warnings, "Stopped before exceeding the 1 GiB total-recovery safety limit.")
            break
        if file_size == 0:
            data_offset = geometry["data_start"]
        else:
            if first_cluster < 2 or first_cluster >= geometry["cluster_count"] + 2:
                _add_warning(warnings, f"Deleted entry at {entry_offset} has an invalid first cluster; skipped.")
                continue
            data_offset = geometry["data_start"] + (first_cluster - 2) * cluster_size
            data_end = data_offset + file_size
            if data_end > geometry["data_end"] or data_end > len(image):
                _add_warning(warnings, f"Deleted entry at {entry_offset} exceeds the contiguous data region; skipped.")
                continue
            end_cluster = first_cluster + (file_size + cluster_size - 1) // cluster_size
            overlap_index = bisect_left(sorted_directory_clusters, first_cluster)
            if (
                overlap_index < len(sorted_directory_clusters)
                and sorted_directory_clusters[overlap_index] < end_cluster
            ):
                _add_warning(
                    warnings,
                    f"Deleted entry at {entry_offset} overlaps an active directory cluster; skipped.",
                )
                continue

        filename = _candidate_filename(long_name, extension, partition_number, entry_offset)
        target = output / filename
        view = memoryview(image)[data_offset : data_offset + file_size]
        digest = hashlib.sha256(view).hexdigest()
        try:
            with target.open("xb") as handle:
                handle.write(view)
        except Exception:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        finally:
            view.release()
        total_recovered_bytes += file_size
        rows.append({
            "filename": filename,
            "format": extension[1:],
            "offset": data_offset,
            "end_offset_exclusive": data_offset + file_size,
            "size_bytes": file_size,
            "complete_boundary": True,
            "format_valid": None,
            "validation_note": (
                "Experimental FAT32 deleted short entry; file data was assumed contiguous and not format-validated; "
                "reconstructed LFN checksum cannot be verified because the short-name first byte was erased"
                if long_name
                else "Experimental FAT32 deleted short entry; file data was assumed contiguous and not format-validated"
            ),
            "sha256": digest,
            "partition_number": partition_number,
            "directory_entry_offset": entry_offset,
            "directory_cluster": directory_cluster,
            "directory_depth": depth,
            "original_long_filename": long_name or "",
            "long_filename_status": long_name_status,
            "first_cluster": first_cluster,
            "recovery_assumption": "active directory chain; contiguous file data; deleted short-alias first byte unavailable",
        })
    return deleted_seen, warnings, scanned_directory_count, total_directory_bytes


def recover_deleted_fat32(image_path: Path, output_dir: Path) -> Fat32RecoveryResult:
    """Recover deleted short-file entries from FAT32 root and active subdirectories.

    The source must be a regular raw image file. The image is memory-mapped read-only.
    This experimental version assumes each file's data occupies contiguous clusters;
    deleted directories are not traversed; LFN reconstruction is best-effort.
    """
    source = image_path.expanduser().resolve(strict=True)
    source_stat = source.stat()
    if not stat.S_ISREG(source_stat.st_mode):
        raise ValueError("Only regular image files are supported; physical devices are not supported.")
    if source_stat.st_size < 512:
        raise ValueError("Image file is too small to contain a FAT32 boot sector.")
    structure = inspect_image(source)
    fat_volumes = [volume for volume in structure.volumes if volume.filesystem == "FAT32"]
    if not fat_volumes:
        raise ValueError("No supported FAT32 volume was identified in this image.")

    destination = output_dir.expanduser().resolve()
    if destination == source.parent:
        raise ValueError("Output directory cannot be the source image directory.")
    if destination.exists() and not destination.is_dir():
        raise ValueError("Output path exists but is not a directory.")
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise FileExistsError("Output directory must be empty to prevent overwriting or mixing runs.")

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    deleted_entries_seen = 0
    directories_scanned = 0
    directory_bytes_scanned = 0
    with source.open("rb") as handle:
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as image:
            for volume in fat_volumes:
                partition = _partition_for(volume, structure)
                if partition is None:
                    available = len(image) - volume.offset_bytes
                    partition_number = 0
                else:
                    if not partition.within_image:
                        warnings.append(f"Partition {partition.number} extends beyond the image; skipped.")
                        continue
                    available = min(partition.size_bytes, len(image) - volume.offset_bytes)
                    partition_number = partition.number
                try:
                    seen, volume_warnings, scanned_dirs, scanned_bytes = _recover_volume(
                        image, volume, available, partition_number, destination, rows
                    )
                    deleted_entries_seen += seen
                    directories_scanned += scanned_dirs
                    directory_bytes_scanned += scanned_bytes
                    warnings.extend(volume_warnings)
                except ValueError as error:
                    warnings.append(f"FAT32 volume at byte offset {volume.offset_bytes} was not recovered: {error}")

    if not rows:
        warnings.append("No recoverable deleted short-file entries were found in supported FAT32 directories.")
    return Fat32RecoveryResult(
        rows,
        warnings,
        deleted_entries_seen,
        directories_scanned,
        directory_bytes_scanned,
    )
