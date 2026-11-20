# V13 CRC-valid IDAT decoy results

## Method

V13 reused ten valid two-IDAT PNG sources. It created three raw-image scenarios per source: contiguous baseline, a simple 64-byte gap between IDAT chunks, and a 64-byte gap containing a 22-byte IDAT decoy chunk with a valid CRC but invalid zlib data. The experiment compared the V11 greedy chunk search with a backtracking version that accepts a reconstructed path only if Pillow fully decodes the PNG.

## Results

| Scenario | Samples | PDRS format-valid | PDRS exact hash | Greedy found path | Greedy exact hash | Greedy decoded | Backtracking exact hash | Backtracking decoded and pixels equal |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Contiguous baseline | 10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| Simple 64-byte gap | 10 | 0/10 | 0/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| CRC-valid decoy in 64-byte gap | 10 | 0/10 | 0/10 | 10/10 | 0/10 | 0/10 | 10/10 | 10/10 |

The greedy search selected the decoy chunk in all ten decoy images. Its reconstructed outputs failed Pillow decoding and did not match the source hash. The backtracking version rejected those paths after decode failure, tried the next CRC-valid chunk candidate, and recovered all ten source PNGs exactly. Baseline and simple-gap outputs also remained exact.

## Interpretation and limits

A valid chunk CRC confirms the bytes of that chunk, but does not establish that its payload belongs in the PNG's compressed image stream. Backtracking plus full decode distinguished this decoy from the real next IDAT in this controlled case. The prototype remains limited to PNGs with one bounded gap between intact chunks, uses Pillow as a semantic validator, and is not integrated into the PDRS CLI. More decoy layouts and multiple gaps remain untested.
