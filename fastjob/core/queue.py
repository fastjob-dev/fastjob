"""
Job queue operations - the heart of FastJob

This handles everything related to putting jobs in the queue and managing them.
The goal is to make it feel natural and reliable for developers.
"""

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Union

from pydantic import ValidationError

from fastjob.core.registry import get_job
from fastjob.db.connection import get_pool
from fastjob.utils.hashing import compute_args_hash


def _validate_job_arguments(job_name: str, job_meta: dict, kwargs: dict) -> None:
    """
    Validate job arguments against the job's Pydantic model.
    
    Args:
        job_name: Name of the job function
        job_meta: Job metadata from registry
        kwargs: Arguments to validate
        
    Raises:
        ValueError: If arguments are invalid
    """
    args_model = job_meta.get("args_model")
    if args_model:
        try:
            args_model(**kwargs)  # Validate arguments
        except ValidationError as e:
            raise ValueError(f"Invalid arguments for job {job_name}: {e}") from e


def _normalize_scheduled_time(scheduled_at: Optional[datetime]) -> Optional[datetime]:
    """
    Normalize scheduled_at to be timezone-naive in UTC.
    
    Args:
        scheduled_at: Optional datetime to normalize
        
    Returns:
        Normalized datetime or None
    """
    if not scheduled_at:
        return None
        
    if scheduled_at.tzinfo is not None:
        # Convert timezone-aware datetime to UTC
        return scheduled_at.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        # For timezone-naive datetime, assume it's in local time and convert to UTC
        # Get the local timezone offset and apply it to get UTC
        # Get timezone offset in seconds (accounts for DST)
        is_dst = time.daylight and time.localtime().tm_isdst
        offset_seconds = time.altzone if is_dst else time.timezone
        # timezone/altzone gives seconds west of UTC (negative for east)
        # To convert local time to UTC, we add this offset (which is negative for eastern timezones)
        offset_delta = timedelta(seconds=offset_seconds)
        return scheduled_at + offset_delta


async def _handle_unique_job_check(conn, job_name: str, args_hash: str) -> Optional[str]:
    """
    Check for existing unique job and return its ID if found.
    
    Args:
        conn: Database connection
        job_name: Name of the job function
        args_hash: Hash of job arguments
        
    Returns:
        Existing job ID if found, None otherwise
    """
    existing_job = await conn.fetchrow(
        """
        SELECT id FROM fastjob_jobs
        WHERE job_name = $1 AND args_hash = $2 AND status = 'queued' AND unique_job = TRUE
    """,
        job_name,
        args_hash,
    )
    
    if existing_job:
        return str(existing_job["id"])
    return None


async def _create_job_record(
    conn,
    job_id: str,
    job_name: str,
    job_meta: dict,
    args_json: str,
    args_hash: Optional[str],
    final_priority: int,
    final_queue: str,
    final_unique: bool,
    scheduled_at: Optional[datetime],
) -> None:
    """
    Create a new job record in the database.
    
    Args:
        conn: Database connection
        job_id: Generated job ID
        job_name: Name of the job function
        job_meta: Job metadata from registry
        args_json: JSON-serialized arguments
        args_hash: Hash of arguments for uniqueness
        final_priority: Final priority value
        final_queue: Final queue name
        final_unique: Whether job is unique
        scheduled_at: When to execute the job
    """
    await conn.execute(
        """
        INSERT INTO fastjob_jobs (id, job_name, args, args_hash, max_attempts, priority, queue, unique_job, scheduled_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    """,
        uuid.UUID(job_id),
        job_name,
        args_json,
        args_hash,
        job_meta["retries"] + 1,  # max_attempts = retries + 1 (original attempt + retries)
        final_priority,
        final_queue,
        final_unique,
        scheduled_at,
    )

    # Notify workers about the new job for instant processing
    await conn.execute(f"NOTIFY fastjob_new_job, '{final_queue}'")


async def enqueue(
    job_func: Callable[..., Any],
    priority: Optional[int] = None,
    queue: Optional[str] = None,
    scheduled_at: Optional[datetime] = None,
    unique: Optional[bool] = None,
    **kwargs,
) -> str:
    """
    Enqueue a job for processing.

    Args:
        job_func: The decorated job function to enqueue
        priority: Job priority (lower number = higher priority). If None, uses job default
        queue: Queue name. If None, uses job default
        scheduled_at: When to execute the job. If None, executes immediately
        unique: Override job's unique setting. If True, prevents duplicate queued jobs
        **kwargs: Arguments to pass to the job function

    Returns:
        str: The job ID, or existing job ID if unique job already exists

    Raises:
        ValueError: If job is not registered or arguments are invalid
    """
    # Ensure plugins are loaded automatically
    from fastjob import _ensure_plugins_loaded

    _ensure_plugins_loaded()

    job_name = f"{job_func.__module__}.{job_func.__name__}"
    job_meta = get_job(job_name)
    if not job_meta:
        raise ValueError(f"Job {job_name} not registered.")

    # Step 1: Validate arguments
    _validate_job_arguments(job_name, job_meta, kwargs)

    # Step 2: Determine final settings - use caller values or job defaults
    final_priority = priority if priority is not None else job_meta["priority"]
    final_queue = queue if queue is not None else job_meta["queue"]
    final_unique = unique if unique is not None else job_meta["unique"]

    # Step 3: Normalize scheduled time
    normalized_scheduled_at = _normalize_scheduled_time(scheduled_at)

    # Step 4: Prepare job data
    job_id = str(uuid.uuid4())
    args_json = json.dumps(kwargs)
    args_hash = compute_args_hash(kwargs) if final_unique else None

    pool = await get_pool()

    async with pool.acquire() as conn:
        # Ensure timezone is UTC for consistent scheduled job handling
        await conn.execute("SET timezone = 'UTC'")

        # Step 5: Handle unique job checking
        if final_unique:
            existing_job_id = await _handle_unique_job_check(conn, job_name, args_hash)
            if existing_job_id:
                return existing_job_id

        # Step 6: Create the job record
        try:
            await _create_job_record(
                conn,
                job_id,
                job_name,
                job_meta,
                args_json,
                args_hash,
                final_priority,
                final_queue,
                final_unique,
                normalized_scheduled_at,
            )
        except Exception as e:
            # Sometimes the database unique constraint catches duplicates we missed
            if (
                final_unique
                and "duplicate key value violates unique constraint" in str(e)
            ):
                # Let's find the job that beat us to it using args_hash
                existing_job_id = await _handle_unique_job_check(conn, job_name, args_hash)
                if existing_job_id:
                    return existing_job_id

            # If it's not a uniqueness issue, something else went wrong
            raise

    return job_id


async def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Look up a job and get all its details.

    This is really handy for checking on jobs - you get back everything
    from when it was created to how many times it's been retried.

    Args:
        job_id: The job ID to look up

    Returns:
        Dict with all the job details, or None if the job doesn't exist
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, job_name, args, status, attempts, max_attempts,
                   queue, priority, scheduled_at, last_error,
                   created_at, updated_at
            FROM fastjob_jobs
            WHERE id = $1
        """,
            uuid.UUID(job_id),
        )

        if not row:
            return None

        return {
            "id": str(row["id"]),
            "job_name": row["job_name"],
            "args": json.loads(row["args"]),
            "status": row["status"],
            "attempts": row["attempts"],
            "max_attempts": row["max_attempts"],
            "queue": row["queue"],
            "priority": row["priority"],
            "scheduled_at": (
                row["scheduled_at"].isoformat() if row["scheduled_at"] else None
            ),
            "last_error": row["last_error"],
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }


async def cancel_job(job_id: str) -> bool:
    """
    Cancel a job that's waiting in the queue.

    Note: You can only cancel jobs that haven't started running yet.
    Once a worker picks up a job, you'll need to let it finish.

    Args:
        job_id: The job ID to cancel

    Returns:
        True if we cancelled it, False if we couldn't (maybe it doesn't exist or already started)
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Only allow cancelling queued jobs
        result = await conn.execute(
            """
            UPDATE fastjob_jobs
            SET status = 'cancelled', updated_at = NOW()
            WHERE id = $1 AND status = 'queued'
        """,
            uuid.UUID(job_id),
        )

        # Check if any rows were affected
        return result.split()[-1] == "1"


async def retry_job(job_id: str) -> bool:
    """
    Retry a failed or dead letter job.

    Args:
        job_id: The job ID to retry

    Returns:
        bool: True if job was queued for retry, False if not found or not retryable
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Only allow retrying failed or dead letter jobs
        result = await conn.execute(
            """
            UPDATE fastjob_jobs
            SET status = 'queued', attempts = 0, last_error = NULL, updated_at = NOW()
            WHERE id = $1 AND status IN ('failed', 'dead_letter')
        """,
            uuid.UUID(job_id),
        )

        return result.split()[-1] == "1"


async def delete_job(job_id: str) -> bool:
    """
    Delete a job from the queue.

    Args:
        job_id: The job ID to delete

    Returns:
        bool: True if job was deleted, False if not found
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM fastjob_jobs WHERE id = $1
        """,
            uuid.UUID(job_id),
        )

        return result.split()[-1] == "1"


async def list_jobs(
    queue: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    List jobs with optional filtering.

    Args:
        queue: Filter by queue name
        status: Filter by status ('queued', 'done', 'failed', 'dead_letter', 'cancelled')
        limit: Maximum number of jobs to return
        offset: Number of jobs to skip

    Returns:
        List of job dictionaries
    """
    pool = await get_pool()

    # Build query with optional filters
    conditions = []
    params = []
    param_count = 0

    if queue:
        param_count += 1
        conditions.append(f"queue = ${param_count}")
        params.append(queue)

    if status:
        param_count += 1
        conditions.append(f"status = ${param_count}")
        params.append(status)

    where_clause = ""
    if conditions:
        where_clause = f"WHERE {' AND '.join(conditions)}"

    param_count += 1
    limit_param = f"${param_count}"
    params.append(limit)

    param_count += 1
    offset_param = f"${param_count}"
    params.append(offset)

    query = f"""
        SELECT id, job_name, args, status, attempts, max_attempts,
               queue, priority, scheduled_at, last_error,
               created_at, updated_at
        FROM fastjob_jobs
        {where_clause}
        ORDER BY created_at DESC
        LIMIT {limit_param} OFFSET {offset_param}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

        return [
            {
                "id": str(row["id"]),
                "job_name": row["job_name"],
                "args": json.loads(row["args"]),
                "status": row["status"],
                "attempts": row["attempts"],
                "max_attempts": row["max_attempts"],
                "queue": row["queue"],
                "priority": row["priority"],
                "scheduled_at": (
                    row["scheduled_at"].isoformat() if row["scheduled_at"] else None
                ),
                "last_error": row["last_error"],
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat(),
            }
            for row in rows
        ]


async def get_queue_stats() -> List[Dict[str, Any]]:
    """
    Get statistics for all queues.

    Returns:
        List of dictionaries with queue statistics
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                queue,
                COUNT(*) as total_jobs,
                COUNT(*) FILTER (WHERE status = 'queued') as queued,
                COUNT(*) FILTER (WHERE status = 'done') as done,
                COUNT(*) FILTER (WHERE status = 'failed') as failed,
                COUNT(*) FILTER (WHERE status = 'dead_letter') as dead_letter,
                COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled
            FROM fastjob_jobs
            GROUP BY queue
            ORDER BY queue
        """
        )

        return [
            {
                "queue": row["queue"],
                "total_jobs": row["total_jobs"],
                "queued": row["queued"],
                "done": row["done"],
                "failed": row["failed"],
                "dead_letter": row["dead_letter"],
                "cancelled": row["cancelled"],
            }
            for row in rows
        ]


async def schedule(
    job_func: Callable[..., Any],
    when: Optional[Union[datetime, timedelta, int, float]] = None,
    *,
    run_at: Optional[datetime] = None,
    run_in: Optional[Union[int, float, timedelta]] = None,
    **kwargs,
) -> str:
    """
    Schedule a job to run at a specific time or after a delay.

    Args:
        job_func: The job function to schedule
        when: When to run the job (positional argument). Can be:
            - datetime: Run at specific time
            - timedelta: Run after delay from now
            - int/float: Run after N seconds from now
        run_at: Schedule job at specific datetime (keyword argument)
        run_in: Schedule job after delay (keyword argument)
        **kwargs: Arguments to pass to the job function

    Returns:
        str: The job ID

    Examples:
        # Schedule at specific datetime (positional)
        await schedule(my_job, datetime(2025, 1, 15, 9, 0))

        # Schedule in 30 seconds (positional)
        await schedule(my_job, 30)

        # Schedule in 2 hours using timedelta (positional)
        await schedule(my_job, timedelta(hours=2))

        # Using keyword arguments
        await schedule(my_job, run_at=datetime(2025, 1, 15, 9, 0))
        await schedule(my_job, run_in=30)
    """
    # Handle positional 'when' parameter
    if when is not None:
        if run_at is not None or run_in is not None:
            raise ValueError("Cannot use 'when' parameter with 'run_at' or 'run_in'")

        if isinstance(when, datetime):
            scheduled_time = when
        elif isinstance(when, (int, float)):
            scheduled_time = datetime.now() + timedelta(seconds=when)
        elif isinstance(when, timedelta):
            scheduled_time = datetime.now() + when
        else:
            raise ValueError(
                f"Invalid 'when' parameter: {type(when)}. Must be datetime, timedelta, or int/float"
            )
    else:
        # Use keyword arguments
        if run_at is not None and run_in is not None:
            raise ValueError("Cannot specify both 'run_at' and 'run_in' - use only one")

        if run_at is None and run_in is None:
            raise ValueError("Must specify either 'when', 'run_at', or 'run_in'")

        if run_at is not None:
            scheduled_time = run_at
        else:
            if isinstance(run_in, (int, float)):
                scheduled_time = datetime.now() + timedelta(seconds=run_in)
            elif isinstance(run_in, timedelta):
                scheduled_time = datetime.now() + run_in
            else:
                raise ValueError(
                    f"Invalid 'run_in' parameter: {type(run_in)}. Must be int/float (seconds) or timedelta"
                )

    return await enqueue(job_func, scheduled_at=scheduled_time, **kwargs)
