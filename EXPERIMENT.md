# Course experiment protocol

## Proposed title

**基于文件结构约束的数字文件雕刻与恢复效果评估**

The current PDRS prototype carves contiguous BMP, JPEG, PNG, PDF, and SQLite main-database candidates. This course protocol focuses primarily on PNG boundaries, with JPEG and PDF as comparison formats; BMP has a separate synthetic demo and structural tests.

## Research questions

1. How accurately can signature scanning detect known files when filesystem metadata is unavailable?
2. How do file format and content placement affect exact recovery and byte recovery rates?
3. What false positives and incomplete candidates are introduced by simple header/end-marker rules?

## Scope and hypothesis

Use only synthetic raw images generated for the experiment. The prototype reads the image in read-only mode and writes results to a separate directory. The regular carving command does not recover filesystem deletion records or contact physical devices. A separate experimental command handles deleted FAT32 short entries in the root and still-active subdirectories. By default, it skips visible non-contiguous chains; an opt-in mode reassembles only complete surviving chains after directory and active-file overlap checks. If deletion cleared the FAT links, it falls back to the explicitly reported contiguous-data assumption. SQLite WAL replay and deleted-row recovery remain outside scope.

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

The 0.10–0.16 pilots added deleted root/subdirectory entries, LFN slots, contiguous and zero-length samples, visible-fragmentation and interrupted-chain controls, and cluster sizes of 512 B, 1 KiB, and 2 KiB. The v0.16 runner is retained for the historical skip-fragmentation behavior. Version 0.17 adds a separate opt-in mode and a positive fragmented-file fixture. It follows a complete chain for the number of clusters implied by the directory entry's size, refuses incomplete or malformed chains, and requires a complete map of active-file data clusters before reassembly. It also checks for overlap with active directories, active files, and earlier recovered candidates. The manifest's `source_extents` field records the physical image ranges in logical file order. For a fragmented file, `offset` names only the first extent and `end_offset_exclusive` is blank because one physical end offset cannot describe the whole file. The option does not prove that the surviving FAT chain belonged to the deleted file; byte hashes and controlled Ground Truth remain necessary.

The demo writes two non-empty source files plus a zero-length file and records expected SHA-256 hashes, offsets, and names in Ground Truth. It also puts a deleted file inside a deleted directory; that file should not be found because its parent directory is no longer reachable through an active entry. `run_fat32_deleted_demo.py` reports byte-level exact matches, LFN name matches, and layout-status counts. The v0.16 matrix run produced:

| Sectors per cluster | Cluster size | Expected files | Exact | Recall | Precision | False positives |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 512 B | 3 | 3/3 | 100% | 100% | 0 |
| 2 | 1,024 B | 3 | 3/3 | 100% | 100% | 0 |
| 4 | 2,048 B | 3 | 3/3 | 100% | 100% | 0 |

Each image also has two expected-absent controls: a visibly fragmented file and an interrupted chain. These are results for the generated fixtures only; they do not estimate performance on real media.

The deleted short-name first byte remains unavailable; because of that, an LFN's checksum cannot be fully verified against its short alias. The LFN is metadata for display and output naming, while each saved file also gets an offset suffix to keep names unique. The v0.17 pilot did not enter deleted directories or validate recovered formats. The normal mode skips visible non-contiguous chains. The v0.17 opt-in mode reassembles only complete chains after overlap checks; this remains a hypothesis about the deleted file's original allocation, not proof of provenance. A cleared FAT chain cannot establish the original layout, so it continues to use an explicitly reported contiguous-data assumption. Active-directory traversal is bounded to 32 levels, 4,096 directory starts, 256 MiB of directory bytes, and 64 MiB per individual directory chain. Active-file cluster mapping has a one-million-cluster cap. If traversal reaches a safety limit or an active directory chain is malformed, extraction is skipped for that volume. A candidate whose data clusters overlap a scanned active directory or mapped active file is skipped in the opt-in modes.

The v0.17 comparison scripts generate 512 B, 1 KiB, and 2 KiB cluster variants and write per-image details plus `matrix_summary.csv` under `examples/fat32_layout_matrix_v17`. Each fixture includes four expected files (root, nested, zero-length, and fragmented) and three expected-absent controls (active file, deleted directory, and interrupted chain). The run on the generated fixtures produced:

| Cluster size | Expected present | Exact | Expected absent | False positives | Precision | Recall | Offset match |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 512 B | 4 | 4/4 | 3 | 0 | 100% | 100% | 100% |
| 1,024 B | 4 | 4/4 | 3 | 0 | 100% | 100% | 100% |
| 2,048 B | 4 | 4/4 | 3 | 0 | 100% | 100% | 100% |

In all three runs, `fragmented_chain_reassembled=1`; the two larger cluster cases also classify the shorter root sample as `single_cluster`. These are measurements on synthetic fixtures only and do not estimate performance on real media.

### v0.18: direct entries inside deleted directories

The opt-in scanner follows a deleted directory's surviving FAT chain and checks its direct deleted regular-file entries. It does not recurse into nested deleted directories. Before scanning a directory it requires a complete chain and rejects overlap with active directory clusters, active file clusters, or another scanned deleted directory. Recovered files are also checked against scanned directory clusters, mapped active files, and other recovered candidates. The scan is capped at 256 deleted-directory entries and 64 MiB of directory data. This cannot establish that a surviving chain belonged to the deleted directory; it is a controlled heuristic, not a guarantee of recovery provenance.

`prepare_deleted_directory_fixture_v18.py` changes only a generated v17 synthetic image, after verifying its PDRS marker, to retain a known end-of-chain FAT link for the sample deleted directory. The matrix driver does this in isolated demo folders at 512 B, 1 KiB, and 2 KiB cluster sizes, then compares five expected files and two expected-absent controls. The current synthetic run produced:

| Cluster size | Expected present | Exact | Expected absent | False positives | Precision | Recall | Offset match |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 512 B | 5 | 5/5 | 2 | 0 | 100% | 100% | 100% |
| 1,024 B | 5 | 5/5 | 2 | 0 | 100% | 100% | 100% |
| 2,048 B | 5 | 5/5 | 2 | 0 | 100% | 100% | 100% |

The deleted-directory target is one deterministic synthetic example; the v17 generator alone does not preserve its FAT chain. These results validate behavior on that fixture and its controls only, not a real-world deleted-directory recovery rate.
