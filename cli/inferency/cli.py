"""Main CLI entry point."""

from __future__ import annotations

import click
from rich.console import Console

from . import __version__
from .commands.scan import scan
from .commands.monitor import monitor
from .commands.report import report

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="inferency")
def main() -> None:
    """Inferency - AI Cost Optimization CLI

    Scan codebases for AI API usage, track costs, and get optimization recommendations.
    """
    pass


@main.command()
@click.option("--api-key", prompt=True, hide_input=True, help="Your Inferency API key")
@click.option("--server-url", default=None, help="Inferency server URL")
def config(api_key: str, server_url: str | None) -> None:
    """Configure Inferency CLI credentials."""
    from .client import save_config

    if not api_key.startswith("inf_live_"):
        console.print('[red]API key must start with "inf_live_"[/red]')
        return

    save_config(api_key, server_url)
    console.print("[green]Configuration saved to ~/.inferency/config[/green]")


@main.command()
def status() -> None:
    """Check connection to Inferency server."""
    from .client import InferencyClient, get_api_key, get_server_url

    api_key = get_api_key()
    server_url = get_server_url()

    console.print(f"[bold]Server:[/bold] {server_url}")
    console.print(f"[bold]API Key:[/bold] {'configured' if api_key else '[red]not set[/red]'}")

    if api_key:
        try:
            client = InferencyClient()
            health = client.health()
            console.print(f"[bold]Status:[/bold] [green]{health.get('status', 'unknown')}[/green]")
            console.print(f"[bold]Version:[/bold] {health.get('version', 'unknown')}")
            console.print(f"[bold]Uptime:[/bold] {health.get('uptime', 0)}s")
            console.print(f"[bold]Database:[/bold] {health.get('database', 'unknown')}")
            client.close()
        except Exception as e:
            console.print(f"[bold]Status:[/bold] [red]unreachable ({e})[/red]")


@main.command()
def pricing() -> None:
    """Show current AI model pricing."""
    from .client import InferencyClient, get_api_key

    api_key = get_api_key()
    if not api_key:
        # Show local pricing data
        from .parsers.detector import MODEL_COSTS
        from rich.table import Table

        table = Table(title="AI Model Pricing (per 1M tokens)")
        table.add_column("Model", style="cyan")
        table.add_column("Input", style="green", justify="right")
        table.add_column("Output", style="yellow", justify="right")

        for model, costs in sorted(MODEL_COSTS.items()):
            table.add_row(model, f"${costs['input']:.2f}", f"${costs['output']:.2f}")

        console.print(table)
        return

    try:
        client = InferencyClient()
        models = client.get_pricing()

        from rich.table import Table

        table = Table(title="AI Model Pricing (per 1M tokens)")
        table.add_column("Model", style="cyan")
        table.add_column("Provider", style="dim")
        table.add_column("Input", style="green", justify="right")
        table.add_column("Output", style="yellow", justify="right")

        for m in models:
            input_price = m.get("inputPrice", 0)
            output_price = m.get("outputPrice", 0)
            table.add_row(
                m.get("model", "-"),
                m.get("provider", "-"),
                f"${input_price:.2f}",
                f"${output_price:.2f}",
            )

        console.print(table)
        client.close()
    except Exception as e:
        console.print(f"[red]Failed to fetch pricing: {e}[/red]")


# Register subcommands
main.add_command(scan)
main.add_command(monitor)
main.add_command(report)


if __name__ == "__main__":
    main()
