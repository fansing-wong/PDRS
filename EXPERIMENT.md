# Course experiment protocol

## Proposed title

**基于文件结构约束的数字文件雕刻与恢复效果评估**

The current PDRS prototype carves contiguous BMP, JPEG, PNG, PDF, and SQLite main-database candidates. This course protocol focuses primarily on PNG boundaries, with JPEG and PDF as comparison formats; BMP has a separate synthetic demo and structural tests.

## Research questions

1. How accurately can signature scanning detect known files when filesystem metadata is unavailable?
2. How do file format and content placement affect exact recovery and byte recovery rates?
3. What false positives and incomplete candidates are introduced by simple header/end-marker rules?

## Scope and hypothesis

Use only synthetic raw images generated for the experiment. The prototype reads the image in read-only mode and writes results to a separate directory. The regular carving command does not recover filesystem deletion records, contact physical devices, or reconstruct fragmented files. A separate experimental command handles deleted FAT32 short entries in the root and still-active subdirectories. It skips an entry if the surviving FAT shows a non-contiguous link, ends before the declared file size, or contains an invalid link; if deletion cleared the FAT links, it falls back to the explicitly reported contiguous-data assumption. SQLite WAL replay and deleted-row recovery remain outside scope.

Hypothesis: files stored contiguously with intact headers and valid format terminators will be recovered byte-for-byte more often than truncated files or files whose format markers occur in unrelated payload data. Format-aware boundary rules should reduce false positives compared with header-only extraction.

## Independent variables

- Format: BMP, JPEG, PNG, PDF, SQLite; the main comparative experiment emphasizes JPEG, PNG, and PDF.
- Layout: contiguous, separated by filler bytes, truncated at end marker, truncated before end marker.
- Background: zero-filled area, random filler, and deliberately embedded decoy signatures.
- File size: small, medium, and large samples within locally available resources.

Change one factor at a time in the core comparison. Use a separate adversarial set for decoy signatures and marker-like payload data.

## Ground truth and metrics

Keep a ground-truth CSV with original filename, format, byte length, image offset, and SHA-256. Measure:

- Detection precision = true recovered candidates / all emitted candidates.
- Detection recall = source files detected / all source files inserted.
- Exact recovery rate = byte-identical files / all source files inserted.
- Byte recovery rate = matching recovered bytes / original bytes, computed for each known file.
- Runtime and peak memory for each image size.

Use SHA-256 equality to establish exact recovery. File-open success is a separate format-validity observation, not proof of byte identity.

## Procedure

1. Generate a small set of original JPEG, PNG, and PDF files with known hashes.
2. Build raw image files by placing those bytes at recorded offsets and adding controlled filler, truncation, or decoy patterns.
3. Save a ground-truth manifest before running the recovery program.
4. Scan each image with the same program version and record its CSV output, elapsed time, and peak memory.
5. Compare recovered candidate offsets and hashes against ground truth.
6. Repeat each condition at least five times for timing measurements; reuse identical images so recovery accuracy remains comparable.
7. Summarize results in tables and discuss false positives, misses, format-specific boundaries, and limitations.

## Expected results

- Contiguous, intact candidates should be detected and hash-match the originals.
- Truncated candidates should be marked incomplete or recover only a prefix.
- Decoy signatures should expose false positives and show why signatures alone cannot prove a file is valid.
- Results should show that this first milestone is a carving prototype, not general-purpose recovery: fragmentation and lost metadata require different methods.

## Report outline

1. Introduction and problem statement
2. File carving and format-boundary principles
3. Experimental design and ground-truth construction
4. Prototype architecture and read-only handling
5. Results: accuracy, byte recovery, runtime, and memory
6. Error analysis and threats to validity
7. Conclusion and next steps (additional format validation and performance measurement; filesystem metadata recovery remains outside this prototype)


## Deletion and partial-damage scenarios

`examples/make_recovery_scenario_set_v1.py` creates a SQLite database and three raw images: intact bytes in a location assumed to be unallocated, one zero-filled 512-byte region in a B-tree page, and an image truncated before the declared database end. `examples/run_recovery_scenario_set_v1.py` records manifests and Ground Truth comparisons. The first condition models loss of directory metadata only; it is not a filesystem-deletion recovery test. Zero-fill and truncation are simulations of missing/corrupted bytes, not tests against physical media or actual unreadable sectors.

When reporting platform compatibility, specify the filesystem and encryption state (for example, NTFS, ext4, F2FS, or APFS), not just Windows, Android, Linux, or Apple. See `docs/RECOVERY_ROADMAP.md` for the current capability matrix and planned milestones.


## FAT32 deleted-entry experiments

The 0.10 pilot used a synthetic FAT32 volume with one deleted 8.3 root-directory entry. Version 0.11 adds a deleted entry inside an active subdirectory, an intact-file control, and a deleted-directory control. Version 0.12 adds deleted LFN slots to the root and subdirectory samples. Version 0.13 adds a deliberately fragmented deleted file whose visible FAT chain jumps over a decoy cluster; PDRS must skip it rather than return bytes from the contiguous range. Version 0.14 adds an interrupted-chain control whose FAT end marker occurs before the directory entry's declared size. `recover-fat32-deleted IMAGE OUTPUT` follows the first FAT to scan the root and active subdirectory chains in a regular image file. It extracts candidates using the directory-entry size and first cluster, reconstructs names from adjacent deleted LFN slots when they pass structural checks, and rejects visible fragmented, interrupted, or invalid chains. If deletion cleared FAT links, it still assumes the data is contiguous.

The demo writes two known source files and records expected SHA-256 hashes, offsets, and names in Ground Truth. It also puts a deleted file inside a deleted directory; that file should not be found because its parent directory is no longer reachable through an active entry. `run_fat32_deleted_demo.py` reports byte-level exact matches and LFN name matches separately, with name-level rows in `lfn_name_comparison.csv`. These controlled results do not generalize to real devices.

The deleted short-name first byte remains unavailable; because of that, an LFN's checksum cannot be fully verified against its short alias. The LFN is metadata for display and output naming, while each saved file also gets an offset suffix to keep names unique. The scanner does not enter deleted directories, reconstruct fragmented data, or validate recovered formats. It skips a candidate when a surviving FAT link shows a non-contiguous chain, an early end marker, or invalid metadata, but a cleared FAT chain cannot establish the original layout. Traversal is bounded to 32 directory levels, 4,096 directory starts, 256 MiB of directory bytes, and 64 MiB per individual directory chain. If traversal reaches a safety limit or an active directory chain is malformed, extraction is skipped for that volume. A candidate whose assumed contiguous range overlaps a scanned active directory cluster is also skipped.
