# Recovery scenarios and platform roadmap

## Current pilot (PDRS 0.10.0)

PDRS accepts regular raw image files and reads them without writing to the source. It carves contiguous BMP, JPEG, PNG, PDF, and SQLite main-database candidates. SQLite candidates up to 64 MiB receive `PRAGMA quick_check`; larger candidates receive bounded header and page-one checks, with the skipped deep check reported. The scanner does not join SQLite `-wal` files, recover deleted rows, or interpret app-specific schemas.

The structure inspector reads MBR/GPT partition tables, FAT32 and exFAT boot metadata, an NTFS boot marker, and the ext-family superblock. In addition, `recover-fat32-deleted` experimentally reads deleted short-name entries in FAT32 root directories and attempts to extract each file from a contiguous data range. It does not restore long filenames, recurse into subdirectories, or reassemble fragmented files. Other filesystem directory entries, allocation records, inode tables, and file contents are not read. ext4 recognition remains metadata-only.

## Reproducible deletion and damage examples

Run the synthetic scenario set on Windows from the project root:

```powershell
.\.venv\Scripts\python.exe .\examples\make_recovery_scenario_set_v1.py
.\.venv\Scripts\python.exe .\examples\run_recovery_scenario_set_v1.py
```

The SQLite set includes three conditions:

1. `deleted_file_carve_model`: a complete SQLite database is placed in an image at a location treated as unallocated. It tests whether signature carving can recover intact file bytes after directory metadata is assumed lost. It does not create or parse a real deleted filesystem entry.
2. `zero_filled_sector`: a 512-byte region inside the database's B-tree page is zero-filled. This tests whether PDRS preserves the candidate and reports failed SQLite integrity validation. Zero-filling is a controlled byte-loss surrogate, not an actual disk read error.
3. `truncated_image`: the image ends before the full SQLite database page range. This tests incomplete-boundary reporting.

Each result folder contains a manifest and Ground Truth comparison. The exact hash is expected only for the intact deletion model. A failed check does not attempt to repair or infer missing bytes. The scripts refuse to overwrite existing generated data; remove or rename the generated `examples/recovery_scenario_set_v1` folder yourself before rerunning.

## FAT32 deleted-entry pilot

`examples/make_fat32_deleted_demo.py` builds a synthetic MBR/FAT32 image with a deleted root 8.3 entry and a known text payload. Run `examples/run_fat32_deleted_demo.py` to compare recovered SHA-256 and data offset with Ground Truth, or use the CLI directly:

```powershell
.\.venv\Scripts\python.exe .\examples\make_fat32_deleted_demo.py
.\.venv\Scripts\pdrs.exe recover-fat32-deleted .\examples\fat32_deleted_demo\images\fat32_deleted_root.img .\examples\fat32_deleted_demo\cli_results --ground-truth .\examples\fat32_deleted_demo\ground_truth.csv
```

The deleted first filename character is gone and cannot be inferred. The command recovers generic bytes from the directory-entry size and first cluster. It assumes contiguous storage because deletion may clear FAT chain entries. It does not validate the recovered file format, and a fragmented file may be wrong. This first pilot should be treated as a controlled proof of concept, not a broad FAT32 recovery claim.

## Platform and filesystem plan

Operating system names are not filesystem formats. Recovery depends on the filesystem, partition layout, device encryption, app sandbox, and whether file data remains intact. The current matrix is intentionally narrow:

| Platform | Common formats or data | Current PDRS status | Next research step |
| --- | --- | --- | --- |
| Windows | NTFS, FAT32, exFAT; SQLite app databases | Experimental FAT32 root 8.3 deleted-entry extraction with contiguous-data assumption; FAT32/exFAT boot metadata; NTFS marker only | Add FAT32 subdirectory/LFN and fragmented-file studies; then synthetic NTFS MFT experiments |
| Linux | ext4, XFS, Btrfs; SQLite app databases | ext superblock recognition; no directory or inode recovery | Add ext4 inode and extent metadata inspection, starting read-only on synthetic images |
| Android | ext4 or F2FS userdata; SQLite app databases | ext superblock recognition where ext4 is used; no F2FS or Android app parser | Add F2FS metadata research and export-based SQLite experiments; encryption/key availability must be recorded |
| Apple | APFS, HFS+; app databases | No APFS/HFS+ parser; generic SQLite carving only when an accessible image contains plaintext bytes | Start with read-only APFS container/volume metadata; encrypted volumes require authorized unlocked/exported data |

This table is a plan, not a compatibility claim. A Windows build can inspect a Linux raw image if the implemented parser understands the structures; it does not need the same operating system as the source disk. Encryption may make correct carving impossible without authorized keys, and flash storage discard/trim may remove old data.

## Safe media-damage workflow

The current program does not open physical drives. For a later research milestone, use synthetic images or a separately acquired image copy. A real source should remain untouched; any image acquisition and read-error map should be produced with a dedicated, documented imaging workflow before PDRS is used. PDRS can then compare intact, truncated, and zero-filled regions in that image file. It does not control drive firmware, bypass encryption, or repair a failing device.

## Suggested milestone order

1. Add more FAT32 synthetic samples, including zero-length, multi-cluster contiguous, and interrupted cases, and report byte-level recovery and false-positive rates.
2. Add read-only FAT32 subdirectory/LFN analysis and evaluate when a contiguous assumption is not justified; do not silently claim fragmented recovery.
3. Add bounded NTFS MFT record inspection and separately evaluate resident versus nonresident data.
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
