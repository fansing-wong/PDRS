# V10 paired CLI and in-process timing results

## Method

V10 reused the nine V9 randomized-background images. Each image received five paired measurements. For each pair, the runner measured one CLI scan and one direct call to `carve_image`, alternating which method ran first to balance cache order. Both methods generated candidate files and were checked against the same ground truth.

The CLI interval includes a new Python process, imports, Typer command handling, carving, validation, hashing, candidate writes, and manifest serialization. The in-process interval measures `carve_image` after the runner has imported the package; it includes scanning, validation, hashing, and candidate writes, but excludes process startup and CLI manifest serialization. File-cache state was not cleared.

## Results

| Image size | Pairs | Mean CLI (s) | Median CLI (s) | Mean in-process (s) | Median in-process (s) | Mean paired difference (s) | Median paired difference (s) | Identical outputs |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 MiB | 15 | 0.686883 | 0.662278 | 0.022042 | 0.007187 | 0.664841 | 0.639039 | 15/15 |
| 16 MiB | 15 | 0.680682 | 0.688892 | 0.046583 | 0.043076 | 0.634099 | 0.636104 | 15/15 |
| 64 MiB | 15 | 0.809763 | 0.805765 | 0.167904 | 0.160620 | 0.641858 | 0.650066 | 15/15 |

All 45 pairs produced identical candidate offsets, formats, hashes, and validity states. Each CLI and in-process run recovered the three known files exactly. Both methods also found the same random-background JPEG signatures and marked them invalid.

## Interpretation and limits

The median CLI-minus-in-process difference stayed between 0.636 and 0.650 seconds across all three image sizes. For these runs, that is a useful estimate of the combined process-startup, import, CLI, manifest, and timing overhead beyond the measured `carve_image` call. It is not a pure Python startup measurement because the two timing intervals include different surrounding work.

The 1 MiB in-process median was 0.007 seconds, with a 0.231-second maximum, so its mean is sensitive to one slow run. Cache order was balanced but not reset. These measurements describe this machine and this dataset; they do not establish cold-storage throughput. The runner also does not measure peak memory.
