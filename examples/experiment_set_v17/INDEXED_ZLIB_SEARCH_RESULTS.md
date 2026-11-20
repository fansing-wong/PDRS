# V20 indexed CRC-chunk search results

## Method

V20 used the same ten five-gap, 15-decoy images from V17. It retained incremental zlib validation and required a complete zlib stream before Pillow validation, but changed candidate discovery: it scans each image once for CRC-valid IDAT/IEND chunks, stores their offsets, and uses binary search to find candidates inside each 4096-byte forward window. The earlier V19 implementation recalculated chunk CRCs while rescanning the same windows at every recursion node.

## Results

| Method | Mean time per image | Change from V17 | Exact hash / Pillow / pixels |
|---|---:|---:|---:|
| V17 full backtracking | 15.327268 s | Baseline | 10/10 / 10/10 / 10/10 |
| V19 zlib EOF pruning with repeated window scans | 13.451050 s | 1.14× faster | 10/10 / 10/10 / 10/10 |
| V20 one-pass chunk index + zlib EOF pruning | 0.988780 s | 15.50× faster | 10/10 / 10/10 / 10/10 |

The V20 run indexed 22 CRC-valid IDAT/IEND chunks per image and visited a mean of 29,397 search nodes. It rejected 7,190 branches on zlib errors and 145,420 incomplete zlib paths; only 10 complete paths reached Pillow, one accepted path per image. No returned image differed from the expected source hash or decoded pixels.

## Interpretation and limits

The main gain came from avoiding repeated CRC work over overlapping 4096-byte windows. EOF gating also avoided tens of thousands of unnecessary Pillow decodes. This is a promising optimization for the tested layout, but the comparison uses one run on small synthetic images derived from the V13 sources. The full byte-by-byte index scan, memory use, larger images, other valid PNG variants, and additional candidate distributions still need evaluation. This remains a separate experimental script and is not integrated into the PDRS CLI.

Per-image timings and counters are in `results_indexed_zlib_search/sample_details.csv`; the aggregate is in `results_indexed_zlib_search/summary.csv`.
