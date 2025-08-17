"""
FastJob CLI - Simplified main module with consolidated commands
"""

import argparse
import asyncio

from .colors import print_status

# Import extensible command system
from .commands.core import register_core_commands, resolve_fastjob_instance
from .registry import get_cli_registry


def load_plugin_commands():
    """Load CLI commands from installed fastjob plugins using the registry system."""
    try:
        # Explicitly load plugins firs
        import fastjob

        fastjob.load_plugins()

        from fastjob.plugins import get_plugin_manager

        plugin_manager = get_plugin_manager()

        # Plugins register commands in our registry using: fastjob.cli.registry.register_command()
        plugin_manager.call_hook("register_cli_commands")

    except Exception as e:
        # No plugins found or plugin system not available
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(f"Plugin command loading failed: {e}")


async def handle_plugin_command(args):
    """
    Handle plugin command execution with proper database context setup.

    This function:
    1. Resolves the FastJob instance (Global API vs Instance API)
    2. Sets up the appropriate database context
    3. Calls the plugin command handler
    4. Cleans up the context
    """
    from ..db.context import DatabaseContext, clear_current_context, set_current_context

    try:
        # Resolve FastJob instance based on CLI arguments
        fastjob_instance = await resolve_fastjob_instance(args)

        # Set up database context
        if fastjob_instance:
            # Instance-based API with --database-url
            context = DatabaseContext.from_instance(fastjob_instance)
            print_status(
                f"Using instance-based configuration: {fastjob_instance.settings.database_url}",
                "info",
            )
        else:
            # Global API (default)
            context = DatabaseContext.from_global_api()
            print_status("Using global API configuration", "info")

        # Set the context for Pro/Enterprise features to use
        set_current_context(context)

        # Call the plugin command handler
        return args.plugin_func(args)

    except Exception as e:
        print_status(f"Plugin command setup failed: {e}", "error")
        return 1
    finally:
        # Clean up context
        clear_current_context()


def main():
    """Main CLI entry point with organized command structure"""
    parser = argparse.ArgumentParser(
        description="FastJob CLI - Unified Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  fastjob start --concurrency 4 --queues default,urgen
  fastjob setup
  fastjob status --verbose --jobs

For more information, visit: https://docs.fastjob.dev
        """,
    )

    subparsers = parser.add_subparsers(dest="command", title="Available commands")

    # Register core commands in the registry
    register_core_commands()

    # Load plugin commands (Pro, Enterprise features)
    load_plugin_commands()

    # Add all registered commands to the parser
    registry = get_cli_registry()
    registry.add_to_parser(subparsers)

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Execute the command
    try:
        # Handle both core commands (func) and plugin commands (plugin_func)
        if hasattr(args, "func"):
            # Core command handler
            if asyncio.iscoroutinefunction(args.func):
                return asyncio.run(args.func(args))
            else:
                return args.func(args)
        elif hasattr(args, "plugin_func"):
            # Plugin command handler - set up database context first
            return asyncio.run(handle_plugin_command(args))
        else:
            print_status(f"Command '{args.command}' has no handler", "error")
            return 1

    except KeyboardInterrupt:
        print_status("Operation interrupted by user", "info")
        return 0
    except Exception as e:
        print_status(f"Command failed: {e}", "error")
        return 1


if __name__ == "__main__":
    exit(main())
