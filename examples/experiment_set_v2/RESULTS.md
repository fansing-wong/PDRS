# V2 experiment results

## Dataset and method

The second round used 10 independently generated PNG files at sizes from 8×8 through 128×128 pixels. Each source was used to create a paired baseline, truncated, and fragmented image; a decoy-signature image contained no genuine file. This produced 40 distinct raw images. Each image was scanned five times, for 200 CLI runs total. Repeated runs provide timing repetitions; the independent sample count remains 10 per scenario.

## Accuracy summary

| Scenario | Independent samples | Header detections | False positives | Exact SHA-256 recovery | Candidate precision | Header recall | Exact recovery rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 10 | 50/50 trials | 0 | 50/50 trials; 10/10 unique sources | 100% | 100% | 100% |
| Truncated | 10 | 50/50 trials | 0 | 0/50 trials; 0/10 unique sources | 100% | 100% | 0% |
| Decoy signature | 10 | 0 true detections | 50/50 trials | Not applicable | 0% | Not applicable | Not applicable |
| Fragmented | 10 | 50/50 trials | 0 | 0/50 trials; 0/10 unique sources | 100% | 100% | 0% |

Across all four conditions and 200 runs, there were 150 candidates at true file-header offsets and 50 false-positive candidates from the decoy condition. Overall candidate precision was 150/200 (**75%**). For the 30 genuine source-condition pairs (10 each for baseline, truncation, and fragmentation), header detection recall was 30/30 (**100%**) and exact recovery was 10/30 (**33.3%**).

Repeated trials did not create new independent samples. The unique-source exact recovery rates were 10/10 for baseline, 0/10 for truncation, and 0/10 for fragmentation.

## End-to-end CLI timing

| Scenario | Mean (s) | Median (s) | Min–max (s) |
|---|---:|---:|---:|
| Baseline | 0.431303 | 0.424299 | 0.393592–0.578956 |
| Truncated | 0.430375 | 0.423314 | 0.394122–0.544041 |
| Decoy signature | 0.430964 | 0.426013 | 0.404256–0.488537 |
| Fragmented | 0.432809 | 0.421582 | 0.397791–0.648699 |

Times include Python startup and manifest writing. The input images are small, so these measurements are dominated by command startup and should not be interpreted as scan throughput or large-image performance.

## Findings

1. Signature scanning found every expected PNG header in the three positive scenarios.
2. Exact recovery succeeded only for intact contiguous files.
3. Every decoy image generated a candidate, showing that header and end-marker matching alone cannot distinguish a valid PNG from crafted bytes.
4. Truncated and fragmented candidates were detected but did not match the original SHA-256. Candidate detection and exact content recovery are separate outcomes.
5. The `complete_boundary` field is not a validity score. In particular, a decoy or a fragmented candidate may have an end marker while still being invalid or corrupted.

## Scope limits

This dataset tests synthetic PNG files and marker-based carving. It does not establish performance on real disk images or other formats. The scenario design uses one source file per independent sample, paired across positive conditions. Additional work should validate PNG chunk lengths and CRCs, add varied file types, test larger raw images, and measure memory and throughput separately.
