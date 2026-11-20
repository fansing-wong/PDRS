# Adam7 PNG compatibility results

## Method

The v5 set contains 10 ordinary non-interlaced RGBA controls and 10 manually encoded Adam7 RGBA PNGs, paired by dimensions from 8×13 through 128×75. Pillow decoded every source file before scanning. PDRS carved each image; SHA-256, PNG validation, independent Pillow decoding, dimensions, mode, and decoded pixel bytes were compared with the corresponding source.

## Results

| Kind | Samples | Candidates found | PDRS PNG validation | SHA-256 matches | Pillow decodes | Pixel/mode matches |
|---|---:|---:|---:|---:|---:|---:|
| Non-interlaced controls | 10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| Adam7 interlaced | 10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |

All Adam7 files had IHDR interlace flag 1. The earlier Pillow compatibility experiment had no interlaced files, so this is the first actual Adam7 coverage in the project.

## Interpretation and limits

The v0.4 pass-layout and scanline-length checks accepted all 10 independently decoded Adam7 samples and preserved their bytes exactly. This confirms compatibility for this paired RGBA8 dataset. It does not cover Adam7 with palette/grayscale modes, every legal PNG bit depth, malformed pass data, or real-world image collections.
