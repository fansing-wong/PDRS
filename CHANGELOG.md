# Changelog

## 0.19.0 — FAT32 deleted-directory edge-case matrix

- Adds a two-cluster deleted-directory fixture with deleted LFN slots at the end of the first cluster and the short entry at the start of the second.
- Adds a cluster-reuse control where an active file owns the deleted directory chain's tail cluster; the scanner must skip that directory.
- Runs both scenarios at 512 B, 1 KiB, and 2 KiB clusters, with Ground Truth, SHA-256, offsets, and overlap warnings recorded.
- All six multi-cluster/LFN variants recovered 6/6 expected files with no false positives; all three reuse variants recovered the other 4/4 expected files and rejected the reused directory chain.

## 0.18.0 — Opt-in FAT32 deleted-directory scanning

- Adds an opt-in scan for direct deleted-file entries inside deleted directories whose FAT chains remain complete.
- Requires complete active-file allocation mapping and skips deleted-directory chains that overlap active directories, active files, or another scanned deleted directory.
- Protects recovered file ranges from scanned directory clusters and other candidates; records deleted-parent provenance in the manifest and GUI.
- Bounds deleted-directory traversal to 256 entries and 64 MiB, and does not recurse into nested deleted directories.
- Adds a synthetic matrix at 512 B, 1 KiB, and 2 KiB clusters; all fixtures recovered 5/5 expected files with zero false-positive candidates.

## 0.17.0 — Opt-in FAT32 fragmented-chain reassembly

- Adds an opt-in recovery mode that follows complete surviving FAT chains and writes clusters in logical file order.
- Records merged physical source extents in the manifest; the ordinary byte offset remains the first extent's image offset.
- Requires complete active-file allocation mapping before reassembling fragmented candidates and rejects overlaps with active directories, active files, or already recovered candidates.
- Keeps incomplete, truncated, cyclic, invalid, and malformed chains skipped; cleared FAT links retain the explicitly labelled contiguous-data assumption.
- Adds a synthetic three-cluster-size matrix with one positive fragmented file plus active-file, deleted-directory, and interrupted-chain absence controls.

## 0.16.0 — FAT32 cluster-size matrix

- Extends the synthetic deleted-entry dataset to support 512 B, 1 KiB, and 2 KiB clusters.
- Adds a deleted zero-length file case and scales multi-cluster, fragmented, and interrupted samples to each cluster size.
- Adds a matrix runner that aggregates Ground Truth and data-layout metrics into one CSV.

## 0.15.0 — FAT32 layout evidence reporting

- Reports whether the FAT links needed for a candidate are contiguous or were cleared after deletion.
- Adds a positive multi-cluster case with a surviving contiguous FAT chain.
- Writes candidate layout counts to `data_layout_summary.csv` in the synthetic study.

## 0.14.0 — Interrupted FAT32 chain guard

- Distinguishes cleared FAT links from a premature end-of-chain marker.
- Skips deleted entries when the visible FAT chain ends before the directory entry's declared file size.
- Skips invalid or reserved FAT links; only cleared links retain the contiguous-data fallback.
- Adds a synthetic interrupted-chain case with a decoy cluster and Ground Truth absence record.

## 0.13.0 — Visible FAT32 fragmentation guard

- Checks the FAT links needed for each deleted entry's declared size before contiguous extraction.
- Skips candidates when a surviving FAT link visibly jumps to a non-adjacent cluster, instead of silently emitting bytes from the wrong range.
- Keeps a clearly labelled contiguous-data assumption when deleted FAT links are cleared or unavailable.
- Extends the synthetic FAT32 demo with a fragmented file whose intervening cluster contains unrelated decoy bytes.

## 0.12.0 — FAT32 deleted long-name reconstruction

- Reconstructs a display filename from adjacent deleted FAT32 LFN slots in the root or active subdirectories.
- Stores the original LFN in `manifest.csv` and saves a sanitized, unique output filename with an entry-offset suffix.
- Falls back to a generic candidate name when LFN slots are malformed; data extraction can still proceed.
- Documents that the deleted short-name first byte prevents full LFN checksum verification.
- The FAT32 demo reports LFN exact-name matches separately from byte hash and offset matches.

## 0.11.0 — FAT32 active-subdirectory scan

- Extended deleted short-entry scans from the root directory into still-active subdirectories.
- Added cycle/overlap detection and limits for depth, directory count, directory bytes, and warning volume.
- Skips candidates overlapping an active directory cluster; skips all extraction when traversal is incomplete.
- Added directory depth/cluster details and scan-size statistics to CLI and GUI results.
- Expanded the synthetic Ground Truth demo with root, subdirectory, active-file, and deleted-directory controls.
- Deleted directories, long filenames, fragmented data, and format validation remain unsupported.

## 0.10.0 — Experimental FAT32 deleted-entry recovery

- Added `recover-fat32-deleted` for FAT32 root-directory deleted 8.3 entries in regular raw image files.
- Recovery reads a bounded root-directory chain and writes candidate bytes to a separate empty output directory.
- Added a Tkinter action with explicit confirmation and a generated FAT32/Ground Truth demo.
- Recovery assumes contiguous data; LFN, subdirectories, fragmented files, and non-FAT32 deleted entries remain unsupported.

## 0.9.0 — SQLite carving and ext metadata pilot

- Added contiguous SQLite main-database carving with bounded structural checks and `quick_check` up to 64 MiB.
- Added read-only ext superblock recognition and metadata reporting.
- Added synthetic deletion-residual, zero-filled-region, and truncated-image scenarios with Ground Truth comparisons.
- Documented Windows, Linux, Android, and Apple filesystem boundaries and a staged recovery roadmap.
- SQLite WAL replay, deleted-row recovery, filesystem directory recovery, and physical-device access remain out of scope.

## 0.8.0 — GitHub preparation

- Added bounded BMP candidate carving for supported BMP/DIB header variants.
- Added BMP structural boundary checks and a synthetic demo with Ground Truth.
- Added unit coverage for BMP carving, truncated candidates, PNG validation, image inspection, and Markdown reports.
- Updated project documentation and added repository hygiene and CI configuration.

Earlier course milestones and experimental datasets are documented in `PDRS_REPORT_DRAFT.md`. Generated images and result folders are intentionally excluded from source control.
