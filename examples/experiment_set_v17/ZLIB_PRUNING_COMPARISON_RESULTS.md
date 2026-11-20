# V18 incremental zlib pruning comparison

## Method

V18 reused the ten five-gap, 15-decoy images from V17. It compared V17's full-decode backtracking results with a separate experimental variant that copies a zlib decompressor state for each IDAT branch and abandons a branch when incremental decompression raises an error. V19 added a complete-zlib-stream (`eof`) requirement before invoking Pillow. A complete candidate still had to pass Pillow decoding. Each variant ran once per image; V17 timings are the baseline.

## Results

| Method | Mean time per image | Mean speedup vs V17 | zlib error branches rejected | Incomplete paths rejected | Pillow path checks | Exact hash and pixels |
|---|---:|---:|---:|---:|---:|---:|
| V17 full backtracking | 15.327268 s | Baseline | — | — | Not instrumented | 10/10 |
| V18 zlib error pruning | 13.393092 s | 1.14× | 7,190 | — | 145,430 total | 10/10 |
| V19 zlib error and EOF pruning | 13.451050 s | 1.14× | 7,190 | 145,420 | 10 total | 10/10 |

V18 was modestly faster on average, but one sample was slower than its V17 run. It still performed 145,430 complete Pillow path checks and visited an average of 29,397 recursion nodes per image. V19's EOF check rejected 145,420 incomplete paths before Pillow and reduced Pillow calls to one accepted path per image, but mean time remained about 13.45 seconds because candidate-window scanning continued to recalculate CRCs across overlapping ranges. Every returned PNG matched the source SHA-256 and decoded pixels.

## Interpretation and limits

Incremental zlib error checks alone did not remove the main cost. EOF gating greatly reduced Pillow calls, but repeated scans of overlapping 4096-byte windows remained expensive. These one-pass timings do not establish a stable speedup. V20's indexed-chunk follow-up tests whether avoiding that repeated CRC work can address the bottleneck. These variants remain isolated experiments and are not integrated into PDRS.

Per-image timing and search counters are in `results_zlib_pruning_comparison/sample_details.csv`; the aggregate is in `results_zlib_pruning_comparison/summary.csv`.
