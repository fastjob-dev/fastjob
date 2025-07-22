"""
Queue management and status commands
"""

import asyncio
from ..colors import print_status, StatusIcon


def add_queues_commands(subparsers):
    """Add queue management commands to CLI"""
    queues_parser = subparsers.add_parser(
        "queues", 
        help="Queue management commands",
        description="View and manage FastJob queues"
    )
    
    queues_subparsers = queues_parser.add_subparsers(dest="queues_command", title="Queue commands")
    
    # List queues
    queues_subparsers.add_parser("list", help="List queue statistics")
    
    # Add status command for overall system status
    subparsers.add_parser(
        "status", 
        help="Show overall system status",
        description="Display job queue statistics and system health"
    ).set_defaults(func=handle_status_command)
    
    queues_parser.set_defaults(func=handle_queues_command)


async def handle_queues_command(args):
    """Handle queue management commands"""
    if not hasattr(args, 'queues_command') or args.queues_command is None:
        print_status("Please specify a queue command (list)", "error")
        return 1
    
    if args.queues_command == "list":
        return await handle_list_queues()
    else:
        print_status(f"Unknown queue command: {args.queues_command}", "error")
        return 1


async def handle_list_queues():
    """Handle queues list command"""
    from fastjob import get_queue_stats
    
    try:
        queues = await get_queue_stats()
        
        if not queues:
            print_status("No queues found", "info")
            return 0
            
        print(f"\n{StatusIcon.info()} Queue Statistics")
        print(f"{'Queue':<15} {'Total':<8} {'Queued':<8} {'Done':<8} {'Failed':<8} {'Dead Letter':<12}")
        print("-" * 70)
        
        for queue in queues:
            print(f"{queue['queue']:<15} {queue['total_jobs']:<8} {queue['queued']:<8} {queue['done']:<8} {queue['failed']:<8} {queue['dead_letter']:<12}")
        
        return 0
        
    except Exception as e:
        print_status(f"Failed to list queues: {e}", "error")
        return 1


async def handle_status_command(args):
    """Handle status command"""
    from fastjob import get_queue_stats
    
    print(f"\n{StatusIcon.rocket()} FastJob Status")
    
    try:
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
        
    except Exception as e:
        print_status(f"Failed to get status: {e}", "error")
        return 1