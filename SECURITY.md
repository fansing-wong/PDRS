# Security policy

PDRS is an educational prototype and is not designed as a hardened service for arbitrary hostile inputs. Parsers and optional validation libraries process bytes from the supplied image.

## Safe use

- Use synthetic images or authorized image copies, not a live disk or irreplaceable source. PDRS accepts regular image files and does not provide direct physical-device acquisition.
- Keep the source image separate from the output directory and retain an untouched original. The bundled damage scenarios alter only generated copies and use zero-fill/truncation as test surrogates.
- Treat carved/recovered files as untrusted. Do not open recovered documents or images in applications you do not trust. FAT32 deleted-entry recovery is experimental and assumes contiguous file data.
- Keep Python and the optional Pillow/pypdf dependencies current.

## Reporting a vulnerability

For a public GitHub repository with private vulnerability reporting enabled, use its private Security Advisory reporting flow. Otherwise, contact the repository owner privately before publishing details. Do not attach private images, recovered files, or personal data to a public issue.