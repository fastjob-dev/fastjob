"""
Embedded worker for local development - simple, fast, and reliable
"""

import asyncio
import logging
from typing import Optional

from fastjob.core.processor import process_jobs
from fastjob.db.connection import get_pool

logger = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None
_shutdown_event: Optional[asyncio.Event] = None


async def _run_embedded_worker_loop(
    concurrency: int = 1, 
    run_once: bool = False,
    poll_interval: float = 0.5
):
    """
    Run the embedded worker loop
    
    Args:
        concurrency: Number of concurrent job processors (default: 1)
        run_once: If True, process available jobs once and exit (for testing)
        poll_interval: How often to check for new jobs in seconds (default: 0.5)
    """
    global _shutdown_event
    _shutdown_event = asyncio.Event()
    
    # Get a fresh pool for this event loop
    try:
        from fastjob.db.connection import close_pool
        await close_pool()  # Close any existing pool from different event loop
    except Exception:
        pass  # Ignore errors from closing pools from different event loops
    pool = await get_pool()
    logger.info(f"Starting embedded worker (concurrency: {concurrency}, run_once: {run_once})")
    
    async def worker_task():
        """Individual worker task"""
        while not _shutdown_event.is_set():
            try:
                async with pool.acquire() as conn:
                    processed = await process_jobs(conn)
                
                if run_once and not processed:
                    # In run_once mode, exit if no jobs were processed
                    break
                    
                if not processed:
                    # No jobs processed, wait before checking again
                    try:
                        await asyncio.wait_for(_shutdown_event.wait(), timeout=poll_interval)
                        break  # Shutdown requested
                    except asyncio.TimeoutError:
                        pass  # Continue loop
                        
            except Exception as e:
                logger.exception(f"Embedded worker error: {e}")
                if run_once:
                    break  # Don't retry in run_once mode
                # Wait before retrying on error
                try:
                    await asyncio.wait_for(_shutdown_event.wait(), timeout=2.0)
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    pass  # Continue loop
    
    try:
        # Start multiple worker tasks for concurrency
        if concurrency == 1:
            await worker_task()
        else:
            tasks = [asyncio.create_task(worker_task()) for _ in range(concurrency)]
            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        logger.info("Embedded worker stopped")


def start_embedded_worker(concurrency: int = 1, run_once: bool = False, poll_interval: float = 0.5):
    """
    Start the embedded worker task (synchronous version for easy use)
    
    Args:
        concurrency: Number of concurrent job processors (default: 1)
        run_once: If True, process available jobs once and exit (for testing)
        poll_interval: How often to check for new jobs in seconds (default: 0.5)
    
    Examples:
        # Basic usage in web app startup
        fastjob.start_embedded_worker()
        
        # For testing - process once and exit
        fastjob.start_embedded_worker(run_once=True)
        
        # Higher concurrency for busy development
        fastjob.start_embedded_worker(concurrency=4)
    """
    global _task
    
    if _task is not None and not _task.done():
        logger.warning("Embedded worker is already running")
        return
        
    _task = asyncio.create_task(_run_embedded_worker_loop(concurrency, run_once, poll_interval))
    logger.info("Embedded worker task created")


async def start_embedded_worker_async(concurrency: int = 1, run_once: bool = False, poll_interval: float = 0.5):
    """
    Start the embedded worker (async version for advanced use cases)
    
    Args:
        concurrency: Number of concurrent job processors (default: 1)
        run_once: If True, process available jobs once and exit (for testing)
        poll_interval: How often to check for new jobs in seconds (default: 0.5)
        
    Returns:
        The worker task, or runs immediately if run_once=True
    
    Examples:
        # In async tests
        await fastjob.start_embedded_worker_async(run_once=True)
        
        # Start background worker in async app startup
        worker_task = await fastjob.start_embedded_worker_async()
    """
    global _task
    
    if run_once:
        # For run_once, execute immediately and return
        await _run_embedded_worker_loop(concurrency, run_once, poll_interval)
        return None
    
    # For continuous operation, start background task
    if _task is not None and not _task.done():
        logger.warning("Embedded worker is already running")
        return _task
        
    _task = asyncio.create_task(_run_embedded_worker_loop(concurrency, run_once, poll_interval))
    logger.info("Embedded worker task created")
    return _task


async def stop_embedded_worker():
    """Stop the embedded worker"""
    global _task, _shutdown_event
    
    if _shutdown_event:
        _shutdown_event.set()
        
    if _task:
        try:
            await asyncio.wait_for(_task, timeout=5.0)  # Reduced timeout
        except asyncio.TimeoutError:
            logger.warning("Embedded worker didn't stop gracefully, cancelling...")
            _task.cancel()
            try:
                await _task
            except asyncio.CancelledError:
                pass
        except Exception as e:
            logger.warning(f"Error stopping embedded worker: {e}")
            if _task and not _task.done():
                _task.cancel()
                try:
                    await _task
                except asyncio.CancelledError:
                    pass
        _task = None
        
    _shutdown_event = None
    logger.info("Embedded worker stopped")


def is_embedded_worker_running() -> bool:
    """Check if embedded worker is currently running"""
    global _task
    return _task is not None and not _task.done()


def get_embedded_worker_status() -> dict:
    """Get embedded worker status information"""
    global _task
    return {
        "running": is_embedded_worker_running(),
        "task_exists": _task is not None,
        "task_done": _task.done() if _task else True
    }