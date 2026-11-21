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
MAX_DELETED_DIRECTORY_COUNT = 256
MAX_DELETED_DIRECTORY_BYTES = 64 * 1024 * 1024
MAX_RECOVERED_FILE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_RECOVERED_BYTES = 1024 * 1024 * 1024
MAX_ACTIVE_FILE_REFERENCE_CLUSTERS = 1_000_000
MAX_RECOVERED_CLUSTER_REFERENCES = 1_000_000
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


def _fat_data_layout(
    image: mmap.mmap,
    *,
    fat_start: int,
    fat_bytes: int,
    first_cluster: int,
    required_clusters: int,
    cluster_count: int,
) -> str:
    """Classify only the FAT links needed to read a deleted file's declared size.

    A visible non-contiguous link is enough to refuse contiguous extraction. Cleared
    free entries retain the explicit contiguous-data assumption; other malformed
    links are rejected.
    """
    if required_clusters <= 1:
        return "single_cluster"
    current = first_cluster
    for _ in range(required_clusters - 1):
        try:
            next_cluster = _fat_entry(image, fat_start, fat_bytes, current)
        except ValueError:
            return "invalid_fat_chain_skipped"
        if next_cluster in (0, 1):
            return "fat_chain_cleared"
        if next_cluster >= FAT32_EOC_MIN:
            return "truncated_fat_chain_skipped"
        if next_cluster == FAT32_BAD_CLUSTER or 0x0FFFFFF0 <= next_cluster < FAT32_EOC_MIN:
            return "invalid_fat_chain_skipped"
        if next_cluster < 2 or next_cluster >= cluster_count + 2:
            return "invalid_fat_chain_skipped"
        if next_cluster != current + 1:
            return "fragmented_chain_skipped"
        current = next_cluster
    return "contiguous_fat_links"


def _fat_chain_layout(
    image: mmap.mmap,
    *,
    fat_start: int,
    fat_bytes: int,
    first_cluster: int,
    required_clusters: int,
    cluster_count: int,
) -> tuple[str, list[int]]:
    """Return the bounded FAT chain needed for a file's declared byte length."""
    if required_clusters <= 0:
        return "zero_length", []
    if first_cluster < 2 or first_cluster >= cluster_count + 2:
        return "invalid_fat_chain_skipped", []
    if required_clusters == 1:
        return "single_cluster", [first_cluster]
    chain = [first_cluster]
    seen = {first_cluster}
    fragmented = False
    current = first_cluster
    for _ in range(required_clusters - 1):
        try:
            next_cluster = _fat_entry(image, fat_start, fat_bytes, current)
        except ValueError:
            return "invalid_fat_chain_skipped", chain
        if next_cluster in (0, 1):
            if fragmented:
                return "fragmented_chain_incomplete_skipped", chain
            return "fat_chain_cleared", chain
        if next_cluster >= FAT32_EOC_MIN:
            return "truncated_fat_chain_skipped", chain
        if next_cluster == FAT32_BAD_CLUSTER or 0x0FFFFFF0 <= next_cluster < FAT32_EOC_MIN:
            return "invalid_fat_chain_skipped", chain
        if next_cluster < 2 or next_cluster >= cluster_count + 2 or next_cluster in seen:
            return "invalid_fat_chain_skipped", chain
        fragmented |= next_cluster != current + 1
        chain.append(next_cluster)
        seen.add(next_cluster)
        current = next_cluster
    if len(chain) != required_clusters:
        return "invalid_fat_chain_skipped", chain
    return ("fragmented_chain_reassembled" if fragmented else "contiguous_fat_links"), chain


def _active_file_cluster_map(
    image: mmap.mmap,
    *,
    fat_start: int,
    fat_bytes: int,
    cluster_count: int,
    cluster_size: int,
    file_entries: list[tuple[int, int, int]],
) -> tuple[set[int], bool, list[str]]:
    """Map clusters referenced by active regular files, within a fixed memory bound."""
    clusters: set[int] = set()
    warnings: list[str] = []
    complete = True
    references = 0
    for entry_offset, first_cluster, file_size in file_entries:
        required = (file_size + cluster_size - 1) // cluster_size
        if required <= 0:
            continue
        if required > MAX_ACTIVE_FILE_REFERENCE_CLUSTERS - references:
            complete = False
            _add_warning(
                warnings,
                f"Active-file FAT mapping exceeded the {MAX_ACTIVE_FILE_REFERENCE_CLUSTERS:,}-cluster safety limit; fragmented reassembly is disabled.",
            )
            break
        status, chain = _fat_chain_layout(
            image,
            fat_start=fat_start,
            fat_bytes=fat_bytes,
            first_cluster=first_cluster,
            required_clusters=required,
            cluster_count=cluster_count,
        )
        if status not in {"single_cluster", "contiguous_fat_links", "fragmented_chain_reassembled"}:
            complete = False
            _add_warning(
                warnings,
                f"Active file at directory entry {entry_offset} could not be mapped completely ({status}); fragmented reassembly is disabled.",
            )
            continue
        clusters.update(chain)
        references += len(chain)
    return clusters, complete, warnings


def _source_extents(
    clusters: list[int], *, file_size: int, cluster_size: int, data_start: int, data_end: int
) -> list[tuple[int, int]] | None:
    """Convert logical cluster order into merged physical (offset, length) extents."""
    remaining = file_size
    extents: list[tuple[int, int]] = []
    for cluster in clusters:
        if remaining <= 0:
            break
        offset = data_start + (cluster - 2) * cluster_size
        length = min(cluster_size, remaining)
        if offset < data_start or offset + length > data_end:
            return None
        if extents and extents[-1][0] + extents[-1][1] == offset:
            previous_offset, previous_length = extents[-1]
            extents[-1] = (previous_offset, previous_length + length)
        else:
            extents.append((offset, length))
        remaining -= length
    return extents if remaining == 0 else None


def _scan_deleted_directory_chains(
    image: mmap.mmap,
    *,
    fat_start: int,
    fat_bytes: int,
    cluster_count: int,
    cluster_size: int,
    data_start: int,
    data_end: int,
    deleted_directories: list[tuple[int, int, int, bytes]],
    active_directory_clusters: set[int],
    active_file_clusters: set[int],
) -> tuple[
    list[tuple[int, int, int, bytes, str | None, str, bool, int | None]],
    list[tuple[int, int, int]],
    set[int],
    list[str],
    int,
    int,
]:
    """Read direct deleted-file entries from bounded, non-overlapping deleted directories."""
    candidates: list[tuple[int, int, int, bytes, str | None, str, bool, int | None]] = []
    active_file_entries: list[tuple[int, int, int]] = []
    deleted_directory_clusters: set[int] = set()
    warnings: list[str] = []
    scanned_directories = 0
    scanned_bytes = 0
    candidate_limit_reported = False

    for directory_entry_offset, _parent_cluster, parent_depth, entry in deleted_directories:
        if scanned_directories >= MAX_DELETED_DIRECTORY_COUNT:
            _add_warning(
                warnings,
                f"Stopped after the {MAX_DELETED_DIRECTORY_COUNT}-deleted-directory safety limit.",
            )
            break
        first_cluster = _entry_cluster(entry)
        if first_cluster < 2 or first_cluster >= cluster_count + 2:
            _add_warning(
                warnings,
                f"Deleted directory at entry {directory_entry_offset} has an invalid first cluster; skipped.",
            )
            continue
        try:
            chain = _directory_chain(
                image,
                fat_start=fat_start,
                fat_bytes=fat_bytes,
                start_cluster=first_cluster,
                cluster_count=cluster_count,
                cluster_size=cluster_size,
            )
        except ValueError as error:
            _add_warning(
                warnings,
                f"Deleted directory at entry {directory_entry_offset} was skipped: {error}",
            )
            continue
        chain_bytes = len(chain) * cluster_size
        if scanned_bytes + chain_bytes > MAX_DELETED_DIRECTORY_BYTES:
            _add_warning(
                warnings,
                "Stopped before exceeding the 64 MiB deleted-directory scan limit.",
            )
            break
        conflict = next(
            (
                cluster
                for cluster in chain
                if cluster in active_directory_clusters
                or cluster in active_file_clusters
                or cluster in deleted_directory_clusters
            ),
            None,
        )
        if conflict is not None:
            _add_warning(
                warnings,
                f"Deleted directory at entry {directory_entry_offset} overlaps active or already scanned cluster {conflict}; skipped.",
            )
            continue
        deleted_directory_clusters.update(chain)
        scanned_directories += 1
        scanned_bytes += chain_bytes

        stop_chain = False
        pending_lfn_slots: list[bytes] = []
        for directory_cluster in chain:
            directory_offset = data_start + (directory_cluster - 2) * cluster_size
            if directory_offset < data_start or directory_offset + cluster_size > data_end:
                _add_warning(
                    warnings,
                    f"Deleted directory at entry {directory_entry_offset} has a cluster outside the data region; skipped.",
                )
                stop_chain = True
                break
            for child_offset in range(directory_offset, directory_offset + cluster_size, 32):
                child_entry = image[child_offset : child_offset + 32]
                first_byte = child_entry[0]
                if first_byte == 0x00:
                    pending_lfn_slots.clear()
                    stop_chain = True
                    break
                attributes = child_entry[11]
                if attributes == 0x0F:
                    if first_byte == 0xE5:
                        if len(pending_lfn_slots) <= MAX_LFN_ENTRIES:
                            pending_lfn_slots.append(child_entry)
                    else:
                        pending_lfn_slots.clear()
                    continue
                if first_byte == 0xE5:
                    if attributes & 0x18:
                        pending_lfn_slots.clear()
                        continue
                    long_name, long_name_status = _decode_deleted_lfn(pending_lfn_slots)
                    if pending_lfn_slots and long_name_status == "invalid":
                        _add_warning(
                            warnings,
                            f"Deleted LFN slots before entry {child_offset} were incomplete or invalid.",
                        )
                    if len(candidates) < MAX_CANDIDATES:
                        candidates.append((
                            child_offset,
                            directory_cluster,
                            parent_depth + 1,
                            child_entry,
                            long_name,
                            long_name_status,
                            True,
                            first_cluster,
                        ))
                    elif not candidate_limit_reported:
                        _add_warning(
                            warnings,
                            f"Only the first {MAX_CANDIDATES} deleted entries will be considered.",
                        )
                        candidate_limit_reported = True
                    pending_lfn_slots.clear()
                    continue

                pending_lfn_slots.clear()
                if attributes & 0x08 or attributes & 0x10 or _is_dot_directory(child_entry):
                    continue
                file_size = struct.unpack_from("<I", child_entry, 28)[0]
                if file_size:
                    active_file_entries.append((child_offset, _entry_cluster(child_entry), file_size))
            if stop_chain:
                break
    return (
        candidates,
        active_file_entries,
        deleted_directory_clusters,
        warnings,
        scanned_directories,
        scanned_bytes,
    )


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
    *,
    reassemble_fragmented: bool = False,
    scan_deleted_directories: bool = False,
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
    deleted_directory_limit_reported = False
    directory_scan_complete = True
    deleted_entries: list[
        tuple[int, int, int, bytes, str | None, str, bool, int | None]
    ] = []
    deleted_directories: list[tuple[int, int, int, bytes]] = []
    active_file_entries: list[tuple[int, int, int]] = []

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
                    if attributes == 0x0F or attributes & 0x08:
                        pending_lfn_slots.clear()
                        continue
                    if attributes & 0x10:
                        if scan_deleted_directories:
                            if len(deleted_directories) < MAX_DELETED_DIRECTORY_COUNT:
                                deleted_directories.append(
                                    (entry_offset, directory_cluster, depth, entry)
                                )
                            elif not deleted_directory_limit_reported:
                                _add_warning(
                                    warnings,
                                    f"Only the first {MAX_DELETED_DIRECTORY_COUNT} deleted directory entries will be considered.",
                                )
                                deleted_directory_limit_reported = True
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
                            False,
                            None,
                        ))
                    elif not candidate_limit_reported:
                        _add_warning(warnings, f"Only the first {MAX_CANDIDATES} deleted entries will be considered.")
                        candidate_limit_reported = True
                    pending_lfn_slots.clear()
                    continue

                pending_lfn_slots.clear()
                if attributes == 0x0F or attributes & 0x08 or _is_dot_directory(entry):
                    continue
                child_cluster = _entry_cluster(entry)
                if not attributes & 0x10:
                    active_file_size = struct.unpack_from("<I", entry, 28)[0]
                    if active_file_size:
                        active_file_entries.append((entry_offset, child_cluster, active_file_size))
                    continue
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
    active_file_clusters: set[int] = set()
    active_file_map_complete = True
    recovered_data_clusters: set[int] = set()
    if reassemble_fragmented or scan_deleted_directories:
        active_file_clusters, active_file_map_complete, map_warnings = _active_file_cluster_map(
            image,
            fat_start=geometry["fat_start"],
            fat_bytes=geometry["fat_bytes"],
            cluster_count=geometry["cluster_count"],
            cluster_size=cluster_size,
            file_entries=active_file_entries,
        )
        warnings.extend(map_warnings)
    deleted_directory_clusters: set[int] = set()
    if scan_deleted_directories:
        if not active_file_map_complete:
            _add_warning(
                warnings,
                "Deleted directories were not scanned because active-file allocation could not be mapped completely.",
            )
        else:
            (
                orphan_candidates,
                orphan_active_file_entries,
                deleted_directory_clusters,
                deleted_directory_warnings,
                orphan_directory_count,
                orphan_directory_bytes,
            ) = _scan_deleted_directory_chains(
                image,
                fat_start=geometry["fat_start"],
                fat_bytes=geometry["fat_bytes"],
                cluster_count=geometry["cluster_count"],
                cluster_size=cluster_size,
                data_start=geometry["data_start"],
                data_end=geometry["data_end"],
                deleted_directories=deleted_directories,
                active_directory_clusters=scanned_directory_clusters,
                active_file_clusters=active_file_clusters,
            )
            warnings.extend(deleted_directory_warnings)
            scanned_directory_count += orphan_directory_count
            total_directory_bytes += orphan_directory_bytes
            deleted_seen += len(orphan_candidates)
            deleted_directory_scan_safe = True
            if orphan_active_file_entries:
                orphan_file_clusters, orphan_map_complete, orphan_map_warnings = _active_file_cluster_map(
                    image,
                    fat_start=geometry["fat_start"],
                    fat_bytes=geometry["fat_bytes"],
                    cluster_count=geometry["cluster_count"],
                    cluster_size=cluster_size,
                    file_entries=orphan_active_file_entries,
                )
                warnings.extend(orphan_map_warnings)
                shared_directory_cluster = next(
                    iter(orphan_file_clusters & deleted_directory_clusters),
                    None,
                )
                if shared_directory_cluster is not None:
                    deleted_directory_scan_safe = False
                    _add_warning(
                        warnings,
                        "Deleted-directory candidates were withheld because an active file inside a scanned deleted directory shares a cluster with a scanned directory chain.",
                    )
                if len(active_file_clusters | orphan_file_clusters) > MAX_ACTIVE_FILE_REFERENCE_CLUSTERS:
                    active_file_map_complete = False
                    _add_warning(
                        warnings,
                        f"Active-file allocation exceeds the {MAX_ACTIVE_FILE_REFERENCE_CLUSTERS:,}-cluster combined safety limit.",
                    )
                else:
                    active_file_clusters.update(orphan_file_clusters)
                    active_file_map_complete = active_file_map_complete and orphan_map_complete
            if deleted_directory_scan_safe:
                deleted_entries.extend(orphan_candidates)
    safety_checks = reassemble_fragmented or scan_deleted_directories
    for (
        entry_offset,
        directory_cluster,
        depth,
        entry,
        long_name,
        long_name_status,
        parent_deleted,
        parent_directory_cluster,
    ) in deleted_entries:
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
        if parent_deleted and not active_file_map_complete:
            _add_warning(
                warnings,
                f"Deleted-file entry at {entry_offset} was skipped because active-file allocation could not be mapped completely.",
            )
            continue
        data_clusters: list[int] = []
        if file_size == 0:
            data_offset = geometry["data_start"]
            data_layout_status = "zero_length"
            source_extents: list[tuple[int, int]] = []
        else:
            if first_cluster < 2 or first_cluster >= geometry["cluster_count"] + 2:
                _add_warning(warnings, f"Deleted entry at {entry_offset} has an invalid first cluster; skipped.")
                continue
            required_clusters = (file_size + cluster_size - 1) // cluster_size
            if reassemble_fragmented:
                data_layout_status, observed_chain = _fat_chain_layout(
                    image,
                    fat_start=geometry["fat_start"],
                    fat_bytes=geometry["fat_bytes"],
                    first_cluster=first_cluster,
                    required_clusters=required_clusters,
                    cluster_count=geometry["cluster_count"],
                )
                if data_layout_status == "fat_chain_cleared":
                    if first_cluster + required_clusters > geometry["cluster_count"] + 2:
                        _add_warning(warnings, f"Deleted entry at {entry_offset} exceeds the contiguous data region; skipped.")
                        continue
                    data_clusters = list(range(first_cluster, first_cluster + required_clusters))
                elif data_layout_status in {
                    "fragmented_chain_incomplete_skipped",
                    "truncated_fat_chain_skipped",
                    "invalid_fat_chain_skipped",
                }:
                    _add_warning(
                        warnings,
                        f"Deleted entry at {entry_offset} has an incomplete or invalid FAT chain ({data_layout_status}); skipped.",
                    )
                    continue
                else:
                    data_clusters = observed_chain
                if data_layout_status == "fragmented_chain_reassembled" and not active_file_map_complete:
                    _add_warning(
                        warnings,
                        f"Deleted entry at {entry_offset} has a fragmented chain, but active-file allocation could not be mapped completely; skipped.",
                    )
                    continue
                if len(recovered_data_clusters) + len(data_clusters) > MAX_RECOVERED_CLUSTER_REFERENCES:
                    _add_warning(
                        warnings,
                        f"Stopped before exceeding the {MAX_RECOVERED_CLUSTER_REFERENCES:,}-cluster overlap-tracking limit.",
                    )
                    break
                conflict = next(
                    (
                        cluster
                        for cluster in data_clusters
                        if cluster in scanned_directory_clusters
                        or cluster in deleted_directory_clusters
                        or cluster in active_file_clusters
                        or cluster in recovered_data_clusters
                    ),
                    None,
                )
                if conflict is not None:
                    if conflict in scanned_directory_clusters:
                        conflict_kind = "an active directory"
                    elif conflict in deleted_directory_clusters:
                        conflict_kind = "a scanned deleted-directory"
                    elif conflict in active_file_clusters:
                        conflict_kind = "an active file"
                    else:
                        conflict_kind = "another recovered candidate"
                    _add_warning(
                        warnings,
                        f"Deleted entry at {entry_offset} overlaps {conflict_kind} cluster {conflict}; skipped.",
                    )
                    continue
                source_extents = _source_extents(
                    data_clusters,
                    file_size=file_size,
                    cluster_size=cluster_size,
                    data_start=geometry["data_start"],
                    data_end=geometry["data_end"],
                )
                if source_extents is None:
                    _add_warning(warnings, f"Deleted entry at {entry_offset} exceeds the data region; skipped.")
                    continue
            else:
                data_layout_status = _fat_data_layout(
                    image,
                    fat_start=geometry["fat_start"],
                    fat_bytes=geometry["fat_bytes"],
                    first_cluster=first_cluster,
                    required_clusters=required_clusters,
                    cluster_count=geometry["cluster_count"],
                )
                if data_layout_status in {
                    "fragmented_chain_skipped",
                    "truncated_fat_chain_skipped",
                    "invalid_fat_chain_skipped",
                }:
                    reason = {
                        "fragmented_chain_skipped": "a visible non-contiguous FAT link",
                        "truncated_fat_chain_skipped": "a FAT end marker before the declared file size",
                        "invalid_fat_chain_skipped": "an invalid FAT link",
                    }[data_layout_status]
                    _add_warning(
                        warnings,
                        f"Deleted entry at {entry_offset} has {reason}; skipped instead of assuming a contiguous range.",
                    )
                    continue
                data_offset = geometry["data_start"] + (first_cluster - 2) * cluster_size
                data_end = data_offset + file_size
                if data_end > geometry["data_end"] or data_end > len(image):
                    _add_warning(warnings, f"Deleted entry at {entry_offset} exceeds the contiguous data region; skipped.")
                    continue
                data_clusters = list(range(first_cluster, first_cluster + required_clusters)) if safety_checks else []
                if not safety_checks:
                    end_cluster = first_cluster + required_clusters
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
                source_extents = [(data_offset, file_size)]
                if safety_checks:
                    if len(recovered_data_clusters) + len(data_clusters) > MAX_RECOVERED_CLUSTER_REFERENCES:
                        _add_warning(
                            warnings,
                            f"Stopped before exceeding the {MAX_RECOVERED_CLUSTER_REFERENCES:,}-cluster overlap-tracking limit.",
                        )
                        break
                    conflict = next(
                        (
                            cluster
                            for cluster in data_clusters
                            if cluster in scanned_directory_clusters
                            or cluster in deleted_directory_clusters
                            or cluster in active_file_clusters
                            or cluster in recovered_data_clusters
                        ),
                        None,
                    )
                    if conflict is not None:
                        _add_warning(
                            warnings,
                            f"Deleted entry at {entry_offset} overlaps protected cluster {conflict}; skipped.",
                        )
                        continue

        data_offset = source_extents[0][0] if source_extents else geometry["data_start"]
        end_offset_exclusive = (
            data_offset + file_size if file_size == 0 or len(source_extents) == 1 else None
        )

        filename = _candidate_filename(long_name, extension, partition_number, entry_offset)
        target = output / filename
        digest = hashlib.sha256()
        try:
            with target.open("xb") as handle:
                for extent_offset, extent_length in source_extents:
                    view = memoryview(image)[extent_offset : extent_offset + extent_length]
                    try:
                        digest.update(view)
                        handle.write(view)
                    finally:
                        view.release()
        except Exception:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        digest_hex = digest.hexdigest()
        total_recovered_bytes += file_size
        if safety_checks:
            recovered_data_clusters.update(data_clusters)
        layout_note = {
            "zero_length": "zero-length file; no data bytes were read",
            "single_cluster": "single-cluster file",
            "contiguous_fat_links": "FAT links for the declared size are contiguous",
            "fat_chain_cleared": "FAT links are cleared; contiguous storage was assumed",
            "fragmented_chain_reassembled": "complete non-contiguous FAT chain was reassembled in logical order",
        }[data_layout_status]
        lfn_note = (
            "; reconstructed LFN is best-effort: deletion erases the short-name first byte and LFN slot ordinals, "
            "so its checksum and completeness cannot be verified and the display name may be partial"
            if long_name
            else ""
        )
        rows.append({
            "filename": filename,
            "format": extension[1:],
            "offset": data_offset,
            "end_offset_exclusive": end_offset_exclusive,
            "size_bytes": file_size,
            "complete_boundary": True,
            "format_valid": None,
            "validation_note": (
                f"Experimental FAT32 deleted short entry; {layout_note}; file format not validated{lfn_note}"
            ),
            "sha256": digest_hex,
            "source_extents": ";".join(
                f"{extent_offset}:{extent_length}" for extent_offset, extent_length in source_extents
            ),
            "partition_number": partition_number,
            "directory_entry_offset": entry_offset,
            "directory_cluster": directory_cluster,
            "directory_depth": depth,
            "original_long_filename": long_name or "",
            "long_filename_status": long_name_status,
            "parent_deleted_directory": parent_deleted,
            "parent_directory_cluster": parent_directory_cluster,
            "first_cluster": first_cluster,
            "data_layout_status": data_layout_status,
            "recovery_assumption": (
                f"active directory chain; {layout_note}{lfn_note}"
                if not parent_deleted
                else f"deleted parent directory cluster {parent_directory_cluster}; {layout_note}{lfn_note}"
            ),
        })
    return deleted_seen, warnings, scanned_directory_count, total_directory_bytes


def recover_deleted_fat32(
    image_path: Path,
    output_dir: Path,
    *,
    reassemble_fragmented: bool = False,
    scan_deleted_directories: bool = False,
) -> Fat32RecoveryResult:
    """Recover deleted short-file entries from FAT32 root and active subdirectories.

    The source must be a regular raw image file. The image is memory-mapped read-only.
    Fragmented-chain reassembly and deleted-directory scanning are opt-in. Reassembly
    requires complete surviving FAT links plus a complete active-file allocation map.
    Deleted-directory scanning follows only complete non-overlapping directory chains;
    LFN reconstruction is best-effort.
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
                        image,
                        volume,
                        available,
                        partition_number,
                        destination,
                        rows,
                        reassemble_fragmented=reassemble_fragmented,
                        scan_deleted_directories=scan_deleted_directories,
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
