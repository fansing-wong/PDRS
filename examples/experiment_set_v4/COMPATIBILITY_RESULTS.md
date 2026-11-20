# PNG compatibility results

## Method

Pillow 13.0.0 generated 10 valid PNG controls covering RGB, RGBA, grayscale, 1-bit grayscale, palette, 16-bit grayscale, grayscale with alpha, and two larger files with different compression levels. The requested Adam7 option was also recorded from the actual PNG IHDR field. PDRS carved each image, then SHA-256 and decoded pixels were compared with the original using Pillow.

## Results

| Metric | Result |
|---|---:|
| Valid PNG variants | 10 |
| Candidates found at expected offsets | 10/10 |
| PDRS PNG structural checks passed | 10/10 |
| SHA-256 exact matches | 10/10 |
| Pillow decoded recovered candidates | 10/10 |
| Decoded pixel data matched source | 10/10 |
| Variants rejected by PDRS | 0/10 |
| Actual Adam7/interlace samples | 0 |

Every tested non-interlaced variant passed both PDRS validation and independent Pillow decoding, with matching source pixels. The variant named `rgb8_adam7_requested` had an actual interlace flag of 0; Pillow did not emit Adam7 for that save request. Therefore this experiment does not test interlaced PNG support.

## Interpretation

The results show no false rejection for these 10 valid PNG fixtures across the tested color modes, bit depths, dimensions, and compression settings. The sample remains small and does not represent every legal PNG combination. Adam7 support remains an explicit limitation and needs a real interlaced fixture before making any compatibility claim.
