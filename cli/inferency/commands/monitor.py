"""Monitor command - real-time cost tracking stream."""

from __future__ import annotations

import json
import time

import click
from rich.console import Console
from rich.live import Live
from rich.table import Table

console = Console()


@click.command()
@click.option("--interval", default=5, help="Refresh interval in seconds")
def monitor(interval: int) -> None:
    """Monitor real-time AI API costs."""
    from ..client import InferencyClient, get_api_key

    api_key = get_api_key()
    if not api_key:
        console.print("[red]No API key configured. Run: inferency config --api-key YOUR_KEY[/red]")
        return

    client = InferencyClient()

    console.print("[bold]Inferency Cost Monitor[/bold]")
    console.print(f"[dim]Refreshing every {interval}s. Press Ctrl+C to stop.[/dim]\n")

    try:
        while True:
            try:
                health = client.health()
                recommendations = client.get_recommendations()

                table = Table(title="Current Recommendations")
                table.add_column("Type", style="cyan")
                table.add_column("Description", style="white")
                table.add_column("Savings", style="green", justify="right")
                table.add_column("Confidence", style="yellow", justify="right")

                for rec in recommendations[:10]:
                    savings = f"${rec.get('estimatedMonthlySavings', 0):.2f}/mo"
                    confidence = f"{rec.get('confidence', 0):.0%}"
                    table.add_row(
                        rec.get("type", "-"),
                        rec.get("description", "-")[:60],
                        savings,
                        confidence,
                    )

                console.clear()
                console.print(f"[green]Server: {health.get('status', 'unknown')}[/green] | Uptime: {health.get('uptime', 0)}s\n")
                console.print(table)
                console.print(f"\n[dim]Last updated: {time.strftime('%H:%M:%S')}[/dim]")

            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

            time.sleep(interval)

    except KeyboardInterrupt:
        console.print("\n[dim]Monitor stopped.[/dim]")
    finally:
        client.close()
