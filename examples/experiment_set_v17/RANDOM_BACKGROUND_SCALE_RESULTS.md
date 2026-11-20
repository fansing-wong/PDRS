# V23 random-background scale results

## Method

V23 measured the V22 fast candidate-index reassembler on 1, 16, and 64 MiB raw images. A fixed-seed PRNG (`231119`) generated one 64 MiB random byte sequence; the smaller images used prefixes of that same sequence. The same five-gap, 15-decoy PNG from V17 was embedded at offset 512 in each image. Each size was scanned three times. The PNG SHA-256 and decoded pixels were checked after every run.

## Results

| Raw image size | Repeats | Mean time | Median | Range | Exact hash and pixels |
|---:|---:|---:|---:|---:|---:|
| 1 MiB | 3 | 0.824241 s | 0.855084 s | 0.721283–0.896355 s | 3/3 |
| 16 MiB | 3 | 0.440024 s | 0.438010 s | 0.437889–0.444173 s | 3/3 |
| 64 MiB | 3 | 0.676958 s | 0.727224 s | 0.574700–0.728950 s | 3/3 |

All nine runs recovered the exact source hash and matching pixels. Each run indexed 22 CRC-valid IDAT/IEND chunks, visited 29,397 search nodes, and reached Pillow once. The measured time did not increase monotonically with image size.

## Interpretation and limits

This confirms recovery in one reproducible random background sequence and shows no clear size-related increase for this layout. The three image sizes are nested prefixes from the same random sequence, not independent backgrounds; only one PNG content sample and one seed were used. These timings are in-process reconstruction times and do not measure CLI startup, physical storage, peak memory, or real disk data. More independent seeds and PNG contents are needed before generalizing.

Per-run data are in `results_random_background_scale/sample_details.csv`; size aggregates are in `results_random_background_scale/scenario_summary.csv`.
