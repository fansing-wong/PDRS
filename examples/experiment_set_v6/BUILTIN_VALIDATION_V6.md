# PDRS v0.5 built-in JPEG/PDF validation comparison

## Results

| Scenario | Samples | PDRS accepted | Independent parser accepted | Agreement |
|---|---:|---:|---:|---:|
| JPEG valid | 10 | 10/10 | 10/10 | 10/10 |
| JPEG decoy | 10 | 0/10 | 0/10 | 10/10 |
| PDF valid | 10 | 10/10 | 10/10 | 10/10 |
| PDF decoy | 10 | 0/10 | 0/10 | 10/10 |

All 40 candidates were still emitted. PDRS v0.5 set `format_valid=True` for every valid JPEG/PDF and `False` for every decoy. These statuses agreed with Pillow and pypdf strict parsing for all 40 samples.

Representative validation notes:

- Valid JPEG: “Pillow fully decoded JPEG candidate”.
- JPEG decoy: Pillow rejected it with `OSError: Truncated File Read`.
- Valid PDF: pypdf parsed a one-page PDF candidate.
- PDF decoy: pypdf rejected it with `PdfReadError: startxref not found`.

This is a 40-file synthetic comparison. Agreement here does not prove the optional validators cover every legal JPEG/PDF feature or every real-world malformed file.
