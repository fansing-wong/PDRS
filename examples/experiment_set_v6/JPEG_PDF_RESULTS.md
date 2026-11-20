# JPEG and PDF carving results

## Method

The v6 dataset contains 10 valid JPEGs and 10 valid PDFs generated with independent libraries, plus 10 JPEG marker decoys and 10 PDF header/EOF decoys. Each image was scanned once. True samples were checked by SHA-256; JPEGs were fully decoded with Pillow; PDFs were parsed using pypdf `PdfReader(strict=True)` and their page count and media box were compared with the originals.

## Results

| Scenario | Samples | Candidates found | True header detections | False positives | Exact hashes | Independent parser accepts | Content equivalent |
|---|---:|---:|---:|---:|---:|---:|---:|
| JPEG valid | 10 | 10/10 | 10/10 | 0 | 10/10 | 10/10 | 10/10 |
| JPEG decoy | 10 | 10/10 | 0 | 10/10 | 0 | 0/10 | Not applicable |
| PDF valid | 10 | 10/10 | 10/10 | 0 | 10/10 | 10/10 | 10/10 |
| PDF decoy | 10 | 10/10 | 0 | 10/10 | 0 | 0/10 | Not applicable |

The marker scanner located all 40 candidate starts. Each valid source was carved byte-for-byte and independently accepted. Each decoy was also carved, but all were rejected by the independent parser. For both formats, raw candidate precision across valid and decoy samples was 10/20 (**50%**); independent parser filtering reduced the accepted set to the 10 valid samples (100% precision for this constructed corpus).

## Error examples and interpretation

- Pillow rejected JPEG decoys with `OSError: Truncated File Read`.
- pypdf in strict mode rejected PDF decoys with `PdfReadError: startxref not found`.
- The scanner's `complete_boundary` indicator is not proof of a valid JPEG or PDF. It means only that an EOI or EOF marker was found.
- Parser rejection does not remove the carved candidate; the manifest and bytes remain available for review.

## Limits

There are 10 independent valid samples and 10 decoys per format, all synthetic. This does not establish performance on fragmented JPEG/PDF files, incremental PDFs, unusual JPEG marker layouts, or real disk images. The PDF check verifies parsing and page properties; it does not compare rendered page appearance.
