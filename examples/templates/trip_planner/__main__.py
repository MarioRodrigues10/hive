"""
CLI entry point for City Trip Planner.

Uses AgentRuntime for multi-entrypoint support with HITL pause/resume.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

import click

from .agent import TripPlannerAgent, default_agent


def setup_logging(verbose: bool = False, debug: bool = False) -> None:
    """Configure logging for execution visibility."""
    if debug:
        level, fmt = logging.DEBUG, "%(asctime)s %(name)s: %(message)s"
    elif verbose:
        level, fmt = logging.INFO, "%(message)s"
    else:
        level, fmt = logging.WARNING, "%(levelname)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stderr)
    logging.getLogger("framework").setLevel(level)


@click.group()
@click.version_option(version="1.0.0")
def cli() -> None:
    """City Trip Planner - Plan food crawls, café hops, and sightseeing adventures."""
    pass


@cli.command()
@click.option(
    "--request",
    "-r",
    type=str,
    default="",
    help="Initial trip request (e.g. 'food crawl in Tokyo, 6 hours, walking')",
)
@click.option("--quiet", "-q", is_flag=True, help="Only output result JSON")
@click.option("--verbose", "-v", is_flag=True, help="Show execution details")
@click.option("--debug", is_flag=True, help="Show debug logging")
def run(request: str, quiet: bool, verbose: bool, debug: bool) -> None:
    """Plan a trip (non-interactive single-shot execution)."""
    if not quiet:
        setup_logging(verbose=verbose, debug=debug)

    context = {"user_request": request} if request else {}

    result = asyncio.run(default_agent.run(context))

    output_data: dict = {
        "success": result.success,
        "steps_executed": result.steps_executed,
        "output": result.output,
    }
    if result.error:
        output_data["error"] = result.error

    click.echo(json.dumps(output_data, indent=2, default=str))
    sys.exit(0 if result.success else 1)


@cli.command()
@click.option("--verbose", "-v", is_flag=True, help="Show execution details")
@click.option("--debug", is_flag=True, help="Show debug logging")
def tui(verbose: bool, debug: bool) -> None:
    """Launch the TUI dashboard for interactive trip planning."""
    setup_logging(verbose=verbose, debug=debug)

    try:
        from framework.tui.app import AdenTUI
    except ImportError:
        click.echo(
            "TUI requires the 'textual' package. Install with: pip install textual"
        )
        sys.exit(1)

    from pathlib import Path

    from framework.llm import LiteLLMProvider
    from framework.runner.tool_registry import ToolRegistry
    from framework.runtime.agent_runtime import create_agent_runtime
    from framework.runtime.event_bus import EventBus
    from framework.runtime.execution_stream import EntryPointSpec

    async def run_with_tui() -> None:
        agent = TripPlannerAgent()

        agent._event_bus = EventBus()
        agent._tool_registry = ToolRegistry()

        storage_path = Path.home() / ".hive" / "agents" / "trip_planner"
        storage_path.mkdir(parents=True, exist_ok=True)

        mcp_config_path = Path(__file__).parent / "mcp_servers.json"
        if mcp_config_path.exists():
            agent._tool_registry.load_mcp_config(mcp_config_path)

        llm = LiteLLMProvider(
            model=agent.config.model,
            api_key=agent.config.api_key,
            api_base=agent.config.api_base,
        )

        tools = list(agent._tool_registry.get_tools().values())
        tool_executor = agent._tool_registry.get_executor()
        graph = agent._build_graph()

        runtime = create_agent_runtime(
            graph=graph,
            goal=agent.goal,
            storage_path=storage_path,
            entry_points=[
                EntryPointSpec(
                    id="start",
                    name="Plan a Trip",
                    entry_node="intake",
                    trigger_type="manual",
                    isolation_level="isolated",
                ),
            ],
            llm=llm,
            tools=tools,
            tool_executor=tool_executor,
        )

        await runtime.start()

        try:
            app = AdenTUI(runtime)
            await app.run_async()
        finally:
            await runtime.stop()

    asyncio.run(run_with_tui())


@cli.command()
@click.option("--verbose", "-v", is_flag=True, help="Show execution details")
def shell(verbose: bool) -> None:
    """Interactive trip planning session (CLI, no TUI)."""
    asyncio.run(_interactive_shell(verbose))


async def _interactive_shell(verbose: bool = False) -> None:
    """Async interactive shell for continuous trip planning."""
    setup_logging(verbose=verbose)

    click.echo("=== City Trip Planner ===")
    click.echo(
        "Describe your trip (e.g. 'coffee hop in Lisbon, half day, walking') or 'quit' to exit:\n"
    )

    agent = TripPlannerAgent()
    await agent.start()

    try:
        while True:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, input, "Trip> "
                )

                if user_input.strip().lower() in {"quit", "exit", "q"}:
                    click.echo("Bon voyage! 🗺️")
                    break

                if not user_input.strip():
                    continue

                click.echo("\nPlanning your adventure...\n")

                result = await agent.trigger_and_wait(
                    "default", {"user_request": user_input}
                )

                if result is None:
                    click.echo("\n[Execution timed out]\n")
                    continue

                if result.success:
                    output = result.output
                    report_file = output.get("report_file")
                    if report_file:
                        click.echo(f"\nItinerary saved: {report_file}\n")
                    else:
                        click.echo("\nTrip planning complete.\n")
                else:
                    click.echo(f"\nPlanning failed: {result.error}\n")

            except KeyboardInterrupt:
                click.echo("\nBon voyage! 🗺️")
                break
            except Exception as e:
                click.echo(f"Error: {e}", err=True)
                import traceback

                traceback.print_exc()
    finally:
        await agent.stop()


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def info(output_json: bool) -> None:
    """Show agent information."""
    info_data = default_agent.info()
    if output_json:
        click.echo(json.dumps(info_data, indent=2))
    else:
        click.echo(f"Agent:       {info_data['name']}")
        click.echo(f"Version:     {info_data['version']}")
        click.echo(f"Description: {info_data['description']}")
        click.echo(f"\nNodes:          {', '.join(info_data['nodes'])}")
        click.echo(f"Client-facing:  {', '.join(info_data['client_facing_nodes'])}")
        click.echo(f"Entry:          {info_data['entry_node']}")
        click.echo(
            f"Terminal:       {', '.join(info_data['terminal_nodes']) or '(none — continuous)'}"
        )


@cli.command()
def validate() -> None:
    """Validate agent structure."""
    validation = default_agent.validate()
    if validation["valid"]:
        click.echo("✓ Agent is valid")
        for warning in validation["warnings"]:
            click.echo(f"  WARNING: {warning}")
    else:
        click.echo("✗ Agent has errors:")
        for error in validation["errors"]:
            click.echo(f"  ERROR: {error}")
    sys.exit(0 if validation["valid"] else 1)


if __name__ == "__main__":
    cli()
