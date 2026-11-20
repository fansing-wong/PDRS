# Changelog

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