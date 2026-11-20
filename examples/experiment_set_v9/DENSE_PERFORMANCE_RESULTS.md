# V9 randomized-background performance results

## Method

V9 contains nine raw images: three independently seeded 1 MiB images, three 16 MiB images, and three 64 MiB images. Each image was written with deterministic pseudorandom bytes across its full length, then overlaid with one known JPEG, PNG, and PDF at recorded offsets. Each image was scanned five times, for 45 end-to-end CLI scans. Windows reported that none of the files was marked as sparse. The operating-system file cache was not cleared between scans.

## Results

| Image size | Independent images | Scans | Mean time (s) | Median time (s) | Range (s) | Mean end-to-end throughput (MiB/s) | Mean candidates per scan | Unexpected candidates across scans | Exact source hashes |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 MiB | 3 | 15 | 0.706085 | 0.679126 | 0.613413–0.856031 | 1.428540 | 3.000 | 0 | 45/45 |
| 16 MiB | 3 | 15 | 0.799787 | 0.758948 | 0.653827–1.249580 | 20.500254 | 4.333 | 20 | 45/45 |
| 64 MiB | 3 | 15 | 0.907128 | 0.886592 | 0.800436–1.155310 | 71.184713 | 6.333 | 50 | 45/45 |

All 135 expected file instances were detected and matched their source SHA-256. The random backgrounds produced 14 distinct extra JPEG header positions: four across the three 16 MiB images and ten across the three 64 MiB images. Repeated five times, those became 20 and 50 unexpected candidate instances in the run log. There were no unexpected candidates in the 1 MiB images.

PDRS marked all 70 repeated extra candidates as `format_valid=False`; all expected candidates were parser-valid and hash-exact. The raw candidate precision across repeated scans was 100% for 1 MiB, 69.2% for 16 MiB, and 47.4% for 64 MiB. Filtering by the parser-valid flag raised precision to 100% on this constructed set. PDRS still saves invalid candidates for review.

## Interpretation and limits

The three-byte JPEG header `FF D8 FF` occurred 14 times in about 243 MiB of pseudorandom background, or roughly one extra header per 17.4 MiB in this dataset. This is consistent with accidental short-signature matches in random data. It does not estimate false-positive rates for real disks, which contain structured and repeated data rather than independent pseudorandom bytes.

Throughput is calculated from the full image size and end-to-end CLI time. It includes process startup, candidate validation, extracted-file writing, and manifest writing. The cache state was uncontrolled, each size has only three independent images, and the results do not isolate scan-loop speed or storage-device throughput. Peak memory was not measured.
