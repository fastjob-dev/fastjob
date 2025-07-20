"""
Job processing engine with proper transaction handling
Free Edition - Core functionality only
"""

import asyncio
import json
import time
from typing import Optional
import logging

import asyncpg
from pydantic import ValidationError

from fastjob.core.registry import get_job

# Basic logging for free edition
logger = logging.getLogger(__name__)


async def process_jobs(conn: asyncpg.Connection, queue: str = "default") -> bool:
    """
    Process a single job from the queue.
    
    Args:
        conn: Database connection
        queue: Queue name to process jobs from
        
    Returns:
        bool: True if a job was processed, False if no jobs available
    """
    # Use a transaction to ensure atomicity
    async with conn.transaction():
        # Lock and fetch the next job (ordered by priority then scheduled time)
        job_record = await conn.fetchrow("""
            SELECT * FROM fastjob_jobs
            WHERE status = 'queued' 
            AND queue = $1
            AND (scheduled_at IS NULL OR scheduled_at <= NOW())
            ORDER BY priority ASC, scheduled_at ASC NULLS FIRST, created_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        """, queue)
        
        if not job_record:
            return False

        job_id = job_record['id']
        job_name = job_record['job_name']
        args_data = json.loads(job_record['args'])
        attempts = job_record['attempts']
        max_attempts = job_record['max_attempts']
        
        # Basic logging
        start_time = time.time()
        logger.info(f"Processing job {job_id} ({job_name}) - attempt {attempts + 1}/{max_attempts}")

        job_meta = get_job(job_name)
        if not job_meta:
            await conn.execute("""
                UPDATE fastjob_jobs
                SET status = 'dead_letter', 
                    attempts = max_attempts,
                    last_error = $1, 
                    updated_at = NOW()
                WHERE id = $2
            """, f"Job {job_name} not registered.", job_id)
            logger.error(f"Job {job_name} not registered - moved to dead letter queue")
            return True

        try:
            # Validate arguments if model is specified
            args_model = job_meta.get("args_model")
            if args_model:
                validated_args = args_model(**args_data).model_dump()
            else:
                validated_args = args_data

            # Execute the job function
            await job_meta['func'](**validated_args)
            
            # Calculate duration
            duration_ms = round((time.time() - start_time) * 1000, 2)
            
            # Mark as successful
            await conn.execute("""
                UPDATE fastjob_jobs
                SET status = 'done', 
                    updated_at = NOW()
                WHERE id = $1
            """, job_id)
            
            logger.info(f"Job {job_id} completed successfully in {duration_ms}ms")
            return True
            
        except Exception as e:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.exception(f"Job {job_id} execution failed in {duration_ms}ms")
            
            new_attempts = attempts + 1
            if new_attempts >= max_attempts:
                # Permanently failed - move to dead letter queue
                await conn.execute("""
                    UPDATE fastjob_jobs
                    SET status = 'dead_letter', 
                        last_error = $1, 
                        attempts = $2, 
                        updated_at = NOW()
                    WHERE id = $3
                """, f"Max retries exceeded: {str(e)}", new_attempts, job_id)
                logger.error(f"Job {job_id} moved to dead letter queue after {new_attempts} attempts")
            else:
                # Retry
                await conn.execute("""
                    UPDATE fastjob_jobs
                    SET status = 'queued', 
                        last_error = $1, 
                        attempts = $2, 
                        updated_at = NOW()
                    WHERE id = $3
                """, str(e), new_attempts, job_id)
                logger.warning(f"Job {job_id} will be retried (attempt {new_attempts})")
            
            return True


async def run_worker(concurrency: int = 4, run_once: bool = False, database_url: Optional[str] = None, queues: list[str] = None):
    """
    Run the job worker process.
    
    Args:
        concurrency: Number of concurrent job processors
        run_once: If True, process available jobs once and exit
        database_url: Database URL to connect to
        queues: List of queue names to process. If None, processes 'default' queue
    """
    from fastjob.settings import FASTJOB_DATABASE_URL
    
    db_url = database_url or FASTJOB_DATABASE_URL
    try:
        pool = await asyncpg.create_pool(db_url)
    except Exception as e:
        logger.error(f"Failed to create database pool: {e}")
        raise
    
    # Default to processing the 'default' queue
    if queues is None:
        queues = ["default"]
    
    logger.info(f"Starting FastJob worker - concurrency: {concurrency}, queues: {queues}")
    
    try:
        if run_once:
            # Process jobs once from all queues
            if pool:
                async with pool.acquire() as conn:
                    for queue in queues:
                        await process_jobs(conn, queue)
            else:
                logger.warning("No database pool available for run_once processing")
        else:
            # Continuous processing
            async def worker():
                import itertools
                queue_cycle = itertools.cycle(queues)  # Round-robin through queues
                
                while True:
                    try:
                        queue = next(queue_cycle)
                        async with pool.acquire() as conn:
                            processed = await process_jobs(conn, queue)
                        
                        if not processed:
                            await asyncio.sleep(1)  # No jobs available, wait a bit
                    except Exception as e:
                        logger.exception(f"Worker error: {e}")
                        await asyncio.sleep(5)  # Error occurred, wait before retrying
            
            # Start multiple worker tasks for concurrency
            tasks = [asyncio.create_task(worker()) for _ in range(concurrency)]
            
            try:
                await asyncio.gather(*tasks)
            except KeyboardInterrupt:
                logger.info("Shutting down workers...")
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        if pool:
            await pool.close()
        logger.info("FastJob worker stopped")