# V8 raw-image scan performance results

## Method

The dataset contains one zero-filled raw image at each size: 1, 16, and 64 MiB. Each image contains the same known JPEG, PNG, and PDF fixtures at separate offsets. The runner performed five end-to-end CLI scans per image, for 15 scans total. Timing includes Python startup, carving, format validation, and manifest writing.

Windows `fsutil sparse queryflag` reported that none of the three image files was marked as sparse. The runner did not clear the operating-system file cache between repeated scans.

## Results

| Image size | Scans | Mean time (s) | Median time (s) | Range (s) | Mean end-to-end throughput (MiB/s) | Candidates and exact hashes per scan |
|---:|---:|---:|---:|---:|---:|---:|
| 1 MiB | 5 | 0.611852 | 0.610787 | 0.588498–0.625462 | 1.635189 | 3 candidates; 3 exact hashes |
| 16 MiB | 5 | 0.675295 | 0.664360 | 0.632401–0.727197 | 23.754772 | 3 candidates; 3 exact hashes |
| 64 MiB | 5 | 0.708628 | 0.708977 | 0.707383–0.709977 | 90.315508 | 3 candidates; 3 exact hashes |

All 15 scans found the three embedded files and matched each candidate's SHA-256 to its source. These are repeated scans of the same three images, not 15 independent datasets.

## Interpretation and limits

The 64 MiB image is 64 times larger than the 1 MiB image, while mean runtime increased by about 15.8%. The reported throughput therefore rises with image size. This is an observed end-to-end result for this computer and these runs, not a direct measurement of storage-device throughput or the carving loop alone. Process startup, validation, manifest writing, and operating-system caching contribute to the result.

There is only one image per size, and cache state was not controlled. A follow-up benchmark should use multiple independently generated images at each size and report cold-cache and warm-cache runs separately where the environment permits. Peak memory was not measured.
