# V16 four-gap PNG reassembly results

## Method

V16 reused the 10 distinct PNG source images from V13 and re-encoded each as five CRC-valid IDAT chunks. It compared a contiguous baseline, four ordinary gaps of 64, 128, 256, and 512 bytes, and the same four gaps containing respectively 1, 2, 3, and 4 CRC-valid IDAT decoys (10 decoys total). Each gap remained within the experimental reassembler's 4096-byte search limit. Greedy and Pillow-validated backtracking reassembly were measured for each of the 30 images; PDRS carving was also run.

## Results

| Scenario | Samples | Gap sizes | Decoys | PDRS format valid / exact hash | Greedy exact hash / decode | Backtracking exact hash / decode / pixels equal | Mean backtracking time |
|---|---:|---|---:|---:|---:|---:|---:|
| Contiguous baseline | 10 | None | 0 | 10/10 | 10/10 | 10/10 | 0.006444 s |
| Four ordinary gaps | 10 | 64, 128, 256, 512 bytes | 0 | 0/0 | 10/10 | 10/10 | 0.007651 s |
| Four gaps with decoys | 10 | 64, 128, 256, 512 bytes | 10 (1+2+3+4) | 0/0 | 0/10 | 10/10 | 1.610717 s |

If each gap were restricted to its nearest real chunk or local decoy, the designed layout would have 2, 3, 4, and 5 choices at successive gaps. The current implementation instead scans forward up to 4096 bytes at every step, so later IDAT chunks can also become choices and the actual number of paths is higher than that simple product. Greedy selection failed on all 10 decoy samples. Backtracking recovered the exact source hash and matching decoded pixels in all 10. Its mean runtime was about 210.5 times the ordinary four-gap condition and about 12.6 times V15's three-gap, six-decoy condition. The maximum measured time was 1.933265 seconds.

These are one-pass descriptive timings from small synthetic PNGs and the experimental reconstruction function. They exclude CLI startup and do not establish worst-case runtime or memory use. The results show that the tested layout is recoverable, while the extra candidate branches add substantial validation cost.

## Interpretation and limits

This result extends the tested backtracking layout to four IDAT gaps and 10 CRC-valid, zlib-invalid decoys. It does not establish a general bound for arbitrary gaps, decoys, chunk orders, IDAT-internal damage, or other formats. Search cost can grow with the number of candidate paths, and full Pillow decoding is part of path acceptance. The experimental reassembler remains separate from the PDRS CLI and is not integrated into it.

Detailed per-image measurements are in `results_four_gap_backtracking/sample_details.csv`; scenario aggregates are in `results_four_gap_backtracking/scenario_summary.csv`.
