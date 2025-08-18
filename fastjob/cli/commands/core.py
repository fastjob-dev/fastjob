"""
Consolidated FastJob CLI commands - refactored for extensibility
"""

import logging

from ..colors import StatusIcon, print_status
from ..registry import register_simple_command

logger = logging.getLogger(__name__)


async def resolve_fastjob_instance(args):
    """
    Resolve FastJob instance configuration from CLI arguments.

    If --database-url is provided, returns a FastJob instance.
    Otherwise, returns None to use the global API.

    Returns:
        FastJob instance or None (to use global API)
    """
    from pydantic import ValidationError

    from fastjob import FastJob

    # Use instance-based API if database URL is provided
    if hasattr(args, "database_url") and args.database_url:
        try:
            return FastJob(database_url=args.database_url)
        except ValidationError as e:
            # Make database URL errors friendlier
            if "database_url" in str(e):
                if "postgresql" in str(e).lower():
                    raise ValueError(
                        f"Invalid database URL: {args.database_url}\nFastJob requires PostgreSQL URLs like: postgresql://user:password@localhost/database"
                    )
                else:
                    raise ValueError(f"Invalid database URL: {args.database_url}")
            raise ValueError(f"Configuration error: {e}")
        except Exception as e:
            # Handle other connection/config errors
            if "connect" in str(e).lower() or "connection" in str(e).lower():
                raise ValueError(
                    f"Can't connect to database: {args.database_url}\nMake sure PostgreSQL is running and the URL is correct"
                )
            raise ValueError(f"Database configuration error: {e}")

    # Otherwise use global API
    return None


def register_core_commands():
    """Register all core CLI commands using the registry system."""

    # Common instance argument for commands that support instance-based usage
    instance_arguments = [
        {
            "args": ["--database-url"],
            "kwargs": {
                "help": "Database URL (overrides FASTJOB_DATABASE_URL environment variable)",
                "metavar": "URL",
            },
        },
    ]

    # Start command (worker functionality)
    register_simple_command(
        name="start",
        help="Start FastJob worker",
        description="Start FastJob worker to process background jobs",
        handler=handle_start_command,
        arguments=[
            {
                "args": ["--concurrency"],
                "kwargs": {
                    "type": int,
                    "default": 4,
                    "help": "Number of concurrent workers (default: 4)",
                },
            },
            {
                "args": ["--queues"],
                "kwargs": {
                    "default": None,
                    "help": "Comma-separated list of queues to process (default: all queues)",
                },
            },
            {
                "args": ["--run-once"],
                "kwargs": {
                    "action": "store_true",
                    "help": "Process jobs once and exit (useful for testing)",
                },
            },
        ]
        + instance_arguments,
        category="worker",
    )

    # Setup command (database management)
    register_simple_command(
        name="setup",
        help="Setup FastJob database",
        description="Initialize or update FastJob database schema",
        handler=handle_setup_command,
        arguments=instance_arguments,
        category="database",
    )

    # Migration status command (database management)
    register_simple_command(
        name="migrate-status",
        help="Show database migration status",
        description="Display current database migration status and pending migrations",
        handler=handle_migrate_status_command,
        arguments=instance_arguments,
        category="database",
    )

    # Status command (monitoring)
    register_simple_command(
        name="status",
        help="Show system status",
        description="Display system health, job statistics, and queue information",
        handler=handle_status_command,
        arguments=[
            {
                "args": ["--jobs"],
                "kwargs": {"action": "store_true", "help": "Show recent jobs"},
            },
            {
                "args": ["--verbose"],
                "kwargs": {"action": "store_true", "help": "Show detailed information"},
            },
        ]
        + instance_arguments,
        category="monitoring",
    )

    # Worker status command (monitoring)
    register_simple_command(
        name="workers",
        help="Show worker status",
        description="Display active workers, heartbeats, and monitoring information",
        handler=handle_workers_command,
        arguments=[
            {
                "args": ["--stale"],
                "kwargs": {"action": "store_true", "help": "Show stale/dead workers"},
            },
            {
                "args": ["--cleanup"],
                "kwargs": {
                    "action": "store_true",
                    "help": "Clean up stale worker records",
                },
            },
        ]
        + instance_arguments,
        category="monitoring",
    )

    # CLI debug command (development)
    register_simple_command(
        name="cli-debug",
        help="Show CLI command registry information",
        description="Display information about registered CLI commands for debugging",
        handler=handle_cli_debug_command,
        arguments=[
            {
                "args": ["--plugins"],
                "kwargs": {"action": "store_true", "help": "Show plugin information"},
            }
        ],
        category="debug",
    )


async def handle_start_command(args):
    """Handle start command (worker functionality)"""

    # Resolve FastJob instance from CLI arguments
    try:
        fastjob_instance = await resolve_fastjob_instance(args)
    except Exception as e:
        print_status(f"Configuration error: {e}", "error")
        return 1

    # Handle queue specification
    if args.queues is None:
        queues = None  # Let run_worker discover all queues
        queue_msg = "all available queues"
    else:
        queues = [q.strip() for q in args.queues.split(",")]
        queue_msg = ", ".join(queues)

    print_status(f"Starting FastJob worker with {args.concurrency} workers", "info")
    print_status(f"Processing queues: {queue_msg}", "info")

    if fastjob_instance:
        print_status(
            f"Using instance-based configuration (database: {fastjob_instance.settings.database_url})",
            "info",
        )
    else:
        print_status("Using global API configuration", "info")

    try:
        if fastjob_instance:
            # Use instance-based API
            await fastjob_instance.run_worker(
                concurrency=args.concurrency, queues=queues, run_once=args.run_once
            )
        else:
            # Use global API (which delegates to a FastJob instance internally)
            import fastjob

            await fastjob.run_worker(
                concurrency=args.concurrency, queues=queues, run_once=args.run_once
            )
    except KeyboardInterrupt:
        print_status("Worker stopped by user", "info")
        return 0
    except Exception as e:
        print_status(f"Worker error: {e}", "error")
        return 1
    finally:
        # Clean up instance if used
        if fastjob_instance and fastjob_instance.is_initialized:
            await fastjob_instance.close()

    return 0


async def handle_setup_command(args):
    """Handle setup command (migration functionality)"""

    # Resolve FastJob instance from CLI arguments
    try:
        fastjob_instance = await resolve_fastjob_instance(args)
    except Exception as e:
        print_status(f"Configuration error: {e}", "error")
        return 1

    try:
        print_status("Setting up FastJob database...", "info")

        if fastjob_instance:
            print_status(
                f"Using instance-based configuration (database: {fastjob_instance.settings.database_url})",
                "info",
            )
            # Use instance-based migrations
            status = await fastjob_instance.get_migration_status()
            applied_count = await fastjob_instance.run_migrations()
        else:
            print_status("Using global API configuration", "info")
            # Use global API migrations
            from fastjob.db.migration_runner import get_migration_status
            from fastjob.db.migrations import run_migrations

            status = await get_migration_status()
            applied_count = await run_migrations()

        print(f"  Found {status['total_migrations']} total migrations")

        if status["pending_migrations"]:
            print(
                f"  Applying {len(status['pending_migrations'])} pending migrations..."
            )
            for migration in status["pending_migrations"]:
                print(f"    - {migration}")
        else:
            print("  Database schema is already up to date")

        if applied_count > 0:
            print_status(f"Applied {applied_count} migrations successfully", "success")
        else:
            print_status("Database setup completed (no migrations needed)", "success")

        return 0
    except Exception as e:
        # Make setup errors friendlier
        error_msg = str(e).lower()
        if "connection" in error_msg or "connect" in error_msg:
            print_status("Can't connect to database", "error")
            print("Make sure PostgreSQL is running and your database URL is correct")
        elif "database" in error_msg and "does not exist" in error_msg:
            print_status("Database doesn't exist", "error")
            print("Run: createdb your_database_name")
        elif "permission" in error_msg or "authentication" in error_msg:
            print_status("Database permission error", "error")
            print("Check your database username/password in the connection URL")
        else:
            print_status(f"Setup failed: {e}", "error")
        return 1
    finally:
        # Clean up instance if used
        if fastjob_instance and fastjob_instance.is_initialized:
            await fastjob_instance.close()


async def handle_migrate_status_command(args):
    """Handle migrate status command"""
    from fastjob.db.context import (
        DatabaseContext,
        clear_current_context,
        set_current_context,
    )
    from fastjob.db.migration_runner import get_migration_status

    # Resolve FastJob instance from CLI arguments
    try:
        fastjob_instance = await resolve_fastjob_instance(args)
    except Exception as e:
        print_status(f"Configuration error: {e}", "error")
        return 1

    # Set up database context
    if fastjob_instance:
        context = DatabaseContext.from_instance(fastjob_instance)
        print_status(
            f"Using instance-based configuration: {fastjob_instance.settings.database_url}",
            "info",
        )
    else:
        context = DatabaseContext.from_global_api()
        print_status("Using global API configuration", "info")

    set_current_context(context)

    try:
        print_status("FastJob Database Migration Status", "info")
        print("=" * 50)

        status = await get_migration_status()

        print(f"Total migrations: {status['total_migrations']}")
        print(f"Applied migrations: {len(status['applied_migrations'])}")
        print(f"Pending migrations: {len(status['pending_migrations'])}")
        print(
            f"Status: {'Up to date' if status['is_up_to_date'] else 'Migrations pending'}"
        )

        if status["applied_migrations"]:
            print("\nApplied migrations:")
            for migration in status["applied_migrations"]:
                print(f"  ✅ {migration}")

        if status["pending_migrations"]:
            print("\nPending migrations:")
            for migration in status["pending_migrations"]:
                print(f"  ⏳ {migration}")
            print("\nRun 'fastjob setup' to apply pending migrations")

        return 0
    except Exception as e:
        print_status(f"Failed to get migration status: {e}", "error")
        return 1
    finally:
        clear_current_context()


async def handle_status_command(args):
    """Handle status command (health + jobs + queues functionality)"""
    from fastjob.db.context import (
        DatabaseContext,
        clear_current_context,
        set_current_context,
    )

    # Resolve FastJob instance from CLI arguments
    try:
        fastjob_instance = await resolve_fastjob_instance(args)
    except Exception as e:
        print_status(f"Configuration error: {e}", "error")
        return 1

    # Set up database context
    if fastjob_instance:
        context = DatabaseContext.from_instance(fastjob_instance)
        print_status(
            f"Using instance-based configuration: {fastjob_instance.settings.database_url}",
            "info",
        )
    else:
        context = DatabaseContext.from_global_api()
        print_status("Using global API configuration", "info")

    set_current_context(context)

    try:
        print(f"\n{StatusIcon.rocket()} FastJob System Status")

        # 1. Health Check
        try:
            from fastjob.db.context import get_context_pool

            pool = await get_context_pool()
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
    finally:
        clear_current_context()

    # 2. Queue Statistics
    try:
        from fastjob.core.queue import get_queue_stats

        queues = await get_queue_stats()
        if queues:
            total_jobs = sum(q["total_jobs"] for q in queues)
            total_queued = sum(q["queued"] for q in queues)
            total_failed = sum(q["failed"] + q["dead_letter"] for q in queues)

            print("\nQueue Statistics:")
            print(f"  Total Jobs: {total_jobs}")
            print(f"  Queued: {total_queued}")
            print(f"  Failed/Dead Letter: {total_failed}")
            print(f"  Active Queues: {len(queues)}")

            if args.verbose:
                print("\nPer-Queue Breakdown:")
                print(
                    f"{'Queue':<15} {'Total':<8} {'Queued':<8} {'Done':<8} {'Failed':<8}"
                )
                print("-" * 60)
                for queue in queues:
                    print(
                        f"{queue['queue']:<15} {queue['total_jobs']:<8} {queue['queued']:<8} {queue['done']:<8} {queue['failed']:<8}"
                    )

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

    # 3. Worker Summary
    try:
        from fastjob.core.heartbeat import get_worker_status

        worker_status = await get_worker_status(pool)
        if "error" not in worker_status:
            status_counts = worker_status.get("status_counts", {})
            active_count = status_counts.get("active", 0)
            stale_count = len(worker_status.get("stale_workers", []))

            if active_count > 0 or stale_count > 0:
                worker_summary = f"{active_count} active"
                if stale_count > 0:
                    worker_summary += f", {stale_count} stale"
                worker_summary += " (use 'fastjob workers' for details)"
                print(f"\nWorkers: {worker_summary}")
            else:
                print("\nWorkers: None running (use 'fastjob start' to begin)")
    except Exception as e:
        # Don't fail the entire status command if worker status fails
        logger.debug(f"Could not get worker summary: {e}")

    # 4. Job Discovery (if verbose)
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

    # 5. Recent Jobs (if --jobs flag)
    if args.jobs:
        try:
            recent_jobs = await list_jobs(limit=10)
            if recent_jobs:
                print(f"\nRecent Jobs ({len(recent_jobs)}):")
                print(f"{'ID'[:8]:<8} {'Name':<25} {'Status':<12} {'Queue':<10}")
                print("-" * 60)
                for job in recent_jobs:
                    job_name = job["job_name"].split(".")[-1]  # Just function name
                    print(
                        f"{job['id'][:8]:<8} {job_name:<25} {job['status']:<12} {job['queue']:<10}"
                    )
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

    print("\nCommand Registry:")
    print(f"  Total commands: {status['total_commands']}")

    if status["categories"]:
        print("  Categories:")
        for category, count in status["categories"].items():
            print(f"    {category}: {count} command{'s' if count != 1 else ''}")

    print("\nRegistered Commands:")
    for category in registry.get_categories():
        commands = registry.get_commands_by_category(category)
        if commands:
            print(f"  {category.upper()}:")
            for cmd in commands:
                aliases_str = (
                    f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
                )
                print(f"    - {cmd.name}: {cmd.help}{aliases_str}")

    # Plugin information if requested
    if args.plugins:
        try:
            import fastjob

            plugin_status = fastjob.get_plugin_status()

            print("\nPlugin Status:")
            print(f"  Active plugins: {plugin_status['summary']['active_count']}")
            print(f"  Failed plugins: {plugin_status['summary']['failed_count']}")

            if plugin_status["active_plugins"]:
                print("  Active:")
                for name, info in plugin_status["active_plugins"].items():
                    print(f"    - {info['name']} v{info['version']}")

            if plugin_status["failed_plugins"]:
                print("  Failed:")
                for failed in plugin_status["failed_plugins"]:
                    print(f"    - {failed['name']}: {failed['error_type']}")

        except Exception as e:
            print_status(f"Could not get plugin information: {e}", "warning")

    return 0


async def handle_workers_command(args):
    """Handle workers command (worker monitoring functionality)"""
    from fastjob.core.heartbeat import cleanup_stale_workers, get_worker_status
    from fastjob.db.context import (
        DatabaseContext,
        clear_current_context,
        get_context_pool,
        set_current_context,
    )

    # Resolve FastJob instance from CLI arguments
    try:
        fastjob_instance = await resolve_fastjob_instance(args)
    except Exception as e:
        print_status(f"Configuration error: {e}", "error")
        return 1

    # Set up database context
    if fastjob_instance:
        context = DatabaseContext.from_instance(fastjob_instance)
        print_status(
            f"Using instance-based configuration: {fastjob_instance.settings.database_url}",
            "info",
        )
    else:
        context = DatabaseContext.from_global_api()
        print_status("Using global API configuration", "info")

    set_current_context(context)

    try:
        print(f"\n{StatusIcon.workers()} FastJob Worker Status")

        pool = await get_context_pool()

        # Clean up stale workers if requested
        if args.cleanup:
            print_status("Cleaning up stale worker records...", "info")
            cleaned = await cleanup_stale_workers(pool)
            if cleaned > 0:
                print_status(f"Cleaned up {cleaned} stale worker records", "success")
            else:
                print_status("No stale workers found", "info")
            print()

        # Get worker status
        worker_status = await get_worker_status(pool)

        if "error" in worker_status:
            print_status(
                f"Failed to get worker status: {worker_status['error']}", "error"
            )
            return 1

        # Display status summary
        status_counts = worker_status.get("status_counts", {})
        active_count = status_counts.get("active", 0)
        stopped_count = status_counts.get("stopped", 0)
        total_concurrency = worker_status.get("total_concurrency", 0)
        health = worker_status.get("health", "unknown")

        print(f"Health: {health.upper()}")
        print(f"Active Workers: {active_count}")
        print(f"Stopped Workers: {stopped_count}")
        print(f"Total Concurrency: {total_concurrency}")

        # Display active workers
        active_workers = worker_status.get("active_workers", [])
        if active_workers:
            print("\nActive Workers:")
            for worker in active_workers:
                uptime = int(worker["uptime_seconds"])
                uptime_str = f"{uptime//3600}h {(uptime%3600)//60}m {uptime%60}s"
                queues_str = (
                    ", ".join(worker["queues"]) if worker["queues"] else "all queues"
                )

                print(f"  🟢 {worker['hostname']}:{worker['pid']}")
                print(f"     Queues: {queues_str}")
                print(f"     Concurrency: {worker['concurrency']}")
                print(f"     Uptime: {uptime_str}")
                print(f"     Last Heartbeat: {worker['last_heartbeat']}")

                # Show metadata if available
                metadata = worker.get("metadata", {})
                if isinstance(metadata, dict) and metadata:
                    if "cpu_percent" in metadata:
                        print(f"     CPU: {metadata['cpu_percent']}%")
                    if "memory_mb" in metadata:
                        print(f"     Memory: {metadata['memory_mb']} MB")
                print()

        # Display stale workers if requested or if any exist
        stale_workers = worker_status.get("stale_workers", [])
        if stale_workers and (args.stale or health == "degraded"):
            print("\nStale Workers (no recent heartbeat):")
            for worker in stale_workers:
                stale_time = int(worker["stale_seconds"])
                stale_str = f"{stale_time//60}m {stale_time%60}s ago"

                print(f"  🔴 {worker['hostname']}:{worker['pid']}")
                print(f"     Last Heartbeat: {worker['last_heartbeat']} ({stale_str})")
                print()

            if not args.cleanup:
                print("Use --cleanup to remove stale worker records")

        if not active_workers and not stale_workers:
            print("\nNo workers found. Start workers with: fastjob start")

        return 0

    except Exception as e:
        print_status(f"Failed to get worker status: {e}", "error")
        return 1
    finally:
        clear_current_context()
