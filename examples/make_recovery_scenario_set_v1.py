"""Create a synthetic SQLite deletion and media-damage scenario set."""
from __future__ import annotations

import csv
import hashlib
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "recovery_scenario_set_v1"
IMAGE_DIR = ROOT / "images"
SOURCE_DIR = ROOT / "sources"
TRUTH_PATH = ROOT / "ground_truth.csv"
IMAGE_OFFSET = 4096


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    if ROOT.exists():
        raise SystemExit(f"Refusing to overwrite existing scenario set: {ROOT}")
    IMAGE_DIR.mkdir(parents=True)
    SOURCE_DIR.mkdir()

    source_path = SOURCE_DIR / "app_messages.sqlite"
    connection = sqlite3.connect(source_path)
    try:
        connection.execute("PRAGMA page_size=1024")
        connection.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO messages (body) VALUES (?)",
            [(f"Synthetic recovery-study message {i:03d}: " + ("sample-data " * 12),) for i in range(80)],
        )
        connection.commit()
        root_page = connection.execute(
            "SELECT rootpage FROM sqlite_schema WHERE name='messages'"
        ).fetchone()[0]
    finally:
        connection.close()

    source = source_path.read_bytes()
    page_size = int.from_bytes(source[16:18], "big")
    if root_page < 2 or len(source) < page_size * 3:
        raise RuntimeError("Synthetic SQLite fixture is too small for the planned damage scenario")

    scenarios: list[tuple[str, str, bytes, str]] = []
    scenarios.append((
        "deleted_file_carve_model",
        "deleted_file_carve_model.img",
        source,
        "Complete database bytes remain at an unallocated-area offset; this models lost directory metadata only.",
    ))

    damaged = bytearray(source)
    damaged_page_start = (root_page - 1) * page_size
    damaged[damaged_page_start : damaged_page_start + 512] = b"\0" * 512
    scenarios.append((
        "zero_filled_sector_in_database",
        "zero_filled_sector.img",
        bytes(damaged),
        "One 512-byte region inside a SQLite B-tree page is zero-filled; this is a byte-loss simulation, not a real bad-sector read.",
    ))

    truncated = source[:-512]
    scenarios.append((
        "image_truncated_after_partial_database",
        "truncated_image.img",
        truncated,
        "The image ends before the full SQLite page count; this simulates missing tail bytes.",
    ))

    truth_rows = []
    scenario_rows = []
    for scenario, filename, payload, description in scenarios:
        prefix = b"PDRS-SYNTHETIC-UNALLOCATED-AREA\0"
        trailer = b"" if scenario == "image_truncated_after_partial_database" else b"\0" * 1024
        image_data = prefix + b"\0" * (IMAGE_OFFSET - len(prefix)) + payload + trailer
        (IMAGE_DIR / filename).write_bytes(image_data)
        truth_rows.append({
            "scenario": scenario,
            "image_filename": filename,
            "source_filename": source_path.name,
            "target_present": "true",
            "expected_offset": IMAGE_OFFSET,
            "expected_sha256": sha256(source),
        })
        scenario_rows.append({
            "scenario": scenario,
            "image_filename": filename,
            "description": description,
            "source_bytes": len(source),
            "scenario_bytes": len(payload),
            "expected_offset": IMAGE_OFFSET,
        })

    with TRUTH_PATH.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(truth_rows[0]))
        writer.writeheader()
        writer.writerows(truth_rows)
    with (ROOT / "scenario_notes.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(scenario_rows[0]))
        writer.writeheader()
        writer.writerows(scenario_rows)

    print(f"Scenario images: {len(scenarios)}")
    print(f"Images:         {IMAGE_DIR}")
    print(f"Source database:{source_path}")
    print(f"Ground truth:   {TRUTH_PATH}")
    print("The damage conditions are synthetic; no physical disk is accessed.")


if __name__ == "__main__":
    main()
