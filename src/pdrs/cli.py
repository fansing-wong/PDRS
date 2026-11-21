"""Command line interface for the PDRS prototype."""

from __future__ import annotations

from pathlib import Path

import typer

from pdrs.carve import carve_image
from pdrs.evaluation import evaluate_ground_truth, load_ground_truth, write_evaluation
from pdrs.fat32_recovery import recover_deleted_fat32
from pdrs.manifest import write_manifest
from pdrs.structure import format_report, inspect_image, report_json

app = typer.Typer(no_args_is_help=True, help="Read-only recovery research tools (FAT32 deletion recovery is experimental)")


@app.command("inspect")
def inspect(
    image: Path = typer.Argument(..., exists=True, readable=True, help="Raw image file to inspect"),
    as_json: bool = typer.Option(False, "--json", help="Print the report as JSON"),
) -> None:
    """Inspect MBR/GPT, ext superblocks, and volume boot-sector metadata in an image file."""
    try:
        report = inspect_image(image)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(report_json(report) if as_json else format_report(report))


@app.command("recover-fat32-deleted")
def recover_fat32_deleted(
    image: Path = typer.Argument(..., exists=True, readable=True, help="Raw image file containing a FAT32 volume"),
    output: Path = typer.Argument(..., help="Empty directory for recovered files and manifest"),
    ground_truth: Path | None = typer.Option(
        None, "--ground-truth", exists=True, readable=True, help="Optional Ground Truth CSV for hash/offset comparison"
    ),
    reassemble_fragmented: bool = typer.Option(
        False,
        "--reassemble-fragmented",
        help="Opt in to reassembling complete surviving FAT chains after active-file overlap checks.",
    ),
    scan_deleted_directories: bool = typer.Option(
        False,
        "--scan-deleted-directories",
        help="Opt in to scanning direct deleted-file entries inside complete, non-overlapping deleted directories.",
    ),
) -> None:
    """Experimental: recover FAT32 deleted entries; risky modes are opt-in."""
    try:
        result = recover_deleted_fat32(
            image,
            output,
            reassemble_fragmented=reassemble_fragmented,
            scan_deleted_directories=scan_deleted_directories,
        )
        manifest = write_manifest(output, result.rows)
        evaluation = None
        if ground_truth is not None:
            evaluation = evaluate_ground_truth(
                load_ground_truth(ground_truth, image.name), result.rows
            )
            comparison_path, summary_path = write_evaluation(output, evaluation)
        if result.warnings:
            warning_path = output / "recovery_warnings.txt"
            with warning_path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(result.warnings) + "\n")
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"Deleted short-file entries examined: {result.deleted_entries_seen}")
    typer.echo(
        f"Directories scanned: {result.directories_scanned} "
        f"({result.directory_bytes_scanned:,} bytes)"
    )
    typer.echo(f"Recovered candidates: {len(result.rows)}")
    typer.echo(f"Manifest: {manifest}")
    if evaluation is not None:
        typer.echo(
            f"Ground Truth exact: {evaluation.summary['recovered_exact_count']}/"
            f"{evaluation.summary['expected_present_count']}"
        )
        typer.echo(f"Comparison: {comparison_path}")
        typer.echo(f"Summary: {summary_path}")
    for warning in result.warnings:
        typer.echo(f"Warning: {warning}", err=True)


@app.command()
def carve(
    image: Path = typer.Argument(..., exists=True, readable=True, help="Raw image file to scan"),
    output: Path = typer.Argument(..., help="Separate directory for recovered candidates"),
) -> None:
    """Carve contiguous BMP, JPEG, PNG, PDF, and SQLite database candidates from a raw image file."""
    try:
        rows = carve_image(image, output)
        manifest = write_manifest(output, rows)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"Candidates: {len(rows)}")
    typer.echo(f"Manifest: {manifest}")


if __name__ == "__main__":
    app()
