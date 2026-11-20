# V12 PNG reassembly boundary-limit results

## Method

V12 used ten independent RGB8 PNG sources, each encoded with two IDAT chunks. Four scenarios were generated per source: contiguous baseline, a 4096-byte gap between IDAT chunks, an 8192-byte gap between IDAT chunks, and a 64-byte gap inserted inside the first IDAT payload. The reassembler retained its 4096-byte forward-search limit from V11.

The gap inside the IDAT payload was inserted without updating that chunk's declared length or CRC. The first IDAT payload was 18,490 bytes, so the next intact IDAT header lies beyond the reassembler's search window after the chunk CRC fails.

## Results

| Scenario | Samples | PDRS candidate found | PDRS complete boundary | PDRS format-valid | PDRS exact hash | Reassembly found | Reassembled exact hash | Pillow decode and pixels equal |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Contiguous baseline | 10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| 4096-byte gap between IDAT chunks | 10 | 10/10 | 10/10 | 0/10 | 0/10 | 10/10 | 10/10 | 10/10 |
| 8192-byte gap between IDAT chunks | 10 | 10/10 | 10/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |
| 64-byte gap inside IDAT payload | 10 | 10/10 | 10/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |

All 40 PNG headers and end boundaries were found. The V11 reassembler recovered the baseline and the 4096-byte aligned gap, including the maximum configured gap. It recovered none of the 8192-byte gaps or the internal-IDAT gaps. All 20 successful outputs matched source SHA-256 and decoded pixels; the other 20 produced no reassembled output.

## Interpretation and limits

The positive and negative controls confirm the current method's boundary: one gap between intact, CRC-valid IDAT chunks is recoverable up to and including 4096 bytes. A gap larger than the search limit or one inside a chunk is not. This is a bounded research method, not a general fragmented-file recovery algorithm.
