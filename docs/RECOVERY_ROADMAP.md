# Recovery scenarios and platform roadmap

## Current pilot (PDRS 0.22.0)

PDRS accepts regular raw image files and reads them without writing to the source. It carves contiguous BMP, JPEG, PNG, PDF, and SQLite main-database candidates. SQLite candidates up to 64 MiB receive `PRAGMA quick_check`; larger candidates receive bounded header and page-one checks, with the skipped deep check reported. The scanner does not join SQLite `-wal` files, recover deleted rows, or interpret app-specific schemas.

The structure inspector reads MBR/GPT partition tables, FAT32 and exFAT boot metadata, an NTFS boot marker, and the ext-family superblock. In addition, `recover-fat32-deleted` experimentally reads deleted short-name entries from the root directory and still-active subdirectories and attempts to reconstruct adjacent deleted LFN slots. Default mode skips visible fragmented chains. The opt-in `--reassemble-fragmented` mode follows complete surviving chains and writes their clusters in logical order, but only when directory traversal and active-file allocation mapping are complete and no cluster overlaps an active directory, active file, or earlier recovered candidate. The additional opt-in `--scan-deleted-directories` mode follows complete deleted-directory chains and reads direct file entries only; it rejects overlap with active directories, active files, and previously scanned deleted directories. It is bounded to 256 directory entries and 64 MiB of deleted-directory data and does not recurse. The v0.19–v0.21 synthetic matrices cover multi-cluster directories, LFN slots crossing a cluster boundary, single and multiple cluster reuse, incomplete/cyclic/bad-cluster directory chains, and overwritten LFN slots. Incomplete or malformed deleted-directory chains are skipped as a whole. The reuse controls reject file-data bytes that resemble directory entries. The overwritten-LFN experiment confirms that data may be recovered even when the displayed name is only partial. The manifest records merged physical ranges in `source_extents`; for fragmented output, `offset` is the first extent's start and `end_offset_exclusive` is blank. If deletion cleared the FAT links, contiguous storage remains an unverified assumption. Output filenames use a sanitized LFN stem plus an entry-offset suffix; the original name is also kept in the manifest. Since deletion erases the short-name first byte and LFN ordinals, reconstructed names are best-effort and may be partial. Directory traversal and cluster mapping are bounded. Other filesystem allocation records, inode tables, and file contents are not read. ext4 recognition remains metadata-only.

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

`examples/make_fat32_deleted_demo.py` and `examples/run_fat32_layout_matrix_v16.py` preserve the v0.16 controls. The v0.17 scripts use a separate fixture with a positive complete fragmented-chain case plus active-file, deleted-directory, and interrupted-chain absence controls. Both matrices cover 512 B, 1 KiB, and 2 KiB clusters and aggregate Ground Truth metrics into `matrix_summary.csv`.

```powershell
.\.venv\Scripts\python.exe .\examples\make_fat32_deleted_demo.py --output-dir .\examples\fat32_deleted_demo_v16 --sectors-per-cluster 1
.\.venv\Scripts\python.exe .\examples\run_fat32_deleted_demo.py --demo-dir .\examples\fat32_deleted_demo_v16
.\.venv\Scripts\python.exe .\examples\run_fat32_layout_matrix_v16.py
```

The v0.17 opt-in reassembly experiment is separate:

```powershell
.\.venv\Scripts\python.exe .\examples\make_fat32_fragmented_demo_v17.py --output-dir .\examples\fat32_deleted_demo_v17 --sectors-per-cluster 1
.\.venv\Scripts\python.exe .\examples\run_fat32_fragmented_demo_v17.py --demo-dir .\examples\fat32_deleted_demo_v17
.\.venv\Scripts\python.exe .\examples\run_fat32_layout_matrix_v17.py
```

The v0.18 deleted-directory experiment uses isolated synthetic demo folders and preserves a known directory FAT end marker before scanning:

```powershell
.\.venv\Scripts\python.exe .\examples\run_deleted_directory_matrix_v18.py
```

The current fixture produced five exact expected recoveries, two expected-absent controls, and zero false positives for each cluster size. This small deterministic set does not estimate field recovery rates.

The v0.19 matrix adds a two-cluster deleted directory with LFN slots crossing a cluster boundary, plus a separate active-file cluster-reuse control:

```powershell
.\.venv\Scripts\python.exe .\examples\run_deleted_directory_matrix_v19.py
```

Each size recovered 6/6 positive files in the multi-cluster case. The reuse case reported one directory-chain overlap skip per image and recovered 4/4 other targets with zero false-positive candidates.

The v0.20 matrix checks partial deleted-directory chains and overwritten LFN slots:

```powershell
.\.venv\Scripts\python.exe .\examples\run_deleted_directory_matrix_v20.py
```

The incomplete chain was skipped in all three cluster sizes, with zero deleted-directory candidates. In the overwritten-LFN control, all five expected files were recovered exactly by bytes and offset, but the target display name was truncated to `Deleted repor`; the manifest now warns that reconstructed LFN names may be partial.

The v0.21 matrix expands reuse to two distinct active files and tests cyclic and bad-cluster directory chains:

```powershell
.\.venv\Scripts\python.exe .\examples\run_deleted_directory_matrix_v21.py
```

Each cluster size rejected both reused directories and emitted two overlap warnings. Cyclic and bad-cluster chains were each skipped with one chain warning per image. All expected-present baseline targets were exact, all negative controls stayed absent, and there were zero false-positive candidates.

The deleted short-name first character is gone; the tool uses the adjacent LFN slots for the display name, but the erased alias byte prevents full checksum verification. The command recovers bytes from the directory-entry size and first cluster. By default it scans entries in active directories only. The v0.18 `--scan-deleted-directories` option follows complete, non-overlapping deleted-directory chains and scans only their direct file entries; it does not recurse. By default it skips visible fragmentation. Its v0.17 opt-in mode reassembles a complete visible chain after checking known active and recovered cluster references; this does not prove that the chain belonged to the deleted file. Incomplete or invalid chains remain skipped, and cleared FAT links still cause a contiguous-storage assumption. It does not validate the recovered file format. Treat this as a controlled proof of concept, not a broad FAT32 recovery claim.

## Platform and filesystem plan

Operating system names are not filesystem formats. Recovery depends on the filesystem, partition layout, device encryption, app sandbox, and whether file data remains intact. The current matrix is intentionally narrow:

| Platform | Common formats or data | Current PDRS status | Next research step |
| --- | --- | --- | --- |
| Windows | NTFS, FAT32, exFAT; SQLite app databases | Experimental FAT32 root/subdirectory deletion recovery; opt-in complete-chain reassembly and direct files in complete deleted directories, with allocation-overlap checks; cleared file chains still use a contiguous-data assumption; FAT32/exFAT boot metadata; NTFS marker only | Add shared multi-cluster active allocations and active-directory reuse controls; then synthetic NTFS MFT experiments |
| Linux | ext4, XFS, Btrfs; SQLite app databases | ext superblock recognition; no directory or inode recovery | Add ext4 inode and extent metadata inspection, starting read-only on synthetic images |
| Android | ext4 or F2FS userdata; SQLite app databases | ext superblock recognition where ext4 is used; no F2FS or Android app parser | Add F2FS metadata research and export-based SQLite experiments; encryption/key availability must be recorded |
| Apple | APFS, HFS+; app databases | No APFS/HFS+ parser; generic SQLite carving only when an accessible image contains plaintext bytes | Start with read-only APFS container/volume metadata; encrypted volumes require authorized unlocked/exported data |

This table is a plan, not a compatibility claim. A Windows build can inspect a Linux raw image if the implemented parser understands the structures; it does not need the same operating system as the source disk. Encryption may make correct carving impossible without authorized keys, and flash storage discard/trim may remove old data.

## Safe media-damage workflow

The current program does not open physical drives. For a later research milestone, use synthetic images or a separately acquired image copy. A real source should remain untouched; any image acquisition and read-error map should be produced with a dedicated, documented imaging workflow before PDRS is used. PDRS can then compare intact, truncated, and zero-filled regions in that image file. It does not control drive firmware, bypass encryption, or repair a failing device.

## Suggested milestone order

1. Expand cluster-reuse cases to shared multi-cluster active allocations and active-directory reuse; report each ambiguity separately.
2. Bound and report LFN reconstruction confidence more directly, including cases where only some deleted LFN slots remain.
3. Add bounded NTFS MFT record inspection and separately evaluate resident versus nonresident data.
4. Add ext4 inode/extent metadata reading, with explicit limits for journal replay and extents.
5. Evaluate F2FS and APFS metadata as separate projects because their structures and encryption constraints differ.
6. Add application-specific parsers only after documenting each app's database schema, WAL handling, version, and privacy boundary.

## Structure references

- [SQLite file format](https://www.sqlite.org/fileformat.html)
- [Microsoft FAT32 File System Specification](https://www.pcjs.org/documents/papers/microsoft/MS_FAT_OVERVIEW_103-2000-12-06.pdf)
- [Linux kernel ext4 superblock documentation](https://docs.kernel.org/filesystems/ext4/super.html)
- [Android file-based encryption](https://source.android.com/docs/security/features/encryption/file-based)
- [Microsoft NTFS overview](https://learn.microsoft.com/en-us/windows-server/storage/file-server/ntfs-overview)
- [Apple file system formats](https://support.apple.com/guide/disk-utility/file-system-formats-dsku19ed921c/22.7/mac/27)
- [Apple platform data protection](https://support.apple.com/guide/security/sec4c6dc1b6e/web)

## FAT copy selection

The FAT32 reader follows `BPB_ExtFlags`: when mirroring is disabled, it reads the designated active FAT copy and rejects an index outside the declared FAT count. When mirroring is enabled, it reads copy 0 and emits a warning that the other copies are not cross-checked. This avoids silently using the wrong table on volumes with an explicitly selected active copy, but does not detect divergence or repair FAT metadata.
