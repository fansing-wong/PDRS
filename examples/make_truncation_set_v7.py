"""Create controlled JPEG/PDF truncation cases from the v6 valid sources."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path


EXAMPLES = Path(__file__).resolve().parent
SOURCE_DIR = EXAMPLES / "experiment_set_v6" / "sources"
ROOT = EXAMPLES / "experiment_set_v7"
IMAGE_DIR = ROOT / "images"
COPIED_SOURCES = ROOT / "sources"
SAMPLE_COUNT = 10


def _truncated_content(fmt: str, scenario: str, source: bytes) -> tuple[bytes, str]:
    if fmt == "jpeg" and scenario == "jpeg_eoi_missing":
        if not source.endswith(b"\xff\xd9"):
            raise ValueError("Source JPEG does not end with an EOI marker")
        return source[:-2], "Only the final JPEG EOI marker was removed"
    if fmt == "jpeg" and scenario == "jpeg_mid_truncated":
        return source[: int(len(source) * 0.60)], "JPEG was cut at 60% of its original byte length"
    if fmt == "pdf" and scenario == "pdf_eof_missing":
        marker = source.rfind(b"%%EOF")
        if marker < 0:
            raise ValueError("Source PDF has no EOF marker")
        return source[:marker], "PDF %%EOF marker and trailing bytes were removed"
    if fmt == "pdf" and scenario == "pdf_xref_missing":
        marker = source.rfind(b"\nxref\n")
        if marker < 0:
            raise ValueError("Source PDF has no classic xref table")
        return source[:marker], "PDF was cut immediately before the xref table"
    raise ValueError(f"Unsupported truncation condition: {fmt}/{scenario}")


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {ROOT}\nMove it aside or use a fresh project copy.")
    if not SOURCE_DIR.is_dir():
        raise SystemExit("Valid sources not found. Run the v6 JPEG/PDF dataset generator first.")
    IMAGE_DIR.mkdir(parents=True)
    COPIED_SOURCES.mkdir(parents=True)
    rows: list[dict[str, object]] = []

    for sample_number in range(1, SAMPLE_COUNT + 1):
        sample_id = f"sample_{sample_number:02d}"
        for fmt, conditions in (
            ("jpeg", ("jpeg_eoi_missing", "jpeg_mid_truncated")),
            ("pdf", ("pdf_eof_missing", "pdf_xref_missing")),
        ):
            source_path = SOURCE_DIR / f"{sample_id}.{fmt}"
            source = source_path.read_bytes()
            copy_path = COPIED_SOURCES / source_path.name
            if not copy_path.exists():
                copy_path.write_bytes(source)
            for scenario in conditions:
                content, note = _truncated_content(fmt, scenario, source)
                prefix = f"PDRS-TRUNC-{scenario}-{sample_id}\x00".encode("ascii") + bytes([0x30 + sample_number]) * 47
                offset = len(prefix)
                image_name = f"{scenario}_{sample_id}.img"
                (IMAGE_DIR / image_name).write_bytes(prefix + content + b"\x00PDRS-TRUNC-END")
                rows.append({
                    "scenario": scenario,
                    "sample_id": sample_id,
                    "format": fmt,
                    "image_filename": image_name,
                    "source_filename": source_path.name,
                    "expected_offset": offset,
                    "original_size_bytes": len(source),
                    "original_sha256": hashlib.sha256(source).hexdigest(),
                    "included_source_bytes": len(content),
                    "scenario_note": note,
                })

    with (ROOT / "ground_truth.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Truncation images: {len(rows)} (10 samples x 4 conditions)")
    print(f"Images:      {IMAGE_DIR}")
    print(f"Sources:     {COPIED_SOURCES}")
    print(f"Ground truth:{ROOT / 'ground_truth.csv'}")


if __name__ == "__main__":
    main()
