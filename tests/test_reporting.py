from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pdrs.evaluation import EvaluationResult
from pdrs.reporting import build_experiment_report, write_new_report


class ReportingTests(unittest.TestCase):
    def test_report_records_hash_and_ground_truth_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.img"
            source.write_bytes(b"synthetic image")
            stat = source.stat()
            digest = hashlib.sha256(b"candidate").hexdigest()
            rows = [
                {
                    "filename": "png_01.png",
                    "format": "png",
                    "offset": 64,
                    "size_bytes": 24,
                    "complete_boundary": True,
                    "format_valid": True,
                    "sha256": digest,
                }
            ]
            evaluation = EvaluationResult(
                summary={
                    "candidate_count": 1,
                    "expected_present_count": 1,
                    "recovered_exact_count": 1,
                    "expected_offset_count": 1,
                    "offset_match_count": 1,
                    "expected_absent_count": 0,
                    "false_positive_candidate_count": 0,
                    "candidate_precision": 1.0,
                    "recovery_recall": 1.0,
                    "offset_match_rate": 1.0,
                },
                details=(
                    {
                        "source_filename": "source.png",
                        "target_present": True,
                        "expected_offset": 64,
                        "recovered_filename": "png_01.png",
                        "recovered_offset": 64,
                        "status": "exact",
                    },
                ),
                candidate_status={"png_01.png": "exact"},
            )
            now = datetime.now(timezone.utc)
            report = build_experiment_report(
                source,
                rows,
                evaluation,
                now,
                now,
                (stat.st_size, stat.st_mtime_ns),
            )

            self.assertIn(hashlib.sha256(b"synthetic image").hexdigest(), report)
            self.assertIn("100.00%", report)
            self.assertIn("png_01.png", report)
            target = root / "report.md"
            write_new_report(target, report)
            with self.assertRaises(FileExistsError):
                write_new_report(target, report)


if __name__ == "__main__":
    unittest.main()
