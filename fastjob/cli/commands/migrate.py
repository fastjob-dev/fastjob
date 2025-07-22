"""
Database migration command
"""

import asyncio
from ..colors import print_status, StatusIcon


def add_migrate_command(subparsers):
    """Add migrate command to CLI"""
    subparsers.add_parser(
        "migrate", 
        help="Run database migrations", 
        description="Initialize or update FastJob database schema"
    ).set_defaults(func=handle_migrate_command)


async def handle_migrate_command(args):
    """Handle migrate command"""
    from fastjob.db.migrations import run_migrations
    
    try:
        print_status("Running database migrations...", "info")
        await run_migrations()
        print_status("Database migrations completed successfully", "success")
        return 0
    except Exception as e:
        print_status(f"Migration failed: {e}", "error")
        return 1