"""
Job management commands - list, show, retry, cancel, delete
"""

import json
import asyncio
from ..colors import print_status, StatusIcon


def add_jobs_commands(subparsers):
    """Add job management commands to CLI"""
    jobs_parser = subparsers.add_parser(
        "jobs", 
        help="Job management commands",
        description="List, inspect, and manage FastJob jobs"
    )
    
    jobs_subparsers = jobs_parser.add_subparsers(dest="jobs_command", title="Job commands")
    
    # List jobs
    list_parser = jobs_subparsers.add_parser("list", help="List jobs")
    list_parser.add_argument("--queue", help="Filter by queue name")
    list_parser.add_argument("--status", help="Filter by status (queued, done, failed, dead_letter)")
    list_parser.add_argument("--limit", type=int, default=50, help="Maximum number of jobs to show (default: 50)")
    
    # Show job details
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
    
    jobs_parser.set_defaults(func=handle_jobs_command)


async def handle_jobs_command(args):
    """Handle job management commands"""
    from fastjob import list_jobs, get_job_status, retry_job, cancel_job, delete_job
    
    if not hasattr(args, 'jobs_command') or args.jobs_command is None:
        print_status("Please specify a job command (list, show, retry, cancel, delete)", "error")
        return 1
    
    if args.jobs_command == "list":
        return await handle_list_jobs(args)
    elif args.jobs_command == "show":
        return await handle_show_job(args)
    elif args.jobs_command == "retry":
        return await handle_retry_job(args)
    elif args.jobs_command == "cancel":
        return await handle_cancel_job(args)
    elif args.jobs_command == "delete":
        return await handle_delete_job(args)
    else:
        print_status(f"Unknown job command: {args.jobs_command}", "error")
        return 1


async def handle_list_jobs(args):
    """Handle jobs list command"""
    from fastjob import list_jobs
    
    try:
        status_filter = args.status if hasattr(args, 'status') else None
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
        
    except Exception as e:
        print_status(f"Failed to list jobs: {e}", "error")
        return 1


async def handle_show_job(args):
    """Handle jobs show command"""
    from fastjob import get_job_status
    
    try:
        job = await get_job_status(args.job_id)
        if not job:
            print_status(f"Job {args.job_id} not found", "error")
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
        
    except Exception as e:
        print_status(f"Failed to show job: {e}", "error")
        return 1


async def handle_retry_job(args):
    """Handle jobs retry command"""
    from fastjob import retry_job
    
    try:
        success = await retry_job(args.job_id)
        if success:
            print_status(f"Job {args.job_id} queued for retry", "success")
            return 0
        else:
            print_status(f"Failed to retry job {args.job_id} (not found or not retryable)", "error")
            return 1
            
    except Exception as e:
        print_status(f"Failed to retry job: {e}", "error")
        return 1


async def handle_cancel_job(args):
    """Handle jobs cancel command"""
    from fastjob import cancel_job
    
    try:
        success = await cancel_job(args.job_id)
        if success:
            print_status(f"Job {args.job_id} cancelled", "success")
            return 0
        else:
            print_status(f"Failed to cancel job {args.job_id} (not found or not cancellable)", "error")
            return 1
            
    except Exception as e:
        print_status(f"Failed to cancel job: {e}", "error")
        return 1


async def handle_delete_job(args):
    """Handle jobs delete command"""
    from fastjob import delete_job
    
    try:
        success = await delete_job(args.job_id)
        if success:
            print_status(f"Job {args.job_id} deleted", "success")
            return 0
        else:
            print_status(f"Failed to delete job {args.job_id} (not found)", "error")
            return 1
            
    except Exception as e:
        print_status(f"Failed to delete job: {e}", "error")
        return 1