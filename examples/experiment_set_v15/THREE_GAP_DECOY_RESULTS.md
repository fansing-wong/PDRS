# V15 three-gap PNG reassembly results

## Method

V15 reused the 10 distinct PNG source images from V13 and re-encoded each as four CRC-valid IDAT chunks. It compared a contiguous baseline, three ordinary gaps of 64, 128, and 256 bytes, and the same three gaps containing respectively 1, 2, and 3 CRC-valid IDAT decoys (six decoys total). Each gap remained within the experimental reassembler's 4096-byte search limit. The greedy V11 method and Pillow-validated V13 backtracking method were timed separately for each of the 30 images. PDRS carving was also run on every raw image.

## Results

| Scenario | Samples | Gap sizes | Decoys | PDRS format valid | Greedy exact hash / decode | Backtracking exact hash / decode / pixels equal | Mean backtracking time |
|---|---:|---|---:|---:|---:|---:|---:|
| Contiguous baseline | 10 | None | 0 | 10/10 | 10/10 | 10/10 | 0.003854 s |
| Three ordinary gaps | 10 | 64, 128, 256 bytes | 0 | 0/10 | 10/10 | 10/10 | 0.006089 s |
| Three gaps with decoys | 10 | 64, 128, 256 bytes | 6 (1+2+3) | 0/10 | 0/10 | 10/10 | 0.127428 s |

For the decoy condition, greedy selection failed to recover a decodable PNG in all 10 samples. Backtracking recovered a PNG in all 10, with the source SHA-256 and decoded pixels matching exactly. Its mean runtime was about 20.9 times the three-gap no-decoy condition. The maximum measured time for the six-decoy samples was 0.162652 seconds. These timings cover only the experimental reconstruction function and validation on these small synthetic PNGs; they are not CLI or large-image performance measurements.

## Interpretation and limits

This result extends the tested backtracking layout to three IDAT gaps and six CRC-valid, zlib-invalid decoys. It does not establish a general bound for arbitrary gaps, decoys, chunk orders, IDAT-internal damage, or other formats. Search can grow as candidate chunks branch, and full Pillow decoding is part of path acceptance. The experimental reassembler remains a separate research script and is not integrated into the PDRS CLI.

Detailed per-image measurements are in `results_three_gap_backtracking/sample_details.csv`; scenario aggregates are in `results_three_gap_backtracking/scenario_summary.csv`.
