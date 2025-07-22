"""
Worker command - start and manage FastJob workers
"""

import asyncio
from ..colors import print_status, StatusIcon


def add_worker_command(subparsers):
    """Add worker command to CLI"""
    worker_parser = subparsers.add_parser(
        "worker", 
        help="Start a FastJob worker",
        description="Start a FastJob worker to process background jobs"
    )
    worker_parser.add_argument("--concurrency", type=int, default=4, help="Number of concurrent workers (default: 4)")
    worker_parser.add_argument("--queues", default="default", help="Comma-separated list of queues to process (default: default)")
    worker_parser.set_defaults(func=handle_worker_command)


async def handle_worker_command(args):
    """Handle worker command"""
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