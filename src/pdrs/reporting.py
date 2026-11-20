"""Build reproducible Markdown reports for completed PDRS GUI scans."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from pdrs import __version__
from pdrs.evaluation import EvaluationResult


def sha256_file(path: Path) -> str:
    """Hash a regular file with bounded memory use and read-only access."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _md_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _percent(value: object) -> str:
    return "N/A" if value is None else f"{float(value) * 100:.2f}%"


def _time(value: datetime) -> str:
    return value.astimezone().isoformat(timespec="seconds")


def build_experiment_report(
    source: Path,
    rows: Sequence[Mapping[str, object]],
    evaluation: EvaluationResult | None,
    scan_started_at: datetime,
    scan_finished_at: datetime,
    scan_source_signature: tuple[int, int],
) -> str:
    """Build a Markdown report without changing the image or scan artifacts."""
    resolved_source = source.resolve(strict=True)
    stat_before = resolved_source.stat()
    image_hash = sha256_file(resolved_source)
    stat_after = resolved_source.stat()
    metadata_stable_during_hash = (
        stat_before.st_size == stat_after.st_size
        and stat_before.st_mtime_ns == stat_after.st_mtime_ns
    )
    metadata_matches_scan = (
        stat_before.st_size == scan_source_signature[0]
        and stat_before.st_mtime_ns == scan_source_signature[1]
        and metadata_stable_during_hash
    )

    candidate_count = len(rows)
    complete_count = sum(row.get("complete_boundary") is True for row in rows)
    valid_count = sum(row.get("format_valid") is True for row in rows)
    invalid_count = sum(row.get("format_valid") is False for row in rows)
    unchecked_count = candidate_count - valid_count - invalid_count
    duration = max(0.0, (scan_finished_at - scan_started_at).total_seconds())

    lines = [
        "# PDRS 数据恢复课程实验报告",
        "",
        "## 实验信息",
        "",
        f"- PDRS 版本：`{__version__}`",
        f"- 镜像文件：`{_md_cell(resolved_source)}`",
        f"- 镜像大小：{stat_after.st_size:,} bytes",
        f"- 镜像 SHA-256：`{image_hash}`",
        f"- 扫描开始：{_time(scan_started_at)}",
        f"- 扫描完成：{_time(scan_finished_at)}",
        f"- 扫描耗时：{duration:.3f} 秒",
        "- 镜像来源身份："
        + ("报告计算哈希时，文件大小和修改时间与扫描开始时一致。" if metadata_matches_scan else "报告计算哈希时的文件大小或修改时间与扫描开始时不一致；请确认镜像未在扫描后更换或修改。"),
        "",
        "## 扫描方法与范围",
        "",
        "程序以只读方式扫描用户提供的 raw 镜像，按 BMP、JPEG、PNG、PDF、SQLite 主数据库文件特征查找连续候选数据，并记录偏移、边界、格式校验和 SHA-256。SQLite 候选不超过 64 MiB 时运行 PRAGMA quick_check。",
        "本实验工具不访问物理磁盘，不恢复文件系统目录/删除记录或 SQLite 删除行，不重放 SQLite WAL，也不重组碎片文件。候选格式校验通过不等同于与原文件逐字节一致；精确性需与已知 SHA-256 对照。",
        "",
        "## 候选统计",
        "",
        "| 指标 | 数量 |",
        "| --- | ---: |",
        f"| 候选总数 | {candidate_count} |",
        f"| 完整边界 | {complete_count} |",
        f"| 格式校验有效 | {valid_count} |",
        f"| 格式校验未通过 | {invalid_count} |",
        f"| 未检查 | {unchecked_count} |",
        "",
        "## Ground Truth 对照",
        "",
    ]

    if evaluation is None:
        lines.append("本次扫描未加载 Ground Truth 数据集，未计算恢复率、候选精确率或偏移匹配率。")
    else:
        summary = evaluation.summary
        lines.extend(
            [
                "| 指标 | 结果 |",
                "| --- | ---: |",
                f"| 预期存在文件 | {summary['expected_present_count']} |",
                f"| SHA-256 匹配 | {summary['recovered_exact_count']} |",
                f"| 恢复率（SHA-256 匹配 / 预期存在） | {_percent(summary['recovery_recall'])} |",
                f"| 候选精确率（SHA-256 匹配 / 候选） | {_percent(summary['candidate_precision'])} |",
                f"| 偏移匹配 | {summary['offset_match_count']} / {summary['expected_offset_count']} |",
                f"| 偏移匹配率 | {_percent(summary['offset_match_rate'])} |",
                f"| 误报候选 | {summary['false_positive_candidate_count']} |",
                "",
                "### Ground Truth 样本明细",
                "",
                "| 原文件 | 预期存在 | 预期偏移 | 恢复候选 | 恢复偏移 | 状态 |",
                "| --- | :---: | ---: | --- | ---: | --- |",
            ]
        )
        for detail in evaluation.details:
            lines.append(
                "| "
                + " | ".join(
                    _md_cell(detail.get(key, ""))
                    for key in (
                        "source_filename",
                        "target_present",
                        "expected_offset",
                        "recovered_filename",
                        "recovered_offset",
                        "status",
                    )
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "## 候选明细",
            "",
            "| 文件名 | 格式 | 镜像偏移 | 大小（bytes） | 边界完整 | 格式校验 | SHA-256 |",
            "| --- | --- | ---: | ---: | :---: | --- | --- |",
        ]
    )
    for row in rows:
        valid_value = row.get("format_valid")
        valid_text = "有效" if valid_value is True else "未通过" if valid_value is False else "未检查"
        lines.append(
            "| "
            + " | ".join(
                (
                    _md_cell(row.get("filename", "")),
                    _md_cell(row.get("format", "")),
                    _md_cell(row.get("offset", "")),
                    _md_cell(row.get("size_bytes", "")),
                    "是" if row.get("complete_boundary") is True else "否",
                    valid_text,
                    f"`{_md_cell(row.get('sha256', ''))}`",
                )
            )
            + " |"
        )
    if not rows:
        lines.append("| （未发现候选） | — | — | — | — | — | — |")

    lines.extend(
        [
            "",
            "## 结果文件",
            "",
            "- `manifest.csv`：候选边界、格式状态和 SHA-256。",
        ]
    )
    if evaluation is not None:
        lines.extend(
            [
                "- `ground_truth_comparison.csv`：逐源文件匹配结果。",
                "- `evaluation_summary.csv`：汇总评价指标。",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def write_new_report(path: Path, content: str) -> Path:
    """Create a new report file without replacing an existing file."""
    target = path.expanduser().resolve()
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return target
