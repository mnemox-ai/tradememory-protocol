"""TradeMemory Protocol CLI."""

import click


@click.group()
def cli():
    """TradeMemory Protocol -- AI Trading Memory"""
    pass


@cli.command()
def setup():
    """Interactive first-time setup wizard."""
    from .onboarding.setup_wizard import run_setup
    run_setup()


@cli.command()
@click.option("--full", is_flag=True, help="Run full diagnostic including external services")
def doctor(full):
    """Check system health."""
    from .onboarding.doctor import run_doctor, print_results
    results = run_doctor(full=full)
    print_results(results)


@cli.command()
@click.argument("platform", required=False)
def config(platform):
    """Show configuration for your AI platform."""
    from .onboarding.platforms import show_config_menu
    show_config_menu(platform)


@cli.command()
@click.option("--fast", is_flag=True, help="Skip typewriter effect and pauses")
def demo(fast):
    """Run interactive demo with 30 simulated trades (no API key needed)."""
    from .demo import main as demo_main
    demo_main(fast=fast)


# Brake + memory in front of a broker MCP server: `tradememory proxy ...`
# (pip install "tradememory-protocol[proxy]", Python 3.12+). The group itself
# imports nothing heavy, so the base CLI keeps working without the extra.
from .proxy.cli import proxy as _proxy_group  # noqa: E402

cli.add_command(_proxy_group, name="proxy")

# Fill history from a venue into memory: `tradememory sync hyperliquid|alpaca`.
from .sync.cli import sync as _sync_group  # noqa: E402

cli.add_command(_sync_group, name="sync")


if __name__ == "__main__":
    cli()
