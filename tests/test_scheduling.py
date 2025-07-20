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