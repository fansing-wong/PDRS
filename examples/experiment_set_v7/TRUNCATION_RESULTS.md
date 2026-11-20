# JPEG/PDF truncation results

## Observed results

| Scenario | Samples | Candidates found | Boundary complete | PDRS parser-valid | Independent parser accepts | Exact source hash matches | Decoded content equals source |
|---|---:|---:|---:|---:|---:|---:|---:|
| JPEG EOI removed | 10 | 10/10 | 0/10 | 10/10 | 10/10 | 0/10 | 10/10 |
| JPEG cut at 60% | 10 | 10/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |
| PDF EOF removed | 10 | 10/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |
| PDF cut before xref | 10 | 10/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |

The JPEG EOI-missing result is notable: Pillow fully decodes all 10 candidates even though the EOI marker and original file hash are missing. A pixel-by-pixel comparison confirmed that all 10 decoded images exactly match their original pixels. For this controlled truncation, the encoded image data is complete and only the terminal marker was removed; the candidate also contains the 15-byte synthetic tail filler.

The other three conditions were rejected by the relevant parser. pypdf also emitted warnings while searching for the missing PDF EOF marker. The candidate headers were still found in all cases.

## Boundary behavior

When the end marker was absent, PDRS extended the candidate to the end of the raw image. Each candidate includes 15 bytes of synthetic trailing filler after the truncated source bytes. This explains why candidate size is larger than the embedded prefix and why SHA-256 cannot match the source.

## Interpretation and limits

`complete_boundary=False` records the missing terminator, while parser acceptance, decoded-content equality, and byte-hash equality measure different outcomes. Pillow can decode JPEG data without its final EOI marker; in these samples the pixels match even though the extracted bytes differ. The results are synthetic and do not establish recovery behavior for arbitrary JPEG/PDF truncations.
