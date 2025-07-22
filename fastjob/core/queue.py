"""
Job queue operations - the heart of FastJob

This handles everything related to putting jobs in the queue and managing them.
The goal is to make it feel natural and reliable for developers.
"""

import json
import uuid
from typing import Callable, Any, Optional, Dict, List, Union
from datetime import datetime, timedelta

from pydantic import ValidationError

from fastjob.core.registry import get_job
from fastjob.db.connection import get_pool


async def enqueue(
    job_func: Callable[..., Any], 
    priority: Optional[int] = None,
    queue: Optional[str] = None,
    scheduled_at: Optional[datetime] = None,
    unique: Optional[bool] = None,
    **kwargs
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
    job_name = f"{job_func.__module__}.{job_func.__name__}"
    job_meta = get_job(job_name)
    if not job_meta:
        raise ValueError(f"Job {job_name} not registered.")

    # Validate arguments if model is specified
    args_model = job_meta.get("args_model")
    if args_model:
        try:
            args_model(**kwargs)  # Validate arguments
        except ValidationError as e:
            raise ValueError(f"Invalid arguments for job {job_name}: {e}") from e

    # Figure out the final settings - use what the caller specified, otherwise use job defaults
    final_priority = priority if priority is not None else job_meta["priority"]
    final_queue = queue if queue is not None else job_meta["queue"]
    final_unique = unique if unique is not None else job_meta["unique"]
    
    # Normalize scheduled_at to be timezone-naive in UTC if it's timezone-aware
    if scheduled_at and scheduled_at.tzinfo is not None:
        scheduled_at = scheduled_at.utctimetuple()
        from datetime import datetime
        scheduled_at = datetime(*scheduled_at[:6])
    
    job_id = str(uuid.uuid4())
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        # For unique jobs, check if we already have this exact job queued
        if final_unique:
            existing_job = await conn.fetchrow("""
                SELECT id FROM fastjob_jobs 
                WHERE job_name = $1 AND args = $2 AND status = 'queued'
            """, job_name, json.dumps(kwargs))
            
            if existing_job:
                return str(existing_job["id"])  # Return the existing job ID instead of creating a duplicate
        
        try:
            await conn.execute("""
                INSERT INTO fastjob_jobs (id, job_name, args, max_attempts, priority, queue, scheduled_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, uuid.UUID(job_id), job_name, json.dumps(kwargs), job_meta["retries"], 
            final_priority, final_queue, scheduled_at)
            
            # Notify workers about the new job for instant processing
            await conn.execute(f"NOTIFY fastjob_new_job, '{final_queue}'")
            
        except Exception as e:
            # Sometimes the database unique constraint catches duplicates we missed
            if final_unique and "duplicate key value violates unique constraint" in str(e):
                # Let's find the job that beat us to it
                existing_job = await conn.fetchrow("""
                    SELECT id FROM fastjob_jobs 
                    WHERE job_name = $1 AND args = $2 AND status = 'queued'
                """, job_name, json.dumps(kwargs))
                
                if existing_job:
                    return str(existing_job["id"])
            
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
        row = await conn.fetchrow("""
            SELECT id, job_name, args, status, attempts, max_attempts, 
                   queue, priority, scheduled_at, last_error, 
                   created_at, updated_at
            FROM fastjob_jobs 
            WHERE id = $1
        """, uuid.UUID(job_id))
        
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
            "scheduled_at": row["scheduled_at"].isoformat() if row["scheduled_at"] else None,
            "last_error": row["last_error"],
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat()
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
        result = await conn.execute("""
            UPDATE fastjob_jobs 
            SET status = 'cancelled', updated_at = NOW()
            WHERE id = $1 AND status = 'queued'
        """, uuid.UUID(job_id))
        
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
        result = await conn.execute("""
            UPDATE fastjob_jobs 
            SET status = 'queued', attempts = 0, last_error = NULL, updated_at = NOW()
            WHERE id = $1 AND status IN ('failed', 'dead_letter')
        """, uuid.UUID(job_id))
        
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
        result = await conn.execute("""
            DELETE FROM fastjob_jobs WHERE id = $1
        """, uuid.UUID(job_id))
        
        return result.split()[-1] == "1"


async def list_jobs(
    queue: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
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
                "scheduled_at": row["scheduled_at"].isoformat() if row["scheduled_at"] else None,
                "last_error": row["last_error"],
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat()
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
        rows = await conn.fetch("""
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
        """)
        
        return [
            {
                "queue": row["queue"],
                "total_jobs": row["total_jobs"],
                "queued": row["queued"],
                "done": row["done"],
                "failed": row["failed"],
                "dead_letter": row["dead_letter"],
                "cancelled": row["cancelled"]
            }
            for row in rows
        ]


async def schedule(
    job_func: Callable[..., Any], 
    *,
    run_at: Optional[datetime] = None,
    run_in: Optional[Union[int, float, timedelta]] = None,
    **kwargs
) -> str:
    """
    Schedule a job to run at a specific time or after a delay.
    
    Args:
        job_func: The job function to schedule
        run_at: Schedule job at specific datetime (mutually exclusive with run_in)
        run_in: Schedule job after delay. Can be:
            - int/float: Delay in seconds from now
            - timedelta: Delay from now
        **kwargs: Arguments to pass to the job function
        
    Returns:
        str: The job ID
        
    Examples:
        # Schedule at specific datetime
        await schedule(my_job, run_at=datetime(2024, 1, 15, 9, 0))
        
        # Schedule in 30 seconds
        await schedule(my_job, run_in=30)
        
        # Schedule in 2 hours using timedelta
        await schedule(my_job, run_in=timedelta(hours=2))
    """
    # Validate arguments
    if run_at is not None and run_in is not None:
        raise ValueError("Cannot specify both 'run_at' and 'run_in' - use only one")
    
    if run_at is None and run_in is None:
        raise ValueError("Must specify either 'run_at' or 'run_in'")
    
    if run_at is not None:
        # Schedule at specific datetime
        scheduled_time = run_at
    else:
        # Schedule after delay (run_in)
        if isinstance(run_in, (int, float)):
            # Number of seconds - schedule after delay
            scheduled_time = datetime.now() + timedelta(seconds=run_in)
        elif isinstance(run_in, timedelta):
            # Timedelta - schedule after delay
            scheduled_time = datetime.now() + run_in
        else:
            raise ValueError(f"Invalid 'run_in' parameter: {type(run_in)}. Must be int/float (seconds) or timedelta")
    
    return await enqueue(job_func, scheduled_at=scheduled_time, **kwargs)


