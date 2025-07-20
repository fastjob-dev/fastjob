
import argparse
import asyncio
import importlib
try:
    from importlib.metadata import entry_points
except ImportError:
    # Python < 3.8 compatibility
    from pkg_resources import iter_entry_points
from fastjob.core.processor import run_worker
from fastjob.db.migrations import run_migrations
from fastjob.core.discovery import discover_jobs


def load_plugin_commands(subparsers):
    """Load CLI commands from installed fastjob plugins"""
    try:
        # Try modern importlib.metadata first
        try:
            plugin_entry_points = entry_points().get('fastjob.plugins', [])
            entry_point_iter = plugin_entry_points
        except:
            # Fallback to pkg_resources for older Python versions
            entry_point_iter = iter_entry_points('fastjob.plugins')
        
        for entry_point in entry_point_iter:
            try:
                plugin_command = entry_point.load()
                # Create subparser for the plugin command
                plugin_parser = subparsers.add_parser(
                    entry_point.name, 
                    help=f"{entry_point.name} command (plugin)"
                )
                # Store the command function for later execution
                plugin_parser.set_defaults(plugin_func=plugin_command)
            except Exception as e:
                print(f"Warning: Could not load plugin command '{entry_point.name}': {e}")
    except Exception:
        # No plugins found or entry points not available
        pass


def main():
    parser = argparse.ArgumentParser(
        description="FastJob CLI - Unified Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  fastjob run-worker --concurrency 4 --queues default,urgent
  fastjob migrate
  fastjob health --verbose
  fastjob dashboard --host 0.0.0.0 --port 8000

For more information, visit: https://docs.fastjob.dev
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", title="Available commands")

    # Core commands (always available)
    run_worker_parser = subparsers.add_parser(
        "run-worker", 
        help="Run a FastJob worker",
        description="Start a FastJob worker to process background jobs"
    )
    run_worker_parser.add_argument("--concurrency", type=int, default=4, help="Number of concurrent jobs to process")
    run_worker_parser.add_argument("--run-once", action="store_true", help="Process available jobs once and exit")
    run_worker_parser.add_argument("--queues", nargs="+", default=["default"], help="Queues to process (comma-separated)")

    subparsers.add_parser("migrate", help="Run database migrations", description="Initialize or update FastJob database schema")
    
    # Health check commands
    health_parser = subparsers.add_parser(
        "health", 
        help="Check system health",
        description="Check the health status of FastJob components"
    )
    health_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed health information")
    
    subparsers.add_parser(
        "ready", 
        help="Check if service is ready (readiness probe)",
        description="Check if FastJob is ready to handle requests"
    )
    
    # Job management commands
    jobs_parser = subparsers.add_parser(
        "jobs",
        help="Job management commands",
        description="Manage FastJob jobs"
    )
    jobs_subparsers = jobs_parser.add_subparsers(dest="jobs_command", title="Job commands")
    
    # List jobs
    list_parser = jobs_subparsers.add_parser("list", help="List jobs")
    list_parser.add_argument("--queue", help="Filter by queue")
    list_parser.add_argument("--status", help="Filter by status")
    list_parser.add_argument("--limit", type=int, default=50, help="Maximum jobs to show")
    list_parser.add_argument("--failed", action="store_true", help="Show only failed jobs")
    
    # Job details
    show_parser = jobs_subparsers.add_parser("show", help="Show job details")
    show_parser.add_argument("job_id", help="Job ID to show")
    
    # Retry job
    retry_parser = jobs_subparsers.add_parser("retry", help="Retry a failed job")
    retry_parser.add_argument("job_id", help="Job ID to retry")
    
    # Cancel job
    cancel_parser = jobs_subparsers.add_parser("cancel", help="Cancel a queued job")
    cancel_parser.add_argument("job_id", help="Job ID to cancel")
    
    # Delete job
    delete_parser = jobs_subparsers.add_parser("delete", help="Delete a job")
    delete_parser.add_argument("job_id", help="Job ID to delete")
    delete_parser.add_argument("--force", action="store_true", help="Skip confirmation")
    
    # Queue management commands
    queues_parser = subparsers.add_parser(
        "queues",
        help="Queue management commands", 
        description="Manage FastJob queues"
    )
    queues_subparsers = queues_parser.add_subparsers(dest="queues_command", title="Queue commands")
    
    # List queues
    queues_subparsers.add_parser("list", help="List queue statistics")
    
    # Worker status
    subparsers.add_parser(
        "status",
        help="Show worker and queue status",
        description="Display current status of workers and queues"
    )

    # Load plugin commands from installed packages
    load_plugin_commands(subparsers)

    args = parser.parse_args()

    # Show version and startup info
    from .colors import print_header, StatusIcon, print_status, error, success, info
    
    # If no command specified, show help
    if not args.command:
        print_header("FastJob CLI")
        print_status("No command specified. Use --help for available commands.", "warning")
        print()
        parser.print_help()
        return

    # Show a friendly startup message for main commands
    if args.command not in ['health', 'ready']:
        print(f"{StatusIcon.rocket()} FastJob CLI")

    discover_jobs()

    # Handle core commands
    try:
        if args.command == "run-worker":
            print_status("Starting FastJob worker...", "info")
            asyncio.run(run_worker(args.concurrency, run_once=args.run_once, queues=args.queues))
        elif args.command == "migrate":
            print_status("Running database migrations...", "info")
            asyncio.run(run_migrations())
            print_status("Migrations completed successfully", "success")
        elif args.command == "health":
            from fastjob.health import cli_health_check
            exit_code = asyncio.run(cli_health_check(verbose=args.verbose))
            exit(exit_code)
        elif args.command == "ready":
            from fastjob.health import cli_readiness_check
            exit_code = asyncio.run(cli_readiness_check())
            exit(exit_code)
        elif args.command == "jobs":
            exit_code = asyncio.run(handle_jobs_command(args))
            exit(exit_code)
        elif args.command == "queues":
            exit_code = asyncio.run(handle_queues_command(args))
            exit(exit_code)
        elif args.command == "status":
            exit_code = asyncio.run(handle_status_command(args))
            exit(exit_code)
        elif hasattr(args, 'plugin_func'):
            # Handle plugin commands
            try:
                # For plugin commands, we need to re-parse with the plugin's arguments
                # Get remaining arguments for the plugin
                import sys
                remaining_args = sys.argv[2:]  # Skip 'fastjob' and command name
                
                # Create a new parser for the plugin to add its specific arguments
                plugin_parser = argparse.ArgumentParser(
                    prog=f"fastjob {args.command}",
                    description=f"{args.command} command"
                )
                exit_code = args.plugin_func(plugin_parser, remaining_args)
                exit(exit_code or 0)
            except Exception as e:
                print_status(f"Plugin command failed: {e}", "error")
                exit(1)
        else:
            print_status(f"Unknown command: {args.command}", "error")
            parser.print_help()
            exit(1)
            
    except KeyboardInterrupt:
        print_status("\nOperation cancelled by user", "warning")
        exit(130)
    except Exception as e:
        print_status(f"Command failed: {e}", "error")
        exit(1)


async def handle_jobs_command(args):
    """Handle job management commands"""
    from fastjob import get_job_status, cancel_job, retry_job, delete_job, list_jobs
    from .colors import print_status, StatusIcon
    import json
    
    if args.jobs_command == "list":
        status_filter = "failed" if args.failed else args.status
        jobs = await list_jobs(
            queue=args.queue,
            status=status_filter,
            limit=args.limit
        )
        
        if not jobs:
            print_status("No jobs found", "info")
            return 0
            
        print(f"\n{StatusIcon.info()} Found {len(jobs)} job(s)")
        print(f"{'ID':<36} {'Name':<30} {'Status':<12} {'Queue':<10} {'Created':<20}")
        print("-" * 120)
        
        for job in jobs:
            created = job['created_at'][:19].replace('T', ' ')
            print(f"{job['id']:<36} {job['job_name']:<30} {job['status']:<12} {job['queue']:<10} {created:<20}")
        
        return 0
        
    elif args.jobs_command == "show":
        job = await get_job_status(args.job_id)
        if not job:
            print_status(f"Couldn't find job {args.job_id}", "error")
            return 1
            
        print(f"\n{StatusIcon.info()} Job Details")
        print(f"ID: {job['id']}")
        print(f"Function: {job['job_name']}")
        print(f"Status: {job['status']}")
        print(f"Queue: {job['queue']}")
        print(f"Priority: {job['priority']}")
        print(f"Attempts: {job['attempts']}/{job['max_attempts']}")
        print(f"Created: {job['created_at']}")
        print(f"Updated: {job['updated_at']}")
        if job['scheduled_at']:
            print(f"Scheduled for: {job['scheduled_at']}")
        if job['last_error']:
            print(f"Last error: {job['last_error']}")
        print(f"Arguments: {json.dumps(job['args'], indent=2)}")
        
        return 0
        
    elif args.jobs_command == "retry":
        success = await retry_job(args.job_id)
        if success:
            print_status(f"Job {args.job_id} queued for retry", "success")
            return 0
        else:
            print_status(f"Failed to retry job {args.job_id} (not found or not retryable)", "error")
            return 1
            
    elif args.jobs_command == "cancel":
        success = await cancel_job(args.job_id)
        if success:
            print_status(f"Job {args.job_id} cancelled", "success")
            return 0
        else:
            print_status(f"Failed to cancel job {args.job_id} (not found or not cancellable)", "error")
            return 1
            
    elif args.jobs_command == "delete":
        if not args.force:
            response = input(f"Are you sure you want to delete job {args.job_id}? (y/N): ")
            if response.lower() != 'y':
                print_status("Delete cancelled", "info")
                return 0
                
        success = await delete_job(args.job_id)
        if success:
            print_status(f"Job {args.job_id} deleted", "success")
            return 0
        else:
            print_status(f"Failed to delete job {args.job_id} (not found)", "error")
            return 1
    
    return 1


async def handle_queues_command(args):
    """Handle queue management commands"""
    from fastjob import get_queue_stats
    from .colors import print_status, StatusIcon
    
    if args.queues_command == "list":
        queues = await get_queue_stats()
        
        if not queues:
            print_status("No queues found", "info")
            return 0
            
        print(f"\n{StatusIcon.info()} Queue Statistics")
        print(f"{'Queue':<15} {'Total':<8} {'Queued':<8} {'Done':<8} {'Failed':<8} {'Dead Letter':<12} {'Cancelled':<10}")
        print("-" * 85)
        
        for queue in queues:
            print(f"{queue['queue']:<15} {queue['total_jobs']:<8} {queue['queued']:<8} "
                  f"{queue['done']:<8} {queue['failed']:<8} {queue['dead_letter']:<12} {queue['cancelled']:<10}")
        
        return 0
    
    return 1


async def handle_status_command(args):
    """Handle status command"""
    from fastjob import get_queue_stats
    from .colors import print_status, StatusIcon
    
    print(f"\n{StatusIcon.rocket()} FastJob Status")
    
    # Show queue statistics
    queues = await get_queue_stats()
    if queues:
        total_jobs = sum(q['total_jobs'] for q in queues)
        total_queued = sum(q['queued'] for q in queues)
        total_failed = sum(q['failed'] + q['dead_letter'] for q in queues)
        
        print(f"\nOverall Statistics:")
        print(f"  Total Jobs: {total_jobs}")
        print(f"  Queued: {total_queued}")
        print(f"  Failed/Dead Letter: {total_failed}")
        print(f"  Active Queues: {len(queues)}")
        
        if total_queued > 0:
            print_status(f"{total_queued} jobs waiting to be processed", "warning")
        elif total_failed > 0:
            print_status(f"{total_failed} jobs need attention", "warning")
        else:
            print_status("All jobs processed successfully", "success")
    else:
        print_status("No jobs found in any queue", "info")
    
    return 0
