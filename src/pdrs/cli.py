"""Command line interface for the PDRS prototype."""

from __future__ import annotations

from pathlib import Path

import typer

from pdrs.carve import carve_image
from pdrs.manifest import write_manifest
from pdrs.structure import format_report, inspect_image, report_json

app = typer.Typer(no_args_is_help=True, help="Read-only recovery research tools")


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
