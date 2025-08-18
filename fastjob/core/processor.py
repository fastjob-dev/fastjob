"""
Job processing engine with proper transaction handling
Core functionality only
"""

import asyncio
import json
import logging
import time
import uuid
from typing import List, Optional, Union

import asyncpg

from fastjob.core.registry import JobRegistry, get_job

# Basic logging for free edition
logger = logging.getLogger(__name__)


async def _move_job_to_dead_letter(
    conn: asyncpg.Connection, job_id: uuid.UUID, max_attempts: int, error_message: str
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


async def _fetch_and_lock_job(
    conn: asyncpg.Connection,
    queue: Optional[Union[str, List[str]]],
    heartbeat: Optional["WorkerHeartbeat"] = None,
) -> Optional[dict]:
    """
    Fetch and lock a job from the queue in a transaction.

    Args:
        conn: Database connection
        queue: Queue specification
        heartbeat: Optional worker heartbeat for tracking

    Returns:
        Job record dict or None if no jobs available
    """
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
            return None

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

    return dict(job_record)


async def _execute_job_safely(
    job_record: dict, job_meta: dict
) -> tuple[bool, Optional[str]]:
    """
    Execute a job function safely with proper error handling.

    Args:
        job_record: Job record from database
        job_meta: Job metadata from registry

    Returns:
        tuple: (success: bool, error_message: Optional[str])
    """
    job_record["id"]
    job_record["max_attempts"]

    # Parse job arguments with corruption handling
    try:
        args_data = json.loads(job_record["args"])
    except Exception as e:
        # Catch both JSONDecodeError and TypeError broadly for corrupted data
        if "json" in str(type(e)).lower() or isinstance(e, (TypeError, ValueError)):
            # This will be handled by the caller
            raise ValueError(f"Corrupted JSON data: {str(e)}") from e
        else:
            # Other exception types - re-raise
            raise

    # Validate arguments if model is specified
    args_model = job_meta.get("args_model")
    if args_model:
        try:
            validated_args = args_model(**args_data).model_dump()
        except (TypeError, ValueError, AttributeError) as validation_error:
            # This will be handled by the caller
            raise ValueError(
                f"Corrupted argument data: {str(validation_error)}"
            ) from validation_error
    else:
        validated_args = args_data

    # Execute the job function (outside transaction)
    try:
        await job_meta["func"](**validated_args)
        return True, None
    except (TypeError, AttributeError) as func_error:
        # Function signature mismatch or corrupted arguments
        if (
            "argument" in str(func_error).lower()
            or "parameter" in str(func_error).lower()
        ):
            # This will be handled by the caller as corruption
            raise ValueError(
                f"Function argument mismatch: {str(func_error)}"
            ) from func_error
        else:
            # Regular TypeError/AttributeError from job logic - should retry
            return False, str(func_error)
    except Exception as e:
        # Regular job execution error (not corruption)
        return False, str(e)


async def _update_job_status(
    conn: asyncpg.Connection,
    job_record: dict,
    success: bool,
    error_message: Optional[str],
    duration_ms: float,
) -> None:
    """
    Update job status in database based on execution result.

    Args:
        conn: Database connection
        job_record: Original job record
        success: Whether job execution succeeded
        error_message: Error message if job failed
        duration_ms: Job execution duration in milliseconds
    """
    job_id = job_record["id"]
    attempts = job_record["attempts"]
    max_attempts = job_record["max_attempts"]

    async with conn.transaction():
        if success:
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
                    f"Max retries exceeded: {error_message}",
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
                    error_message,
                    job_id,
                )
                logger.warning(
                    f"Job {job_id} will be retried (attempt {new_attempts} failed)"
                )


async def process_jobs(
    conn: asyncpg.Connection,
    queue: Optional[Union[str, List[str]]] = "default",
    heartbeat: Optional["WorkerHeartbeat"] = None,
) -> bool:
    """
    Process a single job from the queue(s).

    For compatibility with global API, this now checks the global app's registry
    in addition to the legacy global registry.

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
    job_record = await _fetch_and_lock_job(conn, queue, heartbeat)
    if not job_record:
        return False

    # Step 2: Extract job details
    job_id = job_record["id"]
    job_name = job_record["job_name"]
    attempts = job_record["attempts"]
    max_attempts = job_record["max_attempts"]

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
    try:
        job_success, job_error = await _execute_job_safely(job_record, job_meta)
    except ValueError as corruption_error:
        # Handle corruption errors - move to dead letter immediately
        logger.error(f"Job {job_id} has corrupted data: {corruption_error}")
        await _move_job_to_dead_letter(
            conn, job_id, max_attempts, str(corruption_error)
        )
        return True

    # Step 4: Update job status based on execution result
    duration_ms = round((time.time() - start_time) * 1000, 2)
    await _update_job_status(conn, job_record, job_success, job_error, duration_ms)

    return True


async def process_jobs_with_registry(
    conn: asyncpg.Connection,
    job_registry: JobRegistry,
    queue: Optional[Union[str, List[str]]] = "default",
    heartbeat: Optional["WorkerHeartbeat"] = None,
) -> bool:
    """
    Instance-based job processing with explicit JobRegistry.

    Process a single job from the queue(s) using a specific job registry instance.
    This enables instance-based FastJob applications with isolated job registries.

    Args:
        conn: Database connection
        job_registry: JobRegistry instance to use for job lookup
        queue: Queue specification:
               - None: Process from any queue (no filtering)
               - str: Process from single specific queue
               - List[str]: Process from multiple specific queues efficiently
        heartbeat: Optional worker heartbeat tracker

    Returns:
        bool: True if a job was processed, False if no jobs available
    """
    # Step 1: Fetch and lock a job in a minimal transaction
    job_record = await _fetch_and_lock_job(conn, queue, heartbeat)
    if not job_record:
        return False

    # Step 2: Extract job details
    job_id = job_record["id"]
    job_name = job_record["job_name"]
    attempts = job_record["attempts"]
    max_attempts = job_record["max_attempts"]

    # Basic logging
    start_time = time.time()
    logger.info(
        f"Processing job {job_id} ({job_name}) - attempt {attempts + 1}/{max_attempts}"
    )

    # Use instance-based job registry instead of global
    job_meta = job_registry.get_job(job_name)
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
            f"Job {job_name} not registered in this FastJob instance.",
            job_id,
        )
        logger.error(
            f"Job {job_name} not registered in instance registry - moved to dead letter queue"
        )
        return True

    # Step 3: Execute the job function OUTSIDE of any transaction
    try:
        job_success, job_error = await _execute_job_safely(job_record, job_meta)
    except ValueError as corruption_error:
        # Handle corruption separately - move directly to dead letter
        await _move_job_to_dead_letter(
            conn, job_id, max_attempts, str(corruption_error)
        )
        return True

    # Step 4: Update job status based on execution result
    duration_ms = round((time.time() - start_time) * 1000, 2)
    await _update_job_status(conn, job_record, job_success, job_error, duration_ms)

    return True
