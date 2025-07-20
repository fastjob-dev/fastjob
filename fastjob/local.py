"""
Embedded worker for local development
"""

import asyncio
import logging
from typing import Optional

from fastjob.core.processor import process_jobs
from fastjob.db.connection import get_pool

logger = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None
_shutdown_event: Optional[asyncio.Event] = None


async def _run_embedded_worker_loop():
    """Run the embedded worker loop"""
    global _shutdown_event
    _shutdown_event = asyncio.Event()
    
    pool = await get_pool()
    logger.info("Starting embedded worker")
    
    try:
        while not _shutdown_event.is_set():
            try:
                async with pool.acquire() as conn:
                    processed = await process_jobs(conn)
                
                if not processed:
                    # No jobs processed, wait a bit before checking again
                    try:
                        await asyncio.wait_for(_shutdown_event.wait(), timeout=1.0)
                        break  # Shutdown requested
                    except asyncio.TimeoutError:
                        pass  # Continue loop
                        
            except Exception as e:
                logger.exception(f"Embedded worker error: {e}")
                # Wait before retrying on error
                try:
                    await asyncio.wait_for(_shutdown_event.wait(), timeout=5.0)
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    pass  # Continue loop
    finally:
        logger.info("Embedded worker stopped")


def start_embedded_worker():
    """Start the embedded worker task"""
    global _task
    
    if _task is not None and not _task.done():
        logger.warning("Embedded worker is already running")
        return
        
    _task = asyncio.create_task(_run_embedded_worker_loop())
    logger.info("Embedded worker task created")


async def stop_embedded_worker():
    """Stop the embedded worker"""
    global _task, _shutdown_event
    
    if _shutdown_event:
        _shutdown_event.set()
        
    if _task:
        try:
            await asyncio.wait_for(_task, timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Embedded worker didn't stop gracefully, cancelling...")
            _task.cancel()
            try:
                await _task
            except asyncio.CancelledError:
                pass
        _task = None
        
    _shutdown_event = None
    logger.info("Embedded worker stopped")