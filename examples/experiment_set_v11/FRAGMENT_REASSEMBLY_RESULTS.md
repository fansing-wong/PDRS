# V11 chunk-aligned PNG fragment reassembly results

## Method

Ten independent RGB8 PNG sources were encoded with two consecutive IDAT chunks, each with a valid CRC. Four raw-image scenarios were created for each source: contiguous baseline, and a 64-, 512-, or 4096-byte gap inserted between the two IDAT chunks. The gap search limit was 4096 bytes. The experimental reassembler scans for a PNG signature, validates chunk CRCs, and skips a bounded gap only when it can find the next valid IDAT or IEND chunk.

The standard PDRS carver and the experimental reassembler were both run on all 40 images. Reassembled bytes were checked against source SHA-256 and decoded with Pillow for pixel equality.

## Results

| Scenario | Samples | PDRS candidates found | Complete boundary | PDRS format-valid | PDRS exact source hash | Reassembly success | Reassembled exact hash | Pillow decoded | Pixels equal source |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Contiguous baseline | 10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| 64-byte IDAT gap | 10 | 10/10 | 10/10 | 0/10 | 0/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| 512-byte IDAT gap | 10 | 10/10 | 10/10 | 0/10 | 0/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| 4096-byte IDAT gap | 10 | 10/10 | 10/10 | 0/10 | 0/10 | 10/10 | 10/10 | 10/10 | 10/10 |

PDRS found all PNG headers and IEND boundaries. For the 30 fragmented files, the ordinary candidate still contained the inserted bytes, so its PNG validator rejected it and its hash differed from the source. The chunk-aware reassembler removed exactly one gap per file and recovered all 30 source byte streams exactly. Pillow decoded all 40 outputs and confirmed pixel equality.

## Interpretation and limits

This experiment demonstrates recovery only when one gap lies between two intact, CRC-valid IDAT chunks and is no larger than the configured 4096-byte search limit. It does not test a split inside an IDAT payload, multiple gaps, reordered fragments, missing chunks, or a gap larger than the limit. The reassembler is a separate research script and is not integrated into the PDRS CLI.
