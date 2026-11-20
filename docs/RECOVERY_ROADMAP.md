# Recovery scenarios and platform roadmap

## Current pilot (PDRS 0.9.0)

PDRS accepts regular raw image files and reads them without writing to the source. It carves contiguous BMP, JPEG, PNG, PDF, and SQLite main-database candidates. SQLite candidates up to 64 MiB receive a SQLite `PRAGMA quick_check`; larger candidates receive bounded header and page-one checks, with the skipped deep check reported. The scanner does not join SQLite `-wal` files, recover deleted rows, or interpret app-specific schemas.

The structure inspector reads MBR/GPT partition tables, FAT32 and exFAT boot metadata, an NTFS boot marker, and the ext-family superblock. It does not read directory entries, allocation records, inode tables, cluster chains, or file contents from a filesystem. ext4 recognition is metadata recognition only.

## Reproducible deletion and damage examples

Run the synthetic scenario set on Windows from the project root:

```powershell
.\.venv\Scripts\python.exe .\examples\make_recovery_scenario_set_v1.py
.\.venv\Scripts\python.exe .\examples\run_recovery_scenario_set_v1.py
```

The set includes three conditions:

1. `deleted_file_carve_model`: a complete SQLite database is placed in an image at a location treated as unallocated. It tests whether signature carving can recover intact file bytes after directory metadata is assumed lost. It does not create or parse a real deleted filesystem entry.
2. `zero_filled_sector`: a 512-byte region inside the database's B-tree page is zero-filled. This tests whether PDRS preserves the candidate and reports failed SQLite integrity validation. Zero-filling is a controlled byte-loss surrogate, not an actual disk read error.
3. `truncated_image`: the image ends before the full SQLite database page range. This tests incomplete-boundary reporting.

Each result folder contains a manifest and Ground Truth comparison. The exact hash is expected only for the intact deletion model. A failed check does not attempt to repair or infer missing bytes. The scripts refuse to overwrite existing generated data; remove or rename the generated `examples/recovery_scenario_set_v1` folder yourself before rerunning.

## Platform and filesystem plan

Operating system names are not filesystem formats. Recovery depends on the filesystem, partition layout, device encryption, app sandbox, and whether file data remains intact. The current matrix is intentionally narrow:

| Platform | Common formats or data | Current PDRS status | Next research step |
| --- | --- | --- | --- |
| Windows | NTFS, FAT32, exFAT; SQLite app databases | NTFS marker only; FAT32/exFAT boot metadata; generic SQLite file carving | Build synthetic FAT32/NTFS deleted-entry experiments and validate directory metadata on image copies |
| Linux | ext4, XFS, Btrfs; SQLite app databases | ext superblock recognition; no directory or inode recovery | Add ext4 inode and extent metadata inspection, starting read-only on synthetic images |
| Android | ext4 or F2FS userdata; SQLite app databases | ext superblock recognition where ext4 is used; no F2FS or Android app parser | Add F2FS metadata research and export-based SQLite experiments; encryption/key availability must be recorded |
| Apple | APFS, HFS+; app databases | No APFS/HFS+ parser; generic SQLite carving only when an accessible image contains plaintext bytes | Start with read-only APFS container/volume metadata; encrypted volumes require authorized unlocked/exported data |

This table is a plan, not a compatibility claim. A Windows build can inspect a Linux raw image if the implemented parser understands the structures; it does not need the same operating system as the source disk. Encryption may make correct carving impossible without authorized keys, and flash storage discard/trim may remove old data.

## Safe media-damage workflow

The current program does not open physical drives. For a later research milestone, use synthetic images or a separately acquired image copy. A real source should remain untouched; any image acquisition and read-error map should be produced with a dedicated, documented imaging workflow before PDRS is used. PDRS can then compare intact, truncated, and zero-filled regions in that image file. It does not control drive firmware, bypass encryption, or repair a failing device.

## Suggested milestone order

1. Extend the synthetic deletion/damage dataset and report byte-level recovery ratios by format and damage location.
2. Parse FAT32 directory and allocation metadata from raw image copies; add deleted-entry tests before implementing recovery.
3. Add bounded NTFS MFT record inspection and separately evaluate resident versus nonresident content.
4. Add ext4 inode/extent metadata reading, with explicit limits for journal replay and extents.
5. Evaluate F2FS and APFS metadata as separate projects because their structures and encryption constraints differ.
6. Add application-specific parsers only after documenting each app's database schema, WAL handling, version, and privacy boundary.

## Structure references

- [SQLite file format](https://www.sqlite.org/fileformat.html)
- [Linux kernel ext4 superblock documentation](https://docs.kernel.org/filesystems/ext4/super.html)
- [Android file-based encryption](https://source.android.com/docs/security/features/encryption/file-based)
- [Microsoft NTFS overview](https://learn.microsoft.com/en-us/windows-server/storage/file-server/ntfs-overview)
- [Apple file system formats](https://support.apple.com/guide/disk-utility/file-system-formats-dsku19ed921c/22.7/mac/27)
- [Apple platform data protection](https://support.apple.com/guide/security/sec4c6dc1b6e/web)
