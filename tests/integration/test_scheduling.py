"""
Test suite for job scheduling functionality
"""

import pytest
import asyncio
import uuid
from datetime import datetime, timedelta
from pydantic import BaseModel

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
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Enqueue immediate job
        immediate_job_id = await fastjob.enqueue(scheduled_job, message="immediate")
        
        # Enqueue job scheduled for future
        future_time = datetime.now() + timedelta(hours=1)
        scheduled_job_id = await fastjob.enqueue(
            scheduled_job, 
            scheduled_at=future_time,
            message="future"
        )
        
        # Process jobs - only immediate should run
        async with pool.acquire() as conn:
            processed = await process_jobs(conn)
            assert processed is True  # Immediate job processed
            
            processed = await process_jobs(conn) 
            assert processed is False  # No more jobs to process
        
        # Check statuses
        async with pool.acquire() as conn:
            immediate_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", 
                uuid.UUID(immediate_job_id)
            )
            scheduled_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", 
                uuid.UUID(scheduled_job_id)
            )
            
            assert immediate_record["status"] == "done"
            assert scheduled_record["status"] == "queued"  # Still waiting
        
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_priority_ordering():
    """Test that higher priority jobs (lower numbers) are processed first"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Enqueue jobs with different priorities
        low_priority = await fastjob.enqueue(scheduled_job, priority=100, message="low")
        high_priority = await fastjob.enqueue(scheduled_job, priority=1, message="high") 
        medium_priority = await fastjob.enqueue(scheduled_job, priority=50, message="medium")
        
        # Process one job at a time and verify order
        processing_order = []
        
        async with pool.acquire() as conn:
            for _ in range(3):
                # Get next job to be processed (without processing it)
                next_job = await conn.fetchrow("""
                    SELECT id, priority FROM fastjob_jobs
                    WHERE status = 'queued'
                    ORDER BY priority ASC, created_at ASC
                    LIMIT 1
                """)
                processing_order.append(next_job["priority"])
                
                # Process the job
                await process_jobs(conn)
        
        # Verify jobs were processed in priority order
        assert processing_order == [1, 50, 100]  # High to low priority
        
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_queue_isolation():
    """Test that jobs in different queues are isolated"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Enqueue jobs in different queues
        default_job = await fastjob.enqueue(scheduled_job, message="default queue")
        urgent_job = await fastjob.enqueue(scheduled_job, queue="urgent", message="urgent queue")
        
        # Process only default queue
        async with pool.acquire() as conn:
            processed = await process_jobs(conn, queue="default")
            assert processed is True
            
            # Try to process default queue again
            processed = await process_jobs(conn, queue="default") 
            assert processed is False  # No more jobs in default queue
            
            # Urgent queue should still have jobs
            processed = await process_jobs(conn, queue="urgent")
            assert processed is True
        
        # Verify statuses
        async with pool.acquire() as conn:
            default_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", 
                uuid.UUID(default_job)
            )
            urgent_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", 
                uuid.UUID(urgent_job)
            )
            
            assert default_record["status"] == "done"
            assert urgent_record["status"] == "done"
        
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio 
async def test_schedule_in_and_schedule_at():
    """Test convenience scheduling functions"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Test schedule_at
        future_time = datetime.now() + timedelta(minutes=30)
        at_job_id = await fastjob.schedule_at(
            scheduled_job, 
            future_time, 
            message="scheduled at specific time"
        )
        
        # Test schedule_in (seconds)
        in_job_id = await fastjob.schedule_in(
            scheduled_job,
            1800,  # 30 minutes in seconds
            message="scheduled in 30 minutes"
        )
        
        # Verify both jobs are scheduled correctly
        async with pool.acquire() as conn:
            at_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", 
                uuid.UUID(at_job_id)
            )
            in_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", 
                uuid.UUID(in_job_id)
            )
            
            assert at_record["scheduled_at"] is not None
            assert in_record["scheduled_at"] is not None
            assert at_record["status"] == "queued"
            assert in_record["status"] == "queued"
        
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_unified_schedule_function():
    """Test the new unified schedule() function with different time formats"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Test with datetime object
        future_datetime = datetime.now() + timedelta(minutes=15)
        datetime_job_id = await fastjob.schedule(
            scheduled_job,
            future_datetime,
            message="scheduled with datetime"
        )
        
        # Test with integer seconds
        seconds_job_id = await fastjob.schedule(
            scheduled_job,
            900,  # 15 minutes in seconds
            message="scheduled with seconds"
        )
        
        # Test with float seconds
        float_job_id = await fastjob.schedule(
            scheduled_job,
            900.5,  # 15 minutes and 0.5 seconds
            message="scheduled with float seconds"
        )
        
        # Test with timedelta object
        timedelta_job_id = await fastjob.schedule(
            scheduled_job,
            timedelta(minutes=15),
            message="scheduled with timedelta"
        )
        
        # Verify all jobs are scheduled correctly
        async with pool.acquire() as conn:
            datetime_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", 
                uuid.UUID(datetime_job_id)
            )
            seconds_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", 
                uuid.UUID(seconds_job_id)
            )
            float_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", 
                uuid.UUID(float_job_id)
            )
            timedelta_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", 
                uuid.UUID(timedelta_job_id)
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
            
            # Check that scheduling times are reasonable (within a few seconds of expected)
            now = datetime.now()
            expected_time = now + timedelta(minutes=15)
            
            # For datetime scheduling, time should be exactly what we specified
            assert abs((datetime_record["scheduled_at"] - future_datetime).total_seconds()) < 1
            
            # For seconds and timedelta scheduling, should be close to expected time
            assert abs((seconds_record["scheduled_at"] - expected_time).total_seconds()) < 10
            assert abs((timedelta_record["scheduled_at"] - expected_time).total_seconds()) < 10
            
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_schedule_invalid_input():
    """Test that schedule() raises appropriate errors for invalid input"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Test invalid input type
        with pytest.raises(ValueError, match="Invalid 'when' parameter"):
            await fastjob.schedule(scheduled_job, "invalid_string")
            
        with pytest.raises(ValueError, match="Invalid 'when' parameter"):
            await fastjob.schedule(scheduled_job, [1, 2, 3])
            
        with pytest.raises(ValueError, match="Invalid 'when' parameter"):
            await fastjob.schedule(scheduled_job, {"key": "value"})
        
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio 
async def test_backward_compatibility():
    """Test that schedule_at and schedule_in still work (backward compatibility)"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Test that old functions still work
        future_time = datetime.now() + timedelta(minutes=10)
        
        old_at_job = await fastjob.schedule_at(
            scheduled_job,
            future_time,
            message="using old schedule_at"
        )
        
        old_in_job = await fastjob.schedule_in(
            scheduled_job,
            600,  # 10 minutes
            message="using old schedule_in"
        )
        
        # Compare with new function
        new_at_job = await fastjob.schedule(
            scheduled_job,
            future_time,
            message="using new schedule with datetime"
        )
        
        new_in_job = await fastjob.schedule(
            scheduled_job,
            600,
            message="using new schedule with seconds"
        )
        
        # All should be scheduled successfully
        assert old_at_job is not None
        assert old_in_job is not None
        assert new_at_job is not None
        assert new_in_job is not None
        
        # Verify all jobs exist in database
        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM fastjob_jobs WHERE status = 'queued'")
            assert count == 4
        
    finally:
        await close_pool()
        await drop_test_database()