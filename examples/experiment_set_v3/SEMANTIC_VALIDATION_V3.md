# IDAT decompression validation results

## Test set

The v3 dataset contains 10 valid PNG controls and 10 PNG-shaped decoys with valid chunk lengths, ordering, and CRCs. The decoys use an invalid zlib stream in the IDAT chunk. Each image was scanned once with the v0.3 prototype.

## Results

| Scenario | Samples | Candidates | PNG validation pass | Exact SHA-256 matches | False-positive rejection |
|---|---:|---:|---:|---:|---:|
| Valid controls | 10 | 10 | 10/10 | 10/10 | Not applicable |
| CRC-consistent invalid IDAT | 10 | 10 | 0/10 | 0/10 | 10/10 (100%) |

The scanner still emitted a candidate for each decoy header, but IDAT decompression rejected every decoy. All control PNGs passed validation and matched their source hashes.

## Timing observations

| Scenario | Mean (s) | Median (s) | Range (s) |
|---|---:|---:|---:|
| Valid controls | 0.720815 | 0.571043 | 0.477858–2.141420 |
| CRC-consistent invalid IDAT | 0.534851 | 0.519670 | 0.482243–0.654679 |

One valid-control run took 2.141420 seconds and strongly raised that group's mean. These scans were single runs on small images; timing should be treated as noisy end-to-end CLI observations, not an algorithm throughput result.

## Interpretation and limits

This experiment confirms that chunk and CRC checks alone were insufficient: the prior version accepted all 10 invalid-IDAT decoys. Adding zlib decompression and checking decoded scanline length rejected all 10 while retaining all 10 controls.

The result applies to this synthetic decoy construction. The validator supports non-interlaced PNGs in a defined color/depth profile, enforces compressed and decoded size caps, and does not render the image. It has not been compared against a comprehensive independent PNG decoder across a broad real-world corpus.
