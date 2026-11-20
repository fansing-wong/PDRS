# V22 fast candidate-index results

## Method

V22 refined V21's lazy window index. V21 called the general PNG chunk parser at every offset in each search window. A profile showed that random byte sequences could produce plausible large chunk lengths, causing CRC calculations over large ranges even when the chunk type was not IDAT or IEND. V22 checks the four-byte chunk type first and computes length and CRC only for IDAT/IEND candidates. It retains the lazy window cache, zlib EOF gate, and final Pillow validation.

The decoy comparison used all ten five-gap, 15-decoy images from V17. A scale control padded one decoy image with zeros to 1, 16, and 64 MiB and repeated each size three times. These are repeated measurements of one image, not independent image samples.

## Results

| Raw image size | V21 general parser, one run | V22 type-prefiltered mean | V22 range | Exact hash and pixels |
|---:|---:|---:|---:|---:|
| 1 MiB | 1.010 s | 0.969836 s | 0.720880–1.270406 s | 3/3 |
| 16 MiB | 2.858 s | 1.003839 s | 0.905413–1.095558 s | 3/3 |
| 64 MiB | 16.156 s | 1.101726 s | 0.833817–1.536067 s | 3/3 |

Across the ten V17 decoy images, V22 recovered exact hashes and pixels in 10/10. Its one-pass mean was 1.268551 seconds per image, about 12.08 times faster than V17's full-backtracking mean. The fast candidate index also recovered all 20 V17 baseline and ordinary-gap images exactly. The repeated size control showed no clear time increase from 1 to 64 MiB after the chunk-type prefilter, while V21's general parser became much slower on padded data.

## Interpretation and limits

The profile-guided type check avoids expensive CRC calculations for arbitrary byte sequences that cannot be IDAT or IEND chunks. The 1–64 MiB result is promising for this zero-padded synthetic image, but it is not a general large-disk benchmark: there was one source image, three runs per size, and no independent background seeds. V23 adds one fixed-seed random-background sequence; more independent seeds and varied PNG contents are still needed. V22 remains an experimental reassembler, not a PDRS CLI feature. Further validation should cover larger varied images, memory use, and all supported PNG variants before integration.

The ten-image decoy comparison is in `results_fast_candidate_index/sample_details.csv`. Repeated size trials and their summary are in `results_fast_candidate_index/padded_scale_repeats.csv` and `results_fast_candidate_index/padded_scale_repeat_summary.csv`.
