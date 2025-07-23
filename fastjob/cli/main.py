"""
FastJob CLI - Simplified main module with consolidated commands
"""

import argparse
import asyncio
from .colors import print_status, StatusIcon

# Import consolidated core commands
from .commands.core import add_core_commands


def load_plugin_commands(subparsers):
    """Load CLI commands from installed fastjob plugins using proper plugin architecture"""
    try:
        from fastjob.plugins import get_plugin_manager
        plugin_manager = get_plugin_manager()
        
        # Call plugin hook to let plugins register their own subparsers
        plugin_manager.call_hook('register_cli_commands', subparsers)
                        
    except Exception as e:
        # No plugins found or plugin system not available
        pass


def main():
    """Main CLI entry point with organized command structure"""
    parser = argparse.ArgumentParser(
        description="FastJob CLI - Unified Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  fastjob start --concurrency 4 --queues default,urgent
  fastjob setup
  fastjob status --verbose --jobs

For more information, visit: https://docs.fastjob.dev
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", title="Available commands")

    # Add core commands
    add_core_commands(subparsers)

    # Load plugin commands (Pro, Enterprise features)
    load_plugin_commands(subparsers)

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Execute the command
    try:
        if hasattr(args, 'func'):
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