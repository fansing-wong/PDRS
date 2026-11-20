# Implementation references

These references describe structures checked by PDRS. The implementation covers only a bounded subset and does not claim full format conformance.

- Microsoft, [BITMAPFILEHEADER structure](https://learn.microsoft.com/windows/win32/api/wingdi/ns-wingdi-bitmapfileheader).
- Microsoft, [BITMAPINFOHEADER structure](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-bitmapinfoheader).
- Microsoft, [Bitmap Storage](https://learn.microsoft.com/en-us/windows/win32/gdi/bitmap-storage).
- SQLite, [Database File Format](https://www.sqlite.org/fileformat.html).
- Linux kernel, [ext4 superblock](https://docs.kernel.org/filesystems/ext4/super.html).
- Microsoft, [NTFS overview](https://learn.microsoft.com/en-us/windows-server/storage/file-server/ntfs-overview).
- Android Open Source Project, [File-based encryption](https://source.android.com/docs/security/features/encryption/file-based).
- Apple, [File system formats available in Disk Utility](https://support.apple.com/guide/disk-utility/file-system-formats-dsku19ed921c/22.7/mac/27).
- Apple Platform Security, [Data protection overview](https://support.apple.com/guide/security/sec4c6dc1b6e/web).

PDRS validates selected BMP fields, PNG chunks/CRCs/zlib layout, SQLite database headers and (up to 64 MiB) `quick_check`, and selected partition/filesystem metadata. Optional Pillow and pypdf checks are independent parsers for JPEG and PDF. These checks do not prove provenance, authenticity, or successful recovery of a user's original file.
