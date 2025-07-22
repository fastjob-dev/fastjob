"""
Health check and discovery commands
"""

import asyncio
from ..colors import print_status, StatusIcon


def add_health_commands(subparsers):
    """Add health and discovery commands to CLI"""
    health_parser = subparsers.add_parser(
        "health", 
        help="Check system health",
        description="Verify database connection and job system status"
    )
    health_parser.add_argument("--verbose", action="store_true", help="Show detailed health information")
    health_parser.set_defaults(func=handle_health_command)

    subparsers.add_parser(
        "discover", 
        help="Discover and list registered jobs",
        description="Show all jobs that can be enqueued"
    ).set_defaults(func=handle_discover_command)


async def handle_health_command(args):
    """Handle health command"""
    from fastjob.db.connection import get_pool
    
    print_status("Checking FastJob health...", "info")
    
    try:
        # Test database connection
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            if result == 1:
                print_status("Database connection: OK", "success")
            else:
                print_status("Database connection: FAILED", "error")
                return 1
                
        if args.verbose:
            print_status("Verbose health check passed", "info")
            
    except Exception as e:
        print_status(f"Health check failed: {e}", "error")
        return 1
    
    print_status("FastJob system is healthy", "success")
    return 0


async def handle_discover_command(args):
    """Handle discover command"""
    from fastjob.core.discovery import discover_jobs
    from fastjob.core.registry import get_all_jobs
    
    try:
        print_status("Discovering jobs...", "info")
        discover_jobs()
        jobs = get_all_jobs()
        
        if not jobs:
            print_status("No jobs found", "warning")
            return 0
            
        print(f"\n{StatusIcon.rocket()} Found {len(jobs)} job(s):")
        for job_name, job_info in jobs.items():
            print(f"  - {job_name}")
            if job_info.get("description"):
                print(f"    {job_info['description']}")
                
        return 0
        
    except Exception as e:
        print_status(f"Discovery failed: {e}", "error")
        return 1