# Synthetic carving experiment — observed results

## Result table

| Scenario | Ground truth | Scanner output | Interpretation |
|---|---|---|---|
| Baseline | PNG, offset 55, 78 bytes | 1 candidate, 78 bytes, matching SHA-256, boundary flag `True` | Exact recovery succeeded. |
| Truncated | PNG, offset 56, 78-byte original; only 66 bytes before the removed IEND chunk | 1 candidate, 97 bytes, SHA-256 mismatch, boundary flag `False` | The 66-byte prefix was extracted together with 31 bytes of trailing filler. The candidate is incomplete and is not an exact recovery. |
| Decoy signature | No genuine file | 1 PDF candidate, 52 bytes, boundary flag `True` | False positive. A PDF-like header plus `%%EOF` fooled the marker-based boundary rule. |
| Fragmented | PNG, offset 57, 78 source bytes split by 512 filler bytes | 1 candidate, 590 bytes, SHA-256 mismatch, boundary flag `True` | The scanner copied the gap between the fragments. It did not reconstruct the original file. |

## Summary metrics for this small demonstration

Treating detection of a ground-truth file header as a true detection (even when content recovery is incomplete):

- Candidate detections: 4 total; 3 correspond to inserted file headers and 1 is a decoy.
- Candidate precision: 3 / 4 = **75%**.
- Header detection recall: 3 / 3 = **100%**.
- Exact recovery rate among the 3 genuine file inputs: 1 / 3 = **33.3%**.

These values describe one synthetic example per condition; they demonstrate behavior and are not statistically reliable estimates of real-world performance. The decoy-only condition has no genuine target, so recall for that condition is undefined.

## Interpretation

The experiment separates three outcomes that should not be conflated:

1. **Signature detected** — the scanner found a possible file start.
2. **Boundary marker found** — a format-specific ending marker was located before the next candidate or image end.
3. **Exact recovery** — the extracted bytes have the same length and SHA-256 as the known original.

The current `complete_boundary` field represents only outcome 2. The decoy shows that a boundary marker does not establish that a file is valid. The fragmented case shows that a candidate can have a boundary marker while containing unrelated bytes. Hash comparison against ground truth establishes exact recovery in this experiment.

## Limitations and next experiment step

- One sample per condition is insufficient for a general performance claim. Expand the dataset with multiple files per format and repeat each timing condition at least five times.
- The JPEG demo fixture is marker-only and is not a decodable JPEG; do not include it in format-validity conclusions.
- The scanner currently does not validate PNG CRCs or parse PDF structure.
- Before claiming byte recovery for truncated or fragmented files, define precisely whether the metric counts contiguous matching bytes, any source bytes present, or successfully reassembled bytes.
- Preserve the raw images, ground-truth CSV, result manifests, and software version used for each run.
