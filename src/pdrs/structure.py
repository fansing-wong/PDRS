"""Read-only partition-table and filesystem metadata inspection for image files.

This module deliberately stops at partition tables, volume boot sectors, and
the ext superblock. It never reads directory entries, allocation records, or
file cluster chains.
"""

from __future__ import annotations

import json
import stat
import struct
import uuid
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import BinaryIO


MBR_PARTITION_TYPES = {
    0x01: "FAT12",
    0x04: "FAT16 (<32 MiB)",
    0x06: "FAT16",
    0x07: "NTFS/exFAT/HPFS",
    0x0B: "FAT32",
    0x0C: "FAT32 (LBA)",
    0x0E: "FAT16 (LBA)",
    0x05: "Extended",
    0x0F: "Extended (LBA)",
    0x82: "Linux swap",
    0x83: "Linux filesystem",
    0x85: "Linux extended",
    0xEE: "GPT protective",
}
GPT_ENTRY_BYTES_LIMIT = 16 * 1024 * 1024


@dataclass(frozen=True)
class Partition:
    number: int
    type_id: str
    type_name: str
    name: str
    start_lba: int
    sector_count: int
    offset_bytes: int
    size_bytes: int
    within_image: bool


@dataclass(frozen=True)
class VolumeInfo:
    partition_number: int | None
    offset_bytes: int
    filesystem: str
    volume_label: str
    serial_hex: str
    details: dict[str, int | str | bool | None]


@dataclass
class ImageStructure:
    image_path: str
    image_size_bytes: int
    partition_table: str
    sector_size: int | None
    partitions: list[Partition] = field(default_factory=list)
    volumes: list[VolumeInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _read_at(handle: BinaryIO, offset: int, length: int) -> bytes:
    handle.seek(offset)
    return handle.read(length)


def _valid_mbr_signature(sector: bytes) -> bool:
    return len(sector) >= 512 and sector[510:512] == b"\x55\xaa"


def _mbr_entries(sector: bytes, image_size: int) -> tuple[list[Partition], bool]:
    partitions: list[Partition] = []
    has_gpt_protective_entry = False
    for index in range(4):
        entry = sector[446 + index * 16 : 462 + index * 16]
        status = entry[0]
        type_code = entry[4]
        start_lba, sector_count = struct.unpack_from("<II", entry, 8)
        if type_code == 0xEE:
            has_gpt_protective_entry = True
        if status not in (0, 0x80) or type_code == 0 or sector_count == 0:
            continue
        offset = start_lba * 512
        size = sector_count * 512
        partitions.append(
            Partition(
                number=index + 1,
                type_id=f"0x{type_code:02X}",
                type_name=MBR_PARTITION_TYPES.get(type_code, "Unknown"),
                name="",
                start_lba=start_lba,
                sector_count=sector_count,
                offset_bytes=offset,
                size_bytes=size,
                within_image=start_lba > 0 and offset + size <= image_size,
            )
        )
    return partitions, has_gpt_protective_entry


def _parse_gpt(handle: BinaryIO, image_size: int, sector_size: int) -> tuple[list[Partition], list[str]] | None:
    warnings: list[str] = []
    header = _read_at(handle, sector_size, sector_size)
    if len(header) < 92 or header[:8] != b"EFI PART":
        return None

    revision, header_size, stored_header_crc = struct.unpack_from("<III", header, 8)
    if header_size < 92 or header_size > sector_size:
        return [], [f"GPT header size is invalid for {sector_size}-byte sectors."]
    header_data = bytearray(header[:header_size])
    header_data[16:20] = b"\0\0\0\0"
    if zlib.crc32(header_data) & 0xFFFFFFFF != stored_header_crc:
        return [], ["GPT header CRC check failed; partition entries were not read."]

    current_lba, backup_lba, first_usable, last_usable = struct.unpack_from("<QQQQ", header, 24)
    disk_guid = uuid.UUID(bytes_le=header[56:72])
    entries_lba, entry_count, entry_size, entries_crc = struct.unpack_from("<QIII", header, 72)
    del revision, current_lba, backup_lba, first_usable, last_usable, disk_guid

    if entry_size < 128 or entry_size > 4096 or entry_size % 8:
        return [], [f"GPT entry size {entry_size} is unsupported; partition entries were not read."]
    table_length = entry_count * entry_size
    if table_length > GPT_ENTRY_BYTES_LIMIT:
        return [], ["GPT partition-entry table exceeds the 16 MiB inspection limit."]
    table_offset = entries_lba * sector_size
    if table_offset < 0 or table_offset + table_length > image_size:
        return [], ["GPT partition-entry table extends beyond the image file."]

    raw_entries = _read_at(handle, table_offset, table_length)
    if len(raw_entries) != table_length:
        return [], ["GPT partition-entry table could not be read in full."]
    if zlib.crc32(raw_entries) & 0xFFFFFFFF != entries_crc:
        return [], ["GPT partition-entry table CRC check failed; entries were not interpreted."]

    partitions: list[Partition] = []
    for index in range(entry_count):
        entry = raw_entries[index * entry_size : (index + 1) * entry_size]
        type_guid_bytes = entry[:16]
        if type_guid_bytes == b"\0" * 16:
            continue
        unique_guid_bytes = entry[16:32]
        del unique_guid_bytes
        first_lba, last_lba, attributes = struct.unpack_from("<QQQ", entry, 32)
        del attributes
        if last_lba < first_lba:
            warnings.append(f"GPT partition entry {index + 1} has a reversed LBA range and was ignored.")
            continue
        type_guid = uuid.UUID(bytes_le=type_guid_bytes)
        name = entry[56:128].decode("utf-16le", errors="replace").rstrip("\0 ")
        offset = first_lba * sector_size
        size = (last_lba - first_lba + 1) * sector_size
        partitions.append(
            Partition(
                number=index + 1,
                type_id=str(type_guid),
                type_name="GPT partition",
                name=name,
                start_lba=first_lba,
                sector_count=last_lba - first_lba + 1,
                offset_bytes=offset,
                size_bytes=size,
                within_image=offset + size <= image_size,
            )
        )
    return partitions, warnings


def _exfat_boot_region_checksum(
    handle: BinaryIO,
    volume_offset: int,
    available_bytes: int,
    bytes_per_sector: int,
    region_start_sector: int,
) -> bool | None:
    """Validate the checksum sector for one 12-sector exFAT boot region."""
    region_bytes = 12 * bytes_per_sector
    relative_offset = region_start_sector * bytes_per_sector
    if relative_offset + region_bytes > available_bytes:
        return None
    region_offset = volume_offset + relative_offset
    checksummed = _read_at(handle, region_offset, 11 * bytes_per_sector)
    checksum_sector = _read_at(
        handle, region_offset + 11 * bytes_per_sector, bytes_per_sector
    )
    if len(checksummed) != 11 * bytes_per_sector or len(checksum_sector) != bytes_per_sector:
        return None

    checksum = 0
    for index, value in enumerate(checksummed):
        if index in (106, 107, 112):
            continue
        checksum = (((checksum << 31) | (checksum >> 1)) + value) & 0xFFFFFFFF
    stored_values = {
        struct.unpack_from("<I", checksum_sector, offset)[0]
        for offset in range(0, bytes_per_sector, 4)
    }
    return stored_values == {checksum}


def _exfat_volume(
    handle: BinaryIO,
    boot: bytes,
    offset: int,
    available_bytes: int,
    partition_number: int | None,
) -> tuple[VolumeInfo, list[str]]:
    warnings: list[str] = []
    partition_offset = struct.unpack_from("<Q", boot, 64)[0]
    volume_length = struct.unpack_from("<Q", boot, 72)[0]
    fat_offset = struct.unpack_from("<I", boot, 80)[0]
    fat_length = struct.unpack_from("<I", boot, 84)[0]
    cluster_heap_offset = struct.unpack_from("<I", boot, 88)[0]
    cluster_count = struct.unpack_from("<I", boot, 92)[0]
    root_cluster = struct.unpack_from("<I", boot, 96)[0]
    serial = struct.unpack_from("<I", boot, 100)[0]
    revision = struct.unpack_from("<H", boot, 104)[0]
    bytes_per_sector_shift = boot[108]
    sectors_per_cluster_shift = boot[109]
    number_of_fats = boot[110]

    sector_shift_valid = 9 <= bytes_per_sector_shift <= 12
    bytes_per_sector = 1 << bytes_per_sector_shift if sector_shift_valid else 0
    cluster_shift_valid = (
        sector_shift_valid and sectors_per_cluster_shift <= 25 - bytes_per_sector_shift
    )
    sectors_per_cluster = 1 << sectors_per_cluster_shift if cluster_shift_valid else 0
    volume_bytes = volume_length * bytes_per_sector if bytes_per_sector else 0
    fat_region_end = fat_offset + fat_length * number_of_fats
    cluster_heap_end = cluster_heap_offset + cluster_count * sectors_per_cluster
    root_cluster_valid = root_cluster == 0 or 2 <= root_cluster < cluster_count + 2
    minimum_fat_sectors = (
        ((cluster_count + 2) * 4 + bytes_per_sector - 1) // bytes_per_sector
        if bytes_per_sector
        else 0
    )

    parameter_checks = {
        "must_be_zero_region_valid": boot[11:64] == b"\0" * 53,
        "sector_size_shift_valid": sector_shift_valid,
        "cluster_size_shift_valid": cluster_shift_valid,
        "fat_count_valid": number_of_fats in (1, 2),
        "volume_length_valid": bool(bytes_per_sector)
        and volume_length * bytes_per_sector >= 1 << 20,
        "fat_region_valid": fat_offset >= 24 and fat_length >= minimum_fat_sectors,
        "cluster_heap_follows_fat": fat_region_end <= cluster_heap_offset,
        "cluster_heap_within_volume": cluster_count > 0 and cluster_heap_end <= volume_length,
        "root_cluster_value_valid": root_cluster_valid,
    }
    if not all(parameter_checks.values()):
        warnings.append(f"exFAT boot parameters at byte offset {offset} contain invalid values.")
    if volume_bytes > available_bytes:
        warnings.append(
            f"exFAT volume at byte offset {offset} declares {volume_bytes} bytes, "
            f"but only {available_bytes} bytes are available in the image/partition."
        )

    main_checksum = None
    backup_checksum = None
    if bytes_per_sector:
        main_checksum = _exfat_boot_region_checksum(
            handle, offset, available_bytes, bytes_per_sector, 0
        )
        backup_checksum = _exfat_boot_region_checksum(
            handle, offset, available_bytes, bytes_per_sector, 12
        )
    if main_checksum is False:
        warnings.append(f"exFAT main boot-region checksum failed at byte offset {offset}.")
    elif main_checksum is None:
        warnings.append(f"exFAT main boot region is incomplete at byte offset {offset}.")
    if backup_checksum is False:
        warnings.append(f"exFAT backup boot-region checksum failed at byte offset {offset}.")
    elif backup_checksum is None:
        warnings.append(f"exFAT backup boot region is incomplete at byte offset {offset}.")

    details: dict[str, int | str | bool | None] = {
        "partition_offset_sectors": partition_offset,
        "volume_length_sectors": volume_length,
        "volume_size_bytes": volume_bytes,
        "bytes_per_sector": bytes_per_sector or "invalid shift",
        "sectors_per_cluster": sectors_per_cluster or "invalid shift",
        "cluster_size_bytes": bytes_per_sector * sectors_per_cluster,
        "fat_offset_sectors": fat_offset,
        "fat_length_sectors": fat_length,
        "number_of_fats": number_of_fats,
        "minimum_fat_length_sectors": minimum_fat_sectors,
        "cluster_heap_offset_sectors": cluster_heap_offset,
        "cluster_count": cluster_count,
        "volume_serial": f"{serial:08X}",
        "filesystem_revision": f"{revision >> 8}.{revision & 0xFF:02X}",
        **parameter_checks,
        "main_boot_checksum_valid": main_checksum,
        "backup_boot_checksum_valid": backup_checksum,
        "fits_in_image_or_partition": volume_bytes <= available_bytes,
    }
    return VolumeInfo(partition_number, offset, "exFAT", "", f"{serial:08X}", details), warnings


def _ext_volume(
    handle: BinaryIO,
    offset: int,
    available_bytes: int,
    partition_number: int | None,
) -> tuple[VolumeInfo | None, list[str]]:
    """Recognize an ext-family volume from its fixed-position superblock only."""
    warnings: list[str] = []
    superblock_offset = offset + 1024
    if available_bytes < 2048 or superblock_offset + 1024 > offset + available_bytes:
        return None, warnings
    superblock = _read_at(handle, superblock_offset, 1024)
    if len(superblock) != 1024 or struct.unpack_from("<H", superblock, 56)[0] != 0xEF53:
        return None, warnings

    inode_count = struct.unpack_from("<I", superblock, 0)[0]
    blocks_low = struct.unpack_from("<I", superblock, 4)[0]
    log_block_size = struct.unpack_from("<I", superblock, 24)[0]
    blocks_per_group = struct.unpack_from("<I", superblock, 32)[0]
    inodes_per_group = struct.unpack_from("<I", superblock, 40)[0]
    state_bits = struct.unpack_from("<H", superblock, 58)[0]
    revision = struct.unpack_from("<I", superblock, 76)[0]
    inode_size = struct.unpack_from("<H", superblock, 88)[0] if revision else 128
    feature_incompat = struct.unpack_from("<I", superblock, 96)[0]
    feature_ro_compat = struct.unpack_from("<I", superblock, 100)[0]
    blocks_high = struct.unpack_from("<I", superblock, 336)[0] if feature_incompat & 0x80 else 0

    if log_block_size > 6:
        warnings.append(f"ext superblock at byte offset {superblock_offset} has an unsupported block-size exponent.")
        return None, warnings
    block_size = 1024 << log_block_size
    block_count = (blocks_high << 32) | blocks_low
    volume_size = block_count * block_size
    valid = (
        inode_count > 0
        and block_count > 0
        and blocks_per_group > 0
        and inodes_per_group > 0
        and inode_size >= 128
        and inode_size <= block_size
        and inode_size % 4 == 0
        and revision <= 1
    )
    if not valid:
        warnings.append(f"ext superblock at byte offset {superblock_offset} has inconsistent geometry fields.")
        return None, warnings

    fits = volume_size <= available_bytes
    if not fits:
        warnings.append(
            f"ext volume at byte offset {offset} declares {volume_size} bytes, "
            f"but only {available_bytes} bytes are available in the image/partition."
        )
    has_extents = bool(feature_incompat & 0x40)
    filesystem = "ext4 (extents feature)" if has_extents else "ext filesystem (ext2/3/4-compatible)"
    if state_bits == 0x01:
        state = "clean"
    elif state_bits & 0x02:
        state = "errors recorded"
    elif state_bits == 0:
        state = "not marked clean"
    else:
        state = f"unknown (0x{state_bits:04X})"
    label = superblock[120:136].split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()
    volume_uuid = str(uuid.UUID(bytes=superblock[104:120]))
    details: dict[str, int | str | bool | None] = {
        "superblock_offset_bytes": superblock_offset,
        "block_size_bytes": block_size,
        "block_count": block_count,
        "inode_count": inode_count,
        "inode_size_bytes": inode_size,
        "blocks_per_group": blocks_per_group,
        "inodes_per_group": inodes_per_group,
        "volume_size_bytes": volume_size,
        "volume_state": state,
        "revision": revision,
        "feature_incompat_hex": f"0x{feature_incompat:08X}",
        "feature_ro_compat_hex": f"0x{feature_ro_compat:08X}",
        "extents_feature": has_extents,
        "fits_in_image_or_partition": fits,
    }
    return VolumeInfo(partition_number, offset, filesystem, label, volume_uuid, details), warnings


def _volume_at(
    handle: BinaryIO,
    image_size: int,
    offset: int,
    available_bytes: int,
    partition_number: int | None,
) -> tuple[VolumeInfo | None, list[str]]:
    warnings: list[str] = []
    if offset < 0 or offset + 512 > image_size or available_bytes < 512:
        return None, warnings
    ext_volume, ext_warnings = _ext_volume(handle, offset, available_bytes, partition_number)
    if ext_volume is not None:
        return ext_volume, ext_warnings
    warnings.extend(ext_warnings)
    boot = _read_at(handle, offset, 512)
    if len(boot) != 512 or not _valid_mbr_signature(boot):
        return None, warnings

    oem_id = boot[3:11]
    if oem_id == b"NTFS    ":
        return VolumeInfo(partition_number, offset, "NTFS", "", "", {"metadata_status": "boot sector identified; detailed parsing is not implemented"}), warnings
    if oem_id == b"EXFAT   ":
        volume, warnings = _exfat_volume(
            handle, boot, offset, available_bytes, partition_number
        )
        return volume, warnings

    bytes_per_sector = struct.unpack_from("<H", boot, 11)[0]
    sectors_per_cluster = boot[13]
    reserved_sectors = struct.unpack_from("<H", boot, 14)[0]
    fat_count = boot[16]
    root_entry_count = struct.unpack_from("<H", boot, 17)[0]
    total_sectors_16 = struct.unpack_from("<H", boot, 19)[0]
    fat_size_16 = struct.unpack_from("<H", boot, 22)[0]
    total_sectors_32 = struct.unpack_from("<I", boot, 32)[0]
    fat_size_32 = struct.unpack_from("<I", boot, 36)[0]
    root_cluster = struct.unpack_from("<I", boot, 44)[0]
    fsinfo_sector = struct.unpack_from("<H", boot, 48)[0]
    backup_boot_sector = struct.unpack_from("<H", boot, 50)[0]
    total_sectors = total_sectors_16 or total_sectors_32

    is_fat32_shape = (
        bytes_per_sector in (512, 1024, 2048, 4096)
        and sectors_per_cluster > 0
        and sectors_per_cluster <= 128
        and sectors_per_cluster & (sectors_per_cluster - 1) == 0
        and reserved_sectors > 0
        and 1 <= fat_count <= 4
        and root_entry_count == 0
        and fat_size_16 == 0
        and fat_size_32 > 0
        and total_sectors > 0
    )
    if not is_fat32_shape:
        if boot[82:90] == b"FAT32   ":
            warnings.append(f"FAT32 label found at byte offset {offset}, but BPB fields are inconsistent.")
        return None, warnings

    data_sectors = total_sectors - reserved_sectors - fat_count * fat_size_32
    if data_sectors <= 0:
        warnings.append(f"FAT32 BPB at byte offset {offset} has no data area.")
        return None, warnings
    cluster_count = data_sectors // sectors_per_cluster
    if root_cluster < 2 or root_cluster >= cluster_count + 2:
        warnings.append(f"FAT32 BPB at byte offset {offset} has an out-of-range root cluster.")
        return None, warnings

    volume_size = total_sectors * bytes_per_sector
    if volume_size > available_bytes:
        warnings.append(
            f"FAT32 volume at byte offset {offset} declares {volume_size} bytes, "
            f"but only {available_bytes} bytes are available in the image/partition."
        )

    label = boot[71:82].decode("ascii", errors="replace").strip()
    serial = struct.unpack_from("<I", boot, 67)[0]
    details: dict[str, int | str | bool | None] = {
        "bytes_per_sector": bytes_per_sector,
        "sectors_per_cluster": sectors_per_cluster,
        "reserved_sectors": reserved_sectors,
        "fat_count": fat_count,
        "sectors_per_fat": fat_size_32,
        "total_sectors": total_sectors,
        "volume_size_bytes": volume_size,
        "data_cluster_count": cluster_count,
        "root_directory_cluster": root_cluster,
        "fsinfo_sector": fsinfo_sector,
        "backup_boot_sector": backup_boot_sector,
        "fits_in_image_or_partition": volume_size <= available_bytes,
    }
    return VolumeInfo(partition_number, offset, "FAT32", label, f"{serial:08X}", details), warnings


def inspect_image(image_path: Path) -> ImageStructure:
    """Inspect MBR/GPT, ext superblocks, and FAT32/exFAT boot metadata in a regular image file."""
    source = image_path.expanduser().resolve(strict=True)
    source_stat = source.stat()
    if not stat.S_ISREG(source_stat.st_mode):
        raise ValueError("Only regular image files are supported; physical devices are not supported.")
    image_size = source_stat.st_size
    if image_size < 512:
        raise ValueError("Image file is too small to contain a partition or volume boot sector.")

    with source.open("rb") as handle:
        first_sector = _read_at(handle, 0, 512)
        has_mbr_signature = _valid_mbr_signature(first_sector)
        mbr_partitions, protective = _mbr_entries(first_sector, image_size) if has_mbr_signature else ([], False)

        structure = ImageStructure(
            image_path=str(source),
            image_size_bytes=image_size,
            partition_table="Unrecognized",
            sector_size=None,
        )

        gpt_result = None
        if protective:
            for sector_size in (512, 4096):
                gpt_result = _parse_gpt(handle, image_size, sector_size)
                if gpt_result is not None:
                    structure.partition_table = "GPT"
                    structure.sector_size = sector_size
                    structure.partitions, warnings = gpt_result
                    structure.warnings.extend(warnings)
                    break
            if gpt_result is None:
                structure.partition_table = "Protective MBR; GPT header not found"
                structure.warnings.append("Protective MBR was present, but no supported GPT header was found.")
        elif mbr_partitions:
            structure.partition_table = "MBR"
            structure.sector_size = 512
            structure.partitions = mbr_partitions
        elif has_mbr_signature:
            # A volume boot record also ends with 55 AA; recognize it by its BPB before
            # calling it an empty MBR.
            volume, warnings = _volume_at(handle, image_size, 0, image_size, None)
            structure.warnings.extend(warnings)
            if volume is not None:
                structure.partition_table = "Superfloppy volume (no partition table)"
                structure.volumes.append(volume)
            else:
                structure.partition_table = "MBR (no active partition entries)"
                structure.sector_size = 512
        else:
            volume, warnings = _volume_at(handle, image_size, 0, image_size, None)
            structure.warnings.extend(warnings)
            if volume is not None:
                structure.partition_table = "Superfloppy volume (no partition table)"
                structure.volumes.append(volume)

        if structure.partitions:
            for partition in structure.partitions:
                if not partition.within_image:
                    structure.warnings.append(
                        f"Partition {partition.number} extends beyond the image file and was not inspected."
                    )
                    continue
                if partition.type_id in {"0x05", "0x0F", "0x85"}:
                    structure.warnings.append(
                        f"Partition {partition.number} is an extended-partition container; "
                        "logical partitions were not enumerated."
                    )
                    continue
                volume, warnings = _volume_at(
                    handle,
                    image_size,
                    partition.offset_bytes,
                    partition.size_bytes,
                    partition.number,
                )
                if volume is not None:
                    structure.volumes.append(volume)
                structure.warnings.extend(warnings)

        structure.warnings.append(
            "Inspection is limited to partition tables, volume boot sectors, and ext superblocks; "
            "directories, deleted records, file data, and cluster chains are not read."
        )
        return structure


def format_report(report: ImageStructure) -> str:
    """Return a compact human-readable report shared by CLI and GUI."""
    lines = [
        "PDRS 镜像结构只读摘要",
        f"镜像文件：{report.image_path}",
        f"文件大小：{report.image_size_bytes:,} bytes",
        f"分区表：{report.partition_table}",
        f"分区扇区大小：{report.sector_size or '未确定'} bytes",
        "",
        f"分区数量：{len(report.partitions)}",
    ]
    for partition in report.partitions:
        title = f"分区 {partition.number}"
        if partition.name:
            title += f"（{partition.name}）"
        lines.extend(
            [
                title,
                f"  类型：{partition.type_name} [{partition.type_id}]",
                f"  起始 LBA：{partition.start_lba:,}；扇区数：{partition.sector_count:,}",
                f"  镜像偏移：{partition.offset_bytes:,}；大小：{partition.size_bytes:,} bytes",
                f"  完全位于镜像内：{'是' if partition.within_image else '否'}",
            ]
        )
    lines.extend(["", f"识别到的卷：{len(report.volumes)}"])
    for volume in report.volumes:
        lines.append(
            f"{volume.filesystem} 卷（分区 {volume.partition_number or '无'}，"
            f"偏移 {volume.offset_bytes:,} bytes）"
        )
        if volume.volume_label:
            lines.append(f"  卷标：{volume.volume_label}")
        if volume.serial_hex:
            lines.append(f"  序列号：{volume.serial_hex}")
        for key, value in volume.details.items():
            if isinstance(value, bool):
                rendered = "是" if value else "否"
            elif isinstance(value, int):
                rendered = f"{value:,}"
            else:
                rendered = str(value)
            lines.append(f"  {key}：{rendered}")
    if report.warnings:
        lines.extend(["", "说明 / 警告："])
        lines.extend(f"- {warning}" for warning in report.warnings)
    return "\n".join(lines)


def report_json(report: ImageStructure) -> str:
    """Serialize inspection results for automation or archival use."""
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
