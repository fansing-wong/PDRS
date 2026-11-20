# V14 two-gap PNG reassembly results

## Method

V14 used ten valid PNG sources, each encoded as three consecutive CRC-valid IDAT chunks. It compared three raw-image conditions: a contiguous baseline, two ordinary gaps of 64 and 128 bytes, and the same two gaps containing one CRC-valid but zlib-invalid IDAT decoy in the first gap and two in the second. The experiment compared the greedy V11 reassembler with the V13 backtracking version, which accepts a path only after Pillow fully decodes the rebuilt PNG.

## Results

| Scenario | Samples | Gaps | Decoy chunks | PDRS valid and exact | Greedy exact hash | Greedy Pillow decode | Backtracking exact hash | Backtracking decode and pixels equal |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Contiguous baseline | 10 | None | 0 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| Two ordinary gaps | 10 | 64 and 128 bytes | 0 | 0/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| Two gaps with CRC-valid decoys | 10 | 64 and 128 bytes | 3 total (1 and 2) | 0/10 | 0/10 | 0/10 | 10/10 | 10/10 |

The ordinary carver found the PNG boundary but rejected all 20 fragmented candidates. Greedy reassembly recovered the baseline and ordinary two-gap samples, but chose decoys in all ten decoy cases. Backtracking found a decodable path for all 30 samples and matched the source hash and pixels in each case.

## Interpretation and limits

This result supports backtracking across two gaps with the tested sizes and three decoys. It does not establish recovery across three or more gaps, arbitrary chunk ordering, gaps inside IDAT data, or every CRC-valid decoy. The experimental reassembler remains separate from the PDRS CLI and uses Pillow as its path acceptance check.
