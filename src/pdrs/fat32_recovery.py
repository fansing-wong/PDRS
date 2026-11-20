"""Experimental recovery of deleted FAT32 root-directory short entries."""
from __future__ import annotations

import hashlib
import mmap
import stat
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pdrs.structure import ImageStructure, Partition, VolumeInfo, inspect_image

MAX_ROOT_DIRECTORY_BYTES = 64 * 1024 * 1024
MAX_RECOVERED_FILE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_RECOVERED_BYTES = 1024 * 1024 * 1024
MAX_CANDIDATES = 10000
FAT32_EOC_MIN = 0x0FFFFFF8
FAT32_BAD_CLUSTER = 0x0FFFFFF7


@dataclass(frozen=True)
class Fat32RecoveryResult:
    rows: list[dict[str, Any]]
    warnings: list[str]
    deleted_entries_seen: int


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


def _root_chain(
    image: mmap.mmap,
    *,
    fat_start: int,
    fat_bytes: int,
    root_cluster: int,
    cluster_count: int,
    cluster_size: int,
) -> list[int]:
    clusters: list[int] = []
    seen: set[int] = set()
    current = root_cluster
    while True:
        if current < 2 or current >= cluster_count + 2 or current in seen:
            raise ValueError("FAT32 root directory chain contains an invalid or repeated cluster.")
        if (len(clusters) + 1) * cluster_size > MAX_ROOT_DIRECTORY_BYTES:
            raise ValueError("FAT32 root directory chain exceeds the 64 MiB inspection limit.")
        clusters.append(current)
        seen.add(current)
        next_cluster = _fat_entry(image, fat_start, fat_bytes, current)
        if next_cluster >= FAT32_EOC_MIN:
            break
        if next_cluster in (0, 1, FAT32_BAD_CLUSTER) or next_cluster >= 0x0FFFFFF0:
            raise ValueError("FAT32 root directory chain contains a free, bad, or reserved cluster.")
        current = next_cluster
        if len(clusters) > cluster_count:
            raise ValueError("FAT32 root directory chain exceeds the declared cluster count.")
    return clusters


def _extension(entry: bytes) -> str:
    raw = entry[8:11].decode("ascii", errors="ignore").strip().lower()
    if not raw or any(not (char.isalnum() or char in "_$~-") for char in raw):
        return ".bin"
    return f".{raw}"


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
) -> tuple[int, list[str]]:
    warnings: list[str] = []
    geometry = _volume_geometry(image, volume, available_bytes)
    cluster_size = geometry["cluster_size"]
    root_clusters = _root_chain(
        image,
        fat_start=geometry["fat_start"],
        fat_bytes=geometry["fat_bytes"],
        root_cluster=geometry["root_cluster"],
        cluster_count=geometry["cluster_count"],
        cluster_size=cluster_size,
    )
    deleted_seen = 0
    total_recovered_bytes = sum(int(row["size_bytes"]) for row in rows)
    stop_directory = False
    for directory_cluster in root_clusters:
        directory_offset = geometry["data_start"] + (directory_cluster - 2) * cluster_size
        directory_end = directory_offset + cluster_size
        if directory_offset < geometry["data_start"] or directory_end > geometry["data_end"]:
            raise ValueError("FAT32 root directory cluster lies outside the data region.")
        for entry_offset in range(directory_offset, directory_end, 32):
            entry = image[entry_offset : entry_offset + 32]
            first_byte = entry[0]
            if first_byte == 0x00:
                stop_directory = True
                break
            if first_byte != 0xE5:
                continue
            attributes = entry[11]
            if attributes == 0x0F or attributes & 0x18:
                continue
            deleted_seen += 1
            if len(rows) >= MAX_CANDIDATES:
                warnings.append(f"Stopped after the {MAX_CANDIDATES}-candidate safety limit.")
                return deleted_seen, warnings

            file_size = struct.unpack_from("<I", entry, 28)[0]
            first_cluster = (
                (struct.unpack_from("<H", entry, 20)[0] & 0x0FFF) << 16
            ) | struct.unpack_from("<H", entry, 26)[0]
            extension = _extension(entry)
            if file_size > MAX_RECOVERED_FILE_BYTES:
                warnings.append(
                    f"Deleted entry at {entry_offset} declares {file_size} bytes, over the 256 MiB per-file limit; skipped."
                )
                continue
            if total_recovered_bytes + file_size > MAX_TOTAL_RECOVERED_BYTES:
                warnings.append("Stopped before exceeding the 1 GiB total-recovery safety limit.")
                return deleted_seen, warnings
            if file_size == 0:
                data_offset = geometry["data_start"]
            else:
                if first_cluster < 2 or first_cluster >= geometry["cluster_count"] + 2:
                    warnings.append(f"Deleted entry at {entry_offset} has an invalid first cluster; skipped.")
                    continue
                data_offset = geometry["data_start"] + (first_cluster - 2) * cluster_size
                data_end = data_offset + file_size
                if data_end > geometry["data_end"] or data_end > len(image):
                    warnings.append(f"Deleted entry at {entry_offset} exceeds the contiguous data region; skipped.")
                    continue

            filename = f"deleted_p{partition_number:02d}_entry_{entry_offset:012x}{extension}"
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
                "validation_note": "Experimental FAT32 deleted root 8.3 entry; file data was assumed contiguous and not format-validated",
                "sha256": digest,
                "partition_number": partition_number,
                "directory_entry_offset": entry_offset,
                "first_cluster": first_cluster,
                "recovery_assumption": "contiguous cluster data; original first filename character unavailable",
            })
        if stop_directory:
            break
    return deleted_seen, warnings


def recover_deleted_fat32(image_path: Path, output_dir: Path) -> Fat32RecoveryResult:
    """Recover deleted short-file entries from FAT32 root directories only.

    The source must be a regular raw image file. The image is memory-mapped read-only.
    This experimental version assumes each file's data occupies contiguous clusters.
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
                    seen, volume_warnings = _recover_volume(
                        image, volume, available, partition_number, destination, rows
                    )
                    deleted_entries_seen += seen
                    warnings.extend(volume_warnings)
                except ValueError as error:
                    warnings.append(f"FAT32 volume at byte offset {volume.offset_bytes} was not recovered: {error}")

    if not rows:
        warnings.append("No recoverable deleted short-file entries were found in supported FAT32 root directories.")
    return Fat32RecoveryResult(rows, warnings, deleted_entries_seen)
