"""
Consolidated FastJob CLI commands - refactored for extensibility
"""

import asyncio
import json
from ..colors import print_status, StatusIcon
from ..registry import register_simple_command


def register_core_commands():
    """Register all core CLI commands using the new registry system."""
    
    # Start command (worker functionality)
    register_simple_command(
        name="start",
        help="Start FastJob worker",
        description="Start FastJob worker to process background jobs",
        handler=handle_start_command,
        arguments=[
            {"args": ["--concurrency"], "kwargs": {"type": int, "default": 4, "help": "Number of concurrent workers (default: 4)"}},
            {"args": ["--queues"], "kwargs": {"default": "default", "help": "Comma-separated list of queues to process (default: default)"}},
            {"args": ["--run-once"], "kwargs": {"action": "store_true", "help": "Process jobs once and exit (useful for testing)"}}
        ],
        category="worker"
    )
    
    # Setup command (database management)
    register_simple_command(
        name="setup",
        help="Setup FastJob database",
        description="Initialize or update FastJob database schema",
        handler=handle_setup_command,
        category="database"
    )
    
    # Migration status command (database management)
    register_simple_command(
        name="migrate-status",
        help="Show database migration status",
        description="Display current database migration status and pending migrations",
        handler=handle_migrate_status_command,
        category="database"
    )
    
    # Status command (monitoring)
    register_simple_command(
        name="status",
        help="Show system status",
        description="Display system health, job statistics, and queue information",
        handler=handle_status_command,
        arguments=[
            {"args": ["--jobs"], "kwargs": {"action": "store_true", "help": "Show recent jobs"}},
            {"args": ["--verbose"], "kwargs": {"action": "store_true", "help": "Show detailed information"}}
        ],
        category="monitoring"
    )
    
    # CLI debug command (development)
    register_simple_command(
        name="cli-debug",
        help="Show CLI command registry information",
        description="Display information about registered CLI commands for debugging",
        handler=handle_cli_debug_command,
        arguments=[
            {"args": ["--plugins"], "kwargs": {"action": "store_true", "help": "Show plugin information"}}
        ],
        category="debug"
    )






async def handle_start_command(args):
    """Handle start command (worker functionality)"""
    from fastjob.core.processor import run_worker
    
    queues = [q.strip() for q in args.queues.split(",")]
    
    print_status(f"Starting FastJob worker with {args.concurrency} workers", "info")
    print_status(f"Processing queues: {', '.join(queues)}", "info")
    
    try:
        await run_worker(concurrency=args.concurrency, queues=queues, run_once=args.run_once)
    except KeyboardInterrupt:
        print_status("Worker stopped by user", "info")
        return 0
    except Exception as e:
        print_status(f"Worker error: {e}", "error")
        return 1
    
    return 0


async def handle_setup_command(args):
    """Handle setup command (migration functionality)"""
    from fastjob.db.migrations import run_migrations
    from fastjob.db.migration_runner import get_migration_status
    
    try:
        print_status("Setting up FastJob database...", "info")
        
        # Check current status first
        status = await get_migration_status()
        print(f"  Found {status['total_migrations']} total migrations")
        
        if status['pending_migrations']:
            print(f"  Applying {len(status['pending_migrations'])} pending migrations...")
            for migration in status['pending_migrations']:
                print(f"    - {migration}")
        else:
            print("  Database schema is already up to date")
        
        # Run migrations
        applied_count = await run_migrations()
        
        if applied_count > 0:
            print_status(f"Applied {applied_count} migrations successfully", "success")
        else:
            print_status("Database setup completed (no migrations needed)", "success")
            
        return 0
    except Exception as e:
        print_status(f"Setup failed: {e}", "error")
        return 1


async def handle_migrate_status_command(args):
    """Handle migrate status command"""
    from fastjob.db.migration_runner import get_migration_status
    
    try:
        print_status("FastJob Database Migration Status", "info")
        print("=" * 50)
        
        status = await get_migration_status()
        
        print(f"Total migrations: {status['total_migrations']}")
        print(f"Applied migrations: {len(status['applied_migrations'])}")
        print(f"Pending migrations: {len(status['pending_migrations'])}")
        print(f"Status: {'Up to date' if status['is_up_to_date'] else 'Migrations pending'}")
        
        if status['applied_migrations']:
            print("\nApplied migrations:")
            for migration in status['applied_migrations']:
                print(f"  ✅ {migration}")
        
        if status['pending_migrations']:
            print("\nPending migrations:")
            for migration in status['pending_migrations']:
                print(f"  ⏳ {migration}")
            print(f"\nRun 'fastjob setup' to apply pending migrations")
        
        return 0
    except Exception as e:
        print_status(f"Failed to get migration status: {e}", "error")
        return 1


async def handle_status_command(args):
    """Handle status command (health + jobs + queues functionality)"""
    from fastjob.db.connection import get_pool
    from fastjob import get_queue_stats, list_jobs
    from fastjob.core.discovery import discover_jobs
    from fastjob.core.registry import get_all_jobs
    
    print(f"\n{StatusIcon.rocket()} FastJob System Status")
    
    # 1. Health Check
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            if result == 1:
                print_status("Database connection: OK", "success")
            else:
                print_status("Database connection: FAILED", "error")
                return 1
                
    except Exception as e:
        print_status(f"Health check failed: {e}", "error")
        return 1

    # 2. Queue Statistics
    try:
        queues = await get_queue_stats()
        if queues:
            total_jobs = sum(q['total_jobs'] for q in queues)
            total_queued = sum(q['queued'] for q in queues)
            total_failed = sum(q['failed'] + q['dead_letter'] for q in queues)
            
            print(f"\nQueue Statistics:")
            print(f"  Total Jobs: {total_jobs}")
            print(f"  Queued: {total_queued}")
            print(f"  Failed/Dead Letter: {total_failed}")
            print(f"  Active Queues: {len(queues)}")
            
            if args.verbose:
                print(f"\nPer-Queue Breakdown:")
                print(f"{'Queue':<15} {'Total':<8} {'Queued':<8} {'Done':<8} {'Failed':<8}")
                print("-" * 60)
                for queue in queues:
                    print(f"{queue['queue']:<15} {queue['total_jobs']:<8} {queue['queued']:<8} {queue['done']:<8} {queue['failed']:<8}")
            
            if total_queued > 0:
                print_status(f"{total_queued} jobs waiting to be processed", "warning")
            elif total_failed > 0:
                print_status(f"{total_failed} jobs need attention", "warning")
            else:
                print_status("All jobs processed successfully", "success")
        else:
            print_status("No jobs found in any queue", "info")
            
    except Exception as e:
        print_status(f"Failed to get queue stats: {e}", "error")
        return 1

    # 3. Job Discovery (if verbose)
    if args.verbose:
        try:
            discover_jobs()
            jobs = get_all_jobs()
            
            if jobs:
                print(f"\nRegistered Jobs ({len(jobs)}):")
                for job_name in sorted(jobs.keys()):
                    print(f"  - {job_name}")
            else:
                print_status("No jobs discovered", "warning")
                
        except Exception as e:
            print_status(f"Job discovery failed: {e}", "error")

    # 4. Recent Jobs (if --jobs flag)
    if args.jobs:
        try:
            recent_jobs = await list_jobs(limit=10)
            if recent_jobs:
                print(f"\nRecent Jobs ({len(recent_jobs)}):")
                print(f"{'ID'[:8]:<8} {'Name':<25} {'Status':<12} {'Queue':<10}")
                print("-" * 60)
                for job in recent_jobs:
                    job_name = job['job_name'].split('.')[-1]  # Just function name
                    print(f"{job['id'][:8]:<8} {job_name:<25} {job['status']:<12} {job['queue']:<10}")
            else:
                print("  No recent jobs")
                
        except Exception as e:
            print_status(f"Failed to get recent jobs: {e}", "error")

    return 0


async def handle_cli_debug_command(args):
    """Handle CLI debug command - show command registry and plugin info."""
    from ..registry import get_cli_registry
    
    print(f"\n{StatusIcon.rocket()} FastJob CLI Debug Information")
    
    # Command registry status
    registry = get_cli_registry()
    status = registry.get_registry_status()
    
    print(f"\nCommand Registry:")
    print(f"  Total commands: {status['total_commands']}")
    
    if status['categories']:
        print(f"  Categories:")
        for category, count in status['categories'].items():
            print(f"    {category}: {count} command{'s' if count != 1 else ''}")
    
    print(f"\nRegistered Commands:")
    for category in registry.get_categories():
        commands = registry.get_commands_by_category(category)
        if commands:
            print(f"  {category.upper()}:")
            for cmd in commands:
                aliases_str = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
                print(f"    - {cmd.name}: {cmd.help}{aliases_str}")
    
    # Plugin information if requested
    if args.plugins:
        try:
            import fastjob
            plugin_status = fastjob.get_plugin_status()
            
            print(f"\nPlugin Status:")
            print(f"  Active plugins: {plugin_status['summary']['active_count']}")
            print(f"  Failed plugins: {plugin_status['summary']['failed_count']}")
            
            if plugin_status['active_plugins']:
                print(f"  Active:")
                for name, info in plugin_status['active_plugins'].items():
                    print(f"    - {info['name']} v{info['version']}")
                    
            if plugin_status['failed_plugins']:
                print(f"  Failed:")
                for failed in plugin_status['failed_plugins']:
                    print(f"    - {failed['name']}: {failed['error_type']}")
                    
        except Exception as e:
            print_status(f"Could not get plugin information: {e}", "warning")
    
    return 0