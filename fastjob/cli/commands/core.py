"""
Consolidated FastJob CLI commands - simplified to 3 core commands
"""

import asyncio
import json
from ..colors import print_status, StatusIcon


def add_core_commands(subparsers):
    """Add the 3 core consolidated commands"""
    add_start_command(subparsers)
    add_setup_command(subparsers)  
    add_status_command(subparsers)


def add_start_command(subparsers):
    """Add start command (consolidates worker)"""
    start_parser = subparsers.add_parser(
        "start", 
        help="Start FastJob worker",
        description="Start FastJob worker to process background jobs"
    )
    start_parser.add_argument("--concurrency", type=int, default=4, help="Number of concurrent workers (default: 4)")
    start_parser.add_argument("--queues", default="default", help="Comma-separated list of queues to process (default: default)")
    start_parser.set_defaults(func=handle_start_command)


def add_setup_command(subparsers):
    """Add setup command (consolidates migrate)"""
    subparsers.add_parser(
        "setup", 
        help="Setup FastJob database", 
        description="Initialize or update FastJob database schema"
    ).set_defaults(func=handle_setup_command)


def add_status_command(subparsers):
    """Add status command (consolidates health, jobs, queues)"""
    status_parser = subparsers.add_parser(
        "status", 
        help="Show system status",
        description="Display system health, job statistics, and queue information"
    )
    status_parser.add_argument("--jobs", action="store_true", help="Show recent jobs")
    status_parser.add_argument("--verbose", action="store_true", help="Show detailed information")
    status_parser.set_defaults(func=handle_status_command)


async def handle_start_command(args):
    """Handle start command (worker functionality)"""
    from fastjob.core.processor import run_worker
    
    queues = [q.strip() for q in args.queues.split(",")]
    
    print_status(f"Starting FastJob worker with {args.concurrency} workers", "info")
    print_status(f"Processing queues: {', '.join(queues)}", "info")
    
    try:
        await run_worker(concurrency=args.concurrency, queues=queues)
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
    
    try:
        print_status("Setting up FastJob database...", "info")
        await run_migrations()
        print_status("Database setup completed successfully", "success")
        return 0
    except Exception as e:
        print_status(f"Setup failed: {e}", "error")
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