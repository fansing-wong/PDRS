# Independent Pillow cross-validation

## Method

Pillow 13.0.0 was used as an independent PNG decoder on the recovered candidates. Each candidate was fully loaded with `Image.load()`. For valid controls, decoded pixels and dimensions were compared with the corresponding original source PNG. The CRC-consistent invalid-IDAT decoys were submitted to the same decoder.

## Results

| Scenario | Samples | Pillow decoded as PNG | Pixel-exact match to source | Outcome |
|---|---:|---:|---:|---|
| Valid controls | 10 | 10/10 | 10/10 | All candidates decoded and matched their source pixels. |
| CRC-consistent invalid IDAT decoys | 10 | 0/10 | Not applicable | Pillow rejected all decoys with `OSError: broken data stream when reading image file`. |

The result independently agrees with the PDRS v0.3 validator for this sample set: valid controls pass, invalid compressed streams fail. The pixel comparison gives stronger confirmation for the controls than a container-level check alone.

## Limits

This is a 20-file synthetic sample. It does not establish compatibility across the full PNG specification, such as Adam7 interlacing or unusual legal chunk combinations. Pillow is independent of PDRS, but both results still depend on the quality of this constructed dataset.
