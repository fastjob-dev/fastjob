"""
Job processing engine with proper transaction handling
Free Edition - Core functionality only
"""

import asyncio
import json
import logging
import time
import uuid
from typing import List, Optional, Union

import asyncpg

from fastjob.core.registry import get_job

# Basic logging for free edition
logger = logging.getLogger(__name__)


async def _move_job_to_dead_letter(
    conn: asyncpg.Connection, 
    job_id: uuid.UUID, 
    max_attempts: int, 
    error_message: str
) -> None:
    """
    Move a job to dead letter queue due to corruption or permanent failure.
    
    Args:
        conn: Database connection
        job_id: Job ID to move
        max_attempts: Maximum attempts for the job
        error_message: Error description
    """
    async with conn.transaction():
        await conn.execute(
            """
            UPDATE fastjob_jobs
            SET status = 'dead_letter',
                attempts = $2,
                last_error = $3,
                updated_at = NOW()
            WHERE id = $1
        """,
            job_id,
            max_attempts,
            error_message,
        )
    logger.error(f"Job {job_id} moved to dead letter queue: {error_message}")


async def process_jobs(
    conn: asyncpg.Connection, 
    queue: Optional[Union[str, List[str]]] = "default",
    heartbeat: Optional['WorkerHeartbeat'] = None
) -> bool:
    """
    Process a single job from the queue(s).

    This function has been refactored to execute jobs OUTSIDE of database transactions
    to prevent long-running jobs from holding database locks and causing deadlocks.

    Args:
        conn: Database connection
        queue: Queue specification:
               - None: Process from any queue (no filtering)
               - str: Process from single specific queue
               - List[str]: Process from multiple specific queues efficiently

    Returns:
        bool: True if a job was processed, False if no jobs available
    """
    # Step 1: Fetch and lock a job in a minimal transaction
    job_record = None
    async with conn.transaction():
        # Ensure timezone is UTC for consistent scheduled job handling
        await conn.execute("SET timezone = 'UTC'")

        # Lock and fetch the next job (ordered by priority then scheduled time)
        if queue is None:
            # Process from ANY queue (no filtering)
            job_record = await conn.fetchrow(
                """
                SELECT * FROM fastjob_jobs
                WHERE status = 'queued'
                AND (scheduled_at IS NULL OR scheduled_at <= NOW())
                ORDER BY priority ASC, scheduled_at ASC NULLS FIRST, created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            """
            )
        elif isinstance(queue, list):
            # Process from multiple specific queues efficiently
            job_record = await conn.fetchrow(
                """
                SELECT * FROM fastjob_jobs
                WHERE status = 'queued'
                AND queue = ANY($1)
                AND (scheduled_at IS NULL OR scheduled_at <= NOW())
                ORDER BY priority ASC, scheduled_at ASC NULLS FIRST, created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            """,
                queue,
            )
        else:
            # Process from single specific queue
            job_record = await conn.fetchrow(
                """
                SELECT * FROM fastjob_jobs
                WHERE status = 'queued'
                AND queue = $1
                AND (scheduled_at IS NULL OR scheduled_at <= NOW())
                ORDER BY priority ASC, scheduled_at ASC NULLS FIRST, created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            """,
                queue,
            )
        if not job_record:
            return False

        # Mark job as processing to prevent other workers from picking it up
        job_id = job_record["id"]
        if heartbeat:
            # Update job with worker tracking
            await conn.execute(
                """
                UPDATE fastjob_jobs
                SET status = 'processing',
                    worker_id = $2,
                    updated_at = NOW()
                WHERE id = $1
            """,
                job_id,
                heartbeat.worker_id,
            )
        else:
            await conn.execute(
                """
                UPDATE fastjob_jobs
                SET status = 'processing',
                    updated_at = NOW()
                WHERE id = $1
            """,
                job_id,
            )

    # Step 2: Extract job details (outside transaction)
    job_id = job_record["id"]
    job_name = job_record["job_name"]
    attempts = job_record["attempts"]
    max_attempts = job_record["max_attempts"]
    
    # Parse job arguments with corruption handling
    try:
        args_data = json.loads(job_record["args"])
    except (Exception) as e:
        # Catch both JSONDecodeError and TypeError broadly for corrupted data
        if "json" in str(type(e)).lower() or isinstance(e, (TypeError, ValueError)):
            # Corrupted JSON data - move to dead letter immediately
            logger.error(f"Job {job_id} has corrupted JSON data: {e}")
            await _move_job_to_dead_letter(
                conn, job_id, max_attempts,
                f"Corrupted JSON data: {str(e)}"
            )
            return True
        else:
            # Other exception types - re-raise
            raise

    # Basic logging
    start_time = time.time()
    logger.info(
        f"Processing job {job_id} ({job_name}) - attempt {attempts + 1}/{max_attempts}"
    )

    job_meta = get_job(job_name)
    if not job_meta:
        await conn.execute(
            """
            UPDATE fastjob_jobs
            SET status = 'dead_letter',
                attempts = max_attempts,
                last_error = $1,
                updated_at = NOW()
            WHERE id = $2
        """,
            f"Job {job_name} not registered.",
            job_id,
        )
        logger.error(f"Job {job_name} not registered - moved to dead letter queue")
        return True

    # Step 3: Execute the job function OUTSIDE of any transaction
    job_success = False
    job_error = None

    try:
        # Validate arguments if model is specified
        args_model = job_meta.get("args_model")
        if args_model:
            try:
                validated_args = args_model(**args_data).model_dump()
            except (TypeError, ValueError, AttributeError) as validation_error:
                # Argument validation failed - data structure is corrupted
                logger.error(f"Job {job_id} has corrupted argument data: {validation_error}")
                await _move_job_to_dead_letter(
                    conn, job_id, max_attempts,
                    f"Corrupted argument data: {str(validation_error)}"
                )
                return True
        else:
            validated_args = args_data

        # Execute the job function (outside transaction)
        try:
            await job_meta["func"](**validated_args)
            job_success = True
        except (TypeError, AttributeError) as func_error:
            # Function signature mismatch or corrupted arguments
            if "argument" in str(func_error).lower() or "parameter" in str(func_error).lower():
                logger.error(f"Job {job_id} has argument mismatch: {func_error}")
                await _move_job_to_dead_letter(
                    conn, job_id, max_attempts,
                    f"Function argument mismatch: {str(func_error)}"
                )
                return True
            else:
                # Regular TypeError/AttributeError from job logic - should retry
                raise

    except Exception as e:
        job_error = str(e)
        logger.exception(f"Job {job_id} execution failed")

    # Step 4: Update job status based on execution result in a separate transaction
    duration_ms = round((time.time() - start_time) * 1000, 2)

    async with conn.transaction():
        if job_success:
            # Handle job result TTL setting
            from fastjob.settings import get_settings

            settings = get_settings()

            if settings.result_ttl == 0:
                # Delete immediately (TTL = 0)
                await conn.execute(
                    """
                    DELETE FROM fastjob_jobs
                    WHERE id = $1
                """,
                    job_id,
                )
                logger.info(
                    f"Job {job_id} completed successfully in {duration_ms}ms (deleted immediately)"
                )
            else:
                # Keep with status 'done' and set expires_at for TTL cleanup
                await conn.execute(
                    """
                    UPDATE fastjob_jobs
                    SET status = 'done',
                        expires_at = NOW() + ($2 || ' seconds')::INTERVAL,
                        updated_at = NOW()
                    WHERE id = $1
                """,
                    job_id,
                    str(settings.result_ttl),
                )
                logger.info(
                    f"Job {job_id} completed successfully in {duration_ms}ms (expires in {settings.result_ttl}s)"
                )
        else:
            # Job failed - increment attempts
            new_attempts = attempts + 1
            if new_attempts >= max_attempts:
                # Permanently failed - move to dead letter queue
                await conn.execute(
                    """
                    UPDATE fastjob_jobs
                    SET status = 'dead_letter',
                        attempts = $1,
                        last_error = $2,
                        updated_at = NOW()
                    WHERE id = $3
                """,
                    new_attempts,
                    f"Max retries exceeded: {job_error}",
                    job_id,
                )
                logger.error(
                    f"Job {job_id} moved to dead letter queue after {new_attempts} attempts"
                )
            else:
                # Retry - reset to queued status
                await conn.execute(
                    """
                    UPDATE fastjob_jobs
                    SET status = 'queued',
                        attempts = $1,
                        last_error = $2,
                        updated_at = NOW()
                    WHERE id = $3
                """,
                    new_attempts,
                    job_error,
                    job_id,
                )
                logger.warning(
                    f"Job {job_id} will be retried (attempt {new_attempts} failed)"
                )

    return True


async def run_worker(
    concurrency: int = 4,
    run_once: bool = False,
    database_url: Optional[str] = None,
    queues: list[str] = None,
):
    """
    Run the job worker process.

    Args:
        concurrency: Number of concurrent job processors
        run_once: If True, process available jobs once and exit
        database_url: Database URL to connect to
        queues: List of queue names to process. If None, discovers and processes all available queues
    """
    from fastjob.db.connection import create_pool
    from fastjob.settings import get_settings
    from fastjob.core.heartbeat import WorkerHeartbeat, cleanup_stale_workers

    db_url = database_url or get_settings().database_url
    try:
        pool = await create_pool(db_url)
    except Exception as e:
        logger.error(f"Failed to create database pool: {e}")
        raise

    # queues=None means process jobs from ALL queues (no filtering)
    # queues=["specific"] means process only from those specific queues

    queue_info = "all queues" if queues is None else f"queues: {queues}"
    logger.info(
        f"Starting FastJob worker - concurrency: {concurrency}, processing: {queue_info}"
    )

    try:
        if run_once:
            # Process jobs once from all queues
            if pool:
                async with pool.acquire() as conn:
                    # Process jobs efficiently - single query regardless of queue specification
                    await process_jobs(conn, queues)
            else:
                logger.warning("No database pool available for run_once processing")
        else:
            # Create worker heartbeat system
            heartbeat = WorkerHeartbeat(pool, queues, concurrency)
            await heartbeat.register_worker()
            await heartbeat.start_heartbeat()
            
            # Continuous processing with LISTEN/NOTIFY
            async def worker():
                # Each worker needs its own connection for LISTEN/NOTIFY
                listen_conn = await pool.acquire()
                notification_event = asyncio.Event()

                def notification_callback(connection, pid, channel, payload):
                    logger.debug(f"Received notification on {channel}: {payload}")
                    notification_event.set()

                try:
                    # Set up LISTEN for job notifications
                    await listen_conn.add_listener(
                        "fastjob_new_job", notification_callback
                    )

                    # Track last cleanup time for periodic cleanup
                    last_cleanup = 0
                    cleanup_interval = 300  # 5 minutes

                    while True:
                        try:
                            # Process jobs from all queues first
                            any_processed = False

                            # Use separate connection for job processing to avoid blocking LISTEN
                            async with pool.acquire() as job_conn:
                                # Process jobs efficiently - single query regardless of queue specification
                                processed = await process_jobs(job_conn, queues, heartbeat)
                                if processed:
                                    any_processed = True

                                # Run periodic cleanup of expired jobs
                                current_time = time.time()
                                if current_time - last_cleanup > cleanup_interval:
                                    try:
                                        # Clean up expired completed jobs if RESULT_TTL is set
                                        from fastjob.settings import get_settings

                                        settings = get_settings()

                                        if settings.result_ttl > 0:
                                            cleaned = await job_conn.execute(
                                                "DELETE FROM fastjob_jobs WHERE status = 'done' AND expires_at < NOW()"
                                            )
                                            cleaned_count = (
                                                int(cleaned.split()[-1])
                                                if cleaned
                                                else 0
                                            )
                                            if cleaned_count > 0:
                                                logger.debug(
                                                    f"Cleaned up {cleaned_count} expired jobs"
                                                )
                                        
                                        # Clean up stale workers (no heartbeat in 5+ minutes)
                                        stale_workers = await cleanup_stale_workers(pool, stale_threshold_seconds=300)
                                        
                                        last_cleanup = current_time
                                    except Exception as cleanup_error:
                                        logger.warning(
                                            f"Cleanup failed: {cleanup_error}"
                                        )
                                        last_cleanup = (
                                            current_time  # Prevent continuous retries
                                        )

                            if not any_processed:
                                # No jobs available, wait for NOTIFY with timeout
                                try:
                                    # Wait for notification with 5 second timeoaut
                                    await asyncio.wait_for(
                                        notification_event.wait(), timeout=5.0
                                    )
                                    notification_event.clear()  # Reset for next notification
                                    logger.debug("Received job notification")
                                except asyncio.TimeoutError:
                                    # Timeout is normal - allows periodic checks for scheduled jobs
                                    logger.debug(
                                        "No notifications, checking for scheduled jobs"
                                    )
                                    pass

                        except Exception as e:
                            logger.exception(f"Worker error: {e}")
                            await asyncio.sleep(
                                5
                            )  # Error occurred, wait before retrying

                finally:
                    await listen_conn.remove_listener(
                        "fastjob_new_job", notification_callback
                    )
                    await pool.release(listen_conn)

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
                # Stop heartbeat system
                await heartbeat.stop_heartbeat()
    finally:
        if pool:
            await pool.close()
        logger.info("FastJob worker stopped")
