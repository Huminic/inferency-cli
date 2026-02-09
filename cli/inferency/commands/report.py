"""Report command - generate optimization reports."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..parsers import detect_ai_calls
from .scan import collect_files

console = Console()

OPTIMIZATION_MAP = {
    "gpt-4": [("gpt-4o", "~92% cheaper"), ("gpt-4o-mini", "~99% cheaper")],
    "gpt-4-turbo": [("gpt-4o", "~75% cheaper"), ("gpt-4o-mini", "~98% cheaper")],
    "claude-3-opus": [("claude-3-5-sonnet", "~80% cheaper"), ("claude-3-haiku", "~98% cheaper")],
    "claude-3-sonnet": [("claude-3-haiku", "~92% cheaper")],
    "gemini-1.5-pro": [("gemini-1.5-flash", "~97% cheaper")],
}


@click.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["text", "json", "markdown"]), default="text")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def report(path: str, fmt: str, output: str | None) -> None:
    """Generate an AI cost optimization report."""
    target = Path(path)

    if target.is_file():
        files = [target]
    else:
        files = collect_files(str(target))

    if not files:
        console.print("[yellow]No source files found.[/yellow]")
        return

    all_detections = []
    for f in files:
        detections = detect_ai_calls(str(f))
        all_detections.extend(detections)

    if fmt == "json":
        _output_json(all_detections, output)
    elif fmt == "markdown":
        _output_markdown(all_detections, path, output)
    else:
        _output_text(all_detections, path)


def _output_text(detections, base_path: str) -> None:
    """Rich text output."""
    if not detections:
        console.print(Panel("[green]No AI API calls found in this codebase.[/green]", title="Inferency Report"))
        return

    console.print(Panel(f"[bold]Inferency Optimization Report[/bold]\n{len(detections)} AI API calls found", title="Report"))

    # By provider
    by_provider = {}
    for d in detections:
        by_provider.setdefault(d.provider, []).append(d)

    for provider, dets in sorted(by_provider.items()):
        console.print(f"\n[bold cyan]{provider.upper()}[/bold cyan] ({len(dets)} calls)")

        table = Table()
        table.add_column("File:Line", style="dim")
        table.add_column("Model")
        table.add_column("Cost/1K")
        table.add_column("Recommendation")

        for d in dets:
            import os
            rel = os.path.relpath(d.file_path, base_path)
            cost = f"${d.estimated_cost_per_1k_calls:.2f}" if d.estimated_cost_per_1k_calls > 0 else "-"
            rec = ""
            base_model = d.model.split("-20")[0] if d.model else ""
            if base_model in OPTIMIZATION_MAP:
                suggestions = OPTIMIZATION_MAP[base_model]
                rec = f"Switch to {suggestions[0][0]} ({suggestions[0][1]})"
            table.add_row(f"{rel}:{d.line_number}", d.model or "-", cost, rec)

        console.print(table)

    total_cost = sum(d.estimated_cost_per_1k_calls for d in detections)
    optimizable = sum(
        1 for d in detections if d.model and d.model.split("-20")[0] in OPTIMIZATION_MAP
    )
    console.print(f"\n[bold]Total estimated cost per 1K calls:[/bold] [red]${total_cost:.2f}[/red]")
    console.print(f"[bold]Optimizable calls:[/bold] {optimizable}/{len(detections)}")


def _output_json(detections, output: str | None) -> None:
    """JSON output."""
    data = {
        "total_calls": len(detections),
        "total_cost_per_1k": sum(d.estimated_cost_per_1k_calls for d in detections),
        "detections": [
            {
                "file": d.file_path,
                "line": d.line_number,
                "provider": d.provider,
                "model": d.model,
                "cost_per_1k": d.estimated_cost_per_1k_calls,
                "confidence": d.confidence,
            }
            for d in detections
        ],
    }
    text = json.dumps(data, indent=2)
    if output:
        Path(output).write_text(text)
        console.print(f"[green]Report saved to {output}[/green]")
    else:
        click.echo(text)


def _output_markdown(detections, base_path: str, output: str | None) -> None:
    """Markdown output."""
    import os
    lines = ["# Inferency Optimization Report\n"]
    lines.append(f"**Total AI API calls found:** {len(detections)}\n")

    total_cost = sum(d.estimated_cost_per_1k_calls for d in detections)
    lines.append(f"**Estimated cost per 1K calls:** ${total_cost:.2f}\n")

    lines.append("\n## Findings\n")
    lines.append("| File | Line | Provider | Model | Cost/1K | Recommendation |")
    lines.append("|------|------|----------|-------|---------|----------------|")

    for d in detections:
        rel = os.path.relpath(d.file_path, base_path)
        cost = f"${d.estimated_cost_per_1k_calls:.2f}" if d.estimated_cost_per_1k_calls > 0 else "-"
        rec = ""
        base_model = d.model.split("-20")[0] if d.model else ""
        if base_model in OPTIMIZATION_MAP:
            suggestions = OPTIMIZATION_MAP[base_model]
            rec = f"Switch to {suggestions[0][0]} ({suggestions[0][1]})"
        lines.append(f"| {rel} | {d.line_number} | {d.provider} | {d.model or '-'} | {cost} | {rec} |")

    text = "\n".join(lines) + "\n"
    if output:
        Path(output).write_text(text)
        console.print(f"[green]Report saved to {output}[/green]")
    else:
        click.echo(text)
