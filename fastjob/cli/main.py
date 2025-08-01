"""
FastJob CLI - Simplified main module with consolidated commands
"""

import argparse
import asyncio

from .colors import print_status

# Import extensible command system
from .commands.core import register_core_commands
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
        if hasattr(args, "func"):
            # Command has an async handler
            if asyncio.iscoroutinefunction(args.func):
                return asyncio.run(args.func(args))
            else:
                return args.func(args)
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
