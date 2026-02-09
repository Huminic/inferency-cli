"""Scan command - analyze codebases for AI API usage."""

from __future__ import annotations

import os
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ..parsers import detect_ai_calls

console = Console()

IGNORED_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "vendor",
    ".tox",
    "coverage",
}

SCAN_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs"}


def collect_files(directory: str, max_files: int = 1000) -> list[Path]:
    """Collect source files from directory, respecting ignore rules."""
    files = []
    root = Path(directory)
    for dirpath, dirnames, filenames in os.walk(root):
        # Filter ignored directories in-place
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]

        for fname in filenames:
            if Path(fname).suffix.lower() in SCAN_EXTENSIONS:
                files.append(Path(dirpath) / fname)
                if len(files) >= max_files:
                    return files
    return files


@click.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--remote", is_flag=True, help="Submit to Inferency server for analysis")
def scan(path: str, json_output: bool, remote: bool) -> None:
    """Scan a directory or file for AI API calls."""
    target = Path(path)

    if target.is_file():
        files = [target]
    else:
        console.print(f"[bold]Scanning:[/bold] {target.resolve()}")
        files = collect_files(str(target))
        console.print(f"[dim]Found {len(files)} source files[/dim]")

    if not files:
        console.print("[yellow]No source files found.[/yellow]")
        return

    all_detections = []
    for f in files:
        detections = detect_ai_calls(str(f))
        all_detections.extend(detections)

    if remote:
        _submit_remote(files, all_detections)
        return

    if json_output:
        import json

        output = [
            {
                "file": d.file_path,
                "line": d.line_number,
                "provider": d.provider,
                "model": d.model,
                "cost_per_1k": d.estimated_cost_per_1k_calls,
                "confidence": d.confidence,
            }
            for d in all_detections
        ]
        click.echo(json.dumps(output, indent=2))
        return

    if not all_detections:
        console.print("[green]No AI API calls detected.[/green]")
        return

    # Summary table
    table = Table(title=f"AI API Calls Found: {len(all_detections)}")
    table.add_column("File", style="cyan", no_wrap=True)
    table.add_column("Line", style="magenta", justify="right")
    table.add_column("Provider", style="green")
    table.add_column("Model", style="yellow")
    table.add_column("Cost/1K calls", style="red", justify="right")

    for d in all_detections:
        rel_path = os.path.relpath(d.file_path, path)
        cost = f"${d.estimated_cost_per_1k_calls:.2f}" if d.estimated_cost_per_1k_calls > 0 else "-"
        table.add_row(rel_path, str(d.line_number), d.provider, d.model or "-", cost)

    console.print(table)

    # Provider summary
    providers = {}
    for d in all_detections:
        providers[d.provider] = providers.get(d.provider, 0) + 1

    console.print("\n[bold]Summary:[/bold]")
    for provider, count in sorted(providers.items()):
        console.print(f"  {provider}: {count} call(s)")

    total_cost = sum(d.estimated_cost_per_1k_calls for d in all_detections)
    if total_cost > 0:
        console.print(f"\n[bold red]Estimated total cost per 1K calls: ${total_cost:.2f}[/bold red]")


def _submit_remote(files: list[Path], detections: list) -> None:
    """Submit scan to Inferency server."""
    from ..client import InferencyClient

    try:
        client = InferencyClient()
        file_data = []
        for f in files:
            try:
                content = f.read_text(errors="replace")
                file_data.append({"path": str(f), "content": content})
            except Exception:
                continue

        console.print(f"[dim]Submitting {len(file_data)} files to Inferency server...[/dim]")
        result = client.scan(file_data)
        console.print(f"[green]Scan submitted. ID: {result.get('id', 'unknown')}[/green]")
        issues = result.get("issues", [])
        console.print(f"[bold]{len(issues)} finding(s)[/bold]")
        client.close()
    except Exception as e:
        console.print(f"[red]Remote scan failed: {e}[/red]")
