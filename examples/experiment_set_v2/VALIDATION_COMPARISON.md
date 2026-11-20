# PNG structural validation comparison

## Observed results

The v0.2 validator was run once on each of the same 40 v2 images. It checks PNG chunk lengths, required IHDR/IDAT/IEND chunks, exact IEND boundary, and CRCs.

| Scenario | Candidate headers | Candidates passing PNG validation | Exact SHA-256 matches | Mean end-to-end time (s) |
|---|---:|---:|---:|---:|
| Baseline | 10/10 | 10/10 | 10/10 | 0.450331 |
| Truncated | 10/10 | 0/10 | 0/10 | 0.474853 |
| Decoy signature | 0 genuine; 10 decoy candidates | 0/10 | 0/10 | 0.477626 |
| Fragmented | 10/10 | 0/10 | 0/10 | 0.481501 |

## Comparison with signature-only scanning

- Signature-only scanning emitted a candidate for all 10 decoy images. PNG structural validation marked all 10 invalid, a **100% rejection rate for the synthetic decoys**.
- All 10 intact baseline PNGs passed structure/CRC checks and matched the original SHA-256.
- All 10 truncated and all 10 fragmented candidates failed structural validation. Their candidate headers were still located, but their extracted content was not a valid complete PNG under the implemented checks.
- The validator adds a quality classification; it does not delete candidate files. This preserves potentially useful partial data while exposing that it failed validation.
- Across this dataset, 10 candidates passed validation and all 10 corresponded to intact source files. This is a synthetic result and should not be generalized to other PNGs or formats without additional samples.

## Timing note

The 40 validation scans were run once each and include process startup and manifest writing. Their mean times range from about 0.45 to 0.48 seconds. These values should not be directly compared to the earlier five-run timing study because the run protocols differ and startup noise is large relative to these small images.

## Interpretation

The change separates three questions: whether a signature was found, whether an end marker was found, and whether the candidate passes the implemented PNG structural checks. In this sample set, CRC and chunk validation eliminated the signature-only decoy while preserving the intact baseline. Truncation and fragmentation were classified as invalid rather than exact recoveries. The experiment does not yet assess maliciously crafted PNGs with internally consistent CRCs, other file formats, or real-world disk images.
