# Implementation references

These references describe the file structures checked by the prototype. PDRS implements only a bounded subset and does not claim full format conformance.

- Microsoft, [BITMAPFILEHEADER structure](https://learn.microsoft.com/windows/win32/api/wingdi/ns-wingdi-bitmapfileheader): BMP file size and pixel-array offset fields.
- Microsoft, [BITMAPINFOHEADER structure](https://learn.microsoft.com/windows/win32/api/wingdi/ns-wingdi-bitmapinfoheader): dimensions, planes, bit depth, compression, and image size.
- Microsoft, [Bitmap Storage](https://learn.microsoft.com/en-us/windows/win32/gdi/bitmap-storage): DIB layout and pixel-array organization.

The BMP validator checks supported header sizes, basic fields, palette/mask offsets, and declared pixel-array bounds. It does not decode pixels, validate all masks, or support every BMP-family variant.