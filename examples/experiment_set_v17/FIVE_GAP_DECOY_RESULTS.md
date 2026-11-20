# V17 five-gap PNG reassembly results

## Method

V17 reused the 10 distinct PNG source images from V13 and re-encoded each as six CRC-valid IDAT chunks. It compared a contiguous baseline, five ordinary gaps of 64, 128, 256, 512, and 1024 bytes, and the same five gaps containing respectively 1, 2, 3, 4, and 5 CRC-valid IDAT decoys (15 decoys total). The gaps remained within the 4096-byte per-gap search limit. PDRS carving, greedy reassembly, and Pillow-validated backtracking were run on 30 images.

## Results

| Scenario | Samples | Gap sizes | Decoys | PDRS format valid / exact hash | Greedy exact hash / decode | Backtracking exact hash / decode / pixels equal | Mean backtracking time |
|---|---:|---|---:|---:|---:|---:|---:|
| Contiguous baseline | 10 | None | 0 | 10/10 | 10/10 | 10/10 | 0.004266 s |
| Five ordinary gaps | 10 | 64, 128, 256, 512, 1024 bytes | 0 | 0/0 | 10/10 | 10/10 | 0.009816 s |
| Five gaps with decoys | 10 | 64, 128, 256, 512, 1024 bytes | 15 (1+2+3+4+5) | 0/0 | 0/10 | 10/10 | 15.327268 s |

If each gap were restricted to its nearest real chunk or local decoy, the designed layout would have 2, 3, 4, 5, and 6 choices at successive gaps. The current implementation instead scans forward up to 4096 bytes at each step, so later IDAT chunks can also become choices and the actual path count exceeds that simple product. Greedy selection failed on all 10 decoy samples; full-decode backtracking recovered the source hash and matching pixels in all 10. Mean backtracking time was about 1,561 times the ordinary five-gap condition and 9.5 times V16's four-gap, ten-decoy condition. The maximum measured time was 17.474202 seconds per sample.

These one-pass timings cover the experimental reconstruction and validation functions on small synthetic PNGs. They exclude CLI startup and do not establish worst-case runtime or memory use. Recovery remained correct in this tested layout, but the runtime increase makes unpruned path search impractical as candidate branches continue to grow.

## Interpretation and limits

This result extends the tested layout to five IDAT gaps and 15 CRC-valid, zlib-invalid decoys. It does not establish a general bound for arbitrary gaps, decoys, chunk orders, IDAT-internal damage, or other formats. Candidate-path search grows rapidly, and full Pillow decoding is part of path acceptance. The experimental reassembler remains separate from PDRS CLI. Incremental zlib validation is a possible pruning step to evaluate before considering integration.

V18 instrumented the five-gap search and measured an average of 14,543 Pillow path validations per image. Its pruning comparison and counters are in `ZLIB_PRUNING_COMPARISON_RESULTS.md` and `results_zlib_pruning_comparison/summary.csv`.

Detailed per-image measurements are in `results_five_gap_backtracking/sample_details.csv`; scenario aggregates are in `results_five_gap_backtracking/scenario_summary.csv`.
