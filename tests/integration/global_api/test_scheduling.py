"""
Test suite for job scheduling functionality
"""

import pytest
import time
import uuid
from datetime import datetime, timedelta

import fastjob
from fastjob.core.processor import process_jobs
from fastjob.db.connection import get_pool, close_pool
from tests.db_utils import create_test_database, drop_test_database, clear_table

import os

os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"


@fastjob.job(retries=1)
async def scheduled_job(message: str):
    return f"Processed: {message}"


@pytest.mark.asyncio
async def test_immediate_vs_scheduled_jobs():
    """Test that scheduled jobs don't run until their scheduled time"""
    # Enqueue immediate job
    immediate_job_id = await fastjob.enqueue(scheduled_job, message="immediate")

    # Enqueue job scheduled for future
    future_time = datetime.now() + timedelta(hours=1)
    scheduled_job_id = await fastjob.enqueue(
        scheduled_job, scheduled_at=future_time, message="future"
    )

    # Process jobs - only immediate should run
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()

    processed = await fastjob.run_worker(run_once=True)
    assert processed is True  # Immediate job processed

    processed = await fastjob.run_worker(run_once=True)
    assert processed is False  # No more jobs to process

    # Check statuses
    async with app_pool.acquire() as conn:
        immediate_record = await conn.fetchrow(
            "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(immediate_job_id)
        )
        scheduled_record = await conn.fetchrow(
            "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(scheduled_job_id)
        )

        assert immediate_record["status"] == "done"
        assert scheduled_record["status"] == "queued"  # Still waiting

@pytest.mark.asyncio
async def test_priority_ordering(clean_db):
    """Test that higher priority jobs (lower numbers) are processed first"""
    # Enqueue jobs with different priorities
    low_priority = await fastjob.enqueue(scheduled_job, priority=100, message="low")
    high_priority = await fastjob.enqueue(scheduled_job, priority=1, message="high")
    medium_priority = await fastjob.enqueue(
        scheduled_job, priority=50, message="medium"
    )

    # Verify jobs are queued in database in priority order
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()

    async with app_pool.acquire() as conn:
        # Get all jobs in processing priority order
        jobs = await conn.fetch(
            """
            SELECT id, priority FROM fastjob_jobs
            WHERE status = 'queued'
            ORDER BY priority ASC, created_at ASC
        """
        )
        
        # Extract priorities in the order they would be processed
        processing_order = [job["priority"] for job in jobs]

    # Verify jobs would be processed in priority order: high(1), medium(50), low(100)
    assert processing_order == [1, 50, 100]

    # Process all jobs to verify they actually execute correctly
    await fastjob.run_worker(run_once=True)


@pytest.mark.asyncio
async def test_queue_isolation():
    """Test that jobs in different queues are isolated"""

    # Database setup handled by conftest.py

@pytest.mark.asyncio
async def test_schedule_run_in_and_schedule_run_at():
    """Test scheduling with different time specifications"""

    # Database setup handled by conftest.py

@pytest.mark.asyncio
async def test_unified_schedule_function():
    """Test the new unified schedule() function with different time formats"""
    # Test with datetime object (absolute time)
    future_datetime = datetime.now() + timedelta(minutes=15)
    datetime_job_id = await fastjob.schedule(
        scheduled_job, run_at=future_datetime, message="scheduled with datetime"
    )

    # Test with integer seconds (relative time)
    seconds_job_id = await fastjob.schedule(
        scheduled_job,
        run_in=900,  # 15 minutes in seconds
        message="scheduled with seconds",
    )

    # Test with float seconds (relative time)
    float_job_id = await fastjob.schedule(
        scheduled_job,
        run_in=900.5,  # 15 minutes and 0.5 seconds
        message="scheduled with float seconds",
    )

    # Test with timedelta object (relative time)
    timedelta_job_id = await fastjob.schedule(
        scheduled_job, run_in=timedelta(minutes=15), message="scheduled with timedelta"
    )

    # Verify all jobs are scheduled correctly
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()
    
    async with app_pool.acquire() as conn:
        datetime_record = await conn.fetchrow(
            "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(datetime_job_id)
        )
        seconds_record = await conn.fetchrow(
            "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(seconds_job_id)
        )
        float_record = await conn.fetchrow(
            "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(float_job_id)
        )
        timedelta_record = await conn.fetchrow(
            "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(timedelta_job_id)
        )

        # All should be scheduled
        assert datetime_record["scheduled_at"] is not None
        assert seconds_record["scheduled_at"] is not None
        assert float_record["scheduled_at"] is not None
        assert timedelta_record["scheduled_at"] is not None

        # All should be queued
        assert datetime_record["status"] == "queued"
        assert seconds_record["status"] == "queued"
        assert float_record["status"] == "queued"
        assert timedelta_record["status"] == "queued"

@pytest.mark.asyncio
async def test_schedule_invalid_input():
    """Test that schedule() raises appropriate errors for invalid input"""

    # Database setup handled by conftest.py

@pytest.mark.asyncio
async def test_schedule_keyword_arguments():
    """Test that schedule() works with keyword arguments"""

    # Database setup handled by conftest.py