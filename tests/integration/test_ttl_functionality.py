"""
Test TTL (Time-To-Live) functionality for completed jobs

Tests that the result_ttl setting properly sets expires_at field
and that cleanup works correctly.
"""

import os
import time
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

# Ensure we're using test database
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"

import fastjob
from fastjob.db.connection import get_pool
from fastjob.settings import get_settings


@fastjob.job()
async def ttl_test_job(message: str):
    """Simple test job for TTL testing"""
    return f"processed: {message}"


@pytest.fixture
async def clean_db():
    """Clean database before each test"""
    from tests.db_utils import clear_table

    pool = await get_pool()
    await clear_table(pool)
    yield
    await clear_table(pool)


@pytest.mark.asyncio
async def test_ttl_zero_deletes_immediately(clean_db):
    """Test that TTL=0 deletes jobs immediately after completion"""
    # Set TTL to 0 for immediate deletion
    settings = get_settings()
    original_ttl = settings.result_ttl
    settings.result_ttl = 0

    try:
        # Enqueue a job
        job_id = await fastjob.enqueue(ttl_test_job, message="test_immediate_delete")

        # Process the job
        from fastjob.core.processor import process_jobs

        pool = await get_pool()
        async with pool.acquire() as conn:
            await process_jobs(conn)

        # Verify job was deleted immediately
        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", job_id
            )
            assert result is None, "Job should be deleted immediately when TTL=0"

    finally:
        # Restore original TTL
        settings.result_ttl = original_ttl


@pytest.mark.asyncio
async def test_ttl_positive_sets_expires_at(clean_db):
    """Test that positive TTL sets expires_at field correctly"""
    # Set TTL to 300 seconds (5 minutes)
    settings = get_settings()
    original_ttl = settings.result_ttl
    settings.result_ttl = 300

    try:
        # Enqueue a job
        job_id = await fastjob.enqueue(ttl_test_job, message="test_ttl_expiry")

        # Record time before processing
        before_processing = datetime.now(timezone.utc)

        # Process the job
        from fastjob.core.processor import process_jobs

        pool = await get_pool()
        async with pool.acquire() as conn:
            await process_jobs(conn)

        # Verify job exists with correct status and expires_at
        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT status, expires_at FROM fastjob_jobs WHERE id = $1", job_id
            )

            assert result is not None, "Job should exist after completion"
            assert result["status"] == "done", "Job should have status 'done'"
            assert result["expires_at"] is not None, "Job should have expires_at set"

            # Check that expires_at is approximately 300 seconds from now
            expires_at = result["expires_at"]
            # Convert to timezone-aware datetime for comparison
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            expected_expiry = before_processing + timedelta(seconds=300)

            # Allow for some processing time tolerance (±10 seconds)
            assert (
                abs((expires_at - expected_expiry).total_seconds()) < 10
            ), f"expires_at should be ~300s from processing time. Got {expires_at}, expected ~{expected_expiry}"

    finally:
        # Restore original TTL
        settings.result_ttl = original_ttl


@pytest.mark.asyncio
async def test_ttl_cleanup_removes_expired_jobs(clean_db):
    """Test that expired jobs are cleaned up correctly"""
    # Set a very short TTL for testing
    settings = get_settings()
    original_ttl = settings.result_ttl
    settings.result_ttl = 1  # 1 second TTL

    try:
        # Enqueue and process a job
        job_id = await fastjob.enqueue(ttl_test_job, message="test_cleanup")

        from fastjob.core.processor import process_jobs

        pool = await get_pool()
        async with pool.acquire() as conn:
            await process_jobs(conn)

        # Verify job exists initially
        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT status, expires_at FROM fastjob_jobs WHERE id = $1", job_id
            )
            assert result is not None, "Job should exist after completion"
            assert result["status"] == "done", "Job should have status 'done'"

        # Wait for expiration (1 second + small buffer)
        await asyncio.sleep(1.5)

        # Manually trigger cleanup
        async with pool.acquire() as conn:
            cleaned = await conn.execute(
                "DELETE FROM fastjob_jobs WHERE status = 'done' AND expires_at < NOW()"
            )
            # Extract count from result string like "DELETE 1"
            cleaned_count = (
                int(cleaned.split()[-1]) if cleaned.split()[-1].isdigit() else 0
            )

            assert (
                cleaned_count == 1
            ), f"Should have cleaned up 1 expired job, got {cleaned_count}"

        # Verify job was removed
        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", job_id
            )
            assert result is None, "Expired job should be deleted by cleanup"

    finally:
        # Restore original TTL
        settings.result_ttl = original_ttl


@pytest.mark.asyncio
async def test_ttl_failed_jobs_not_cleaned_up(clean_db):
    """Test that failed jobs are not cleaned up by TTL expiration"""
    settings = get_settings()
    original_ttl = settings.result_ttl
    settings.result_ttl = 1  # 1 second TTL

    try:
        # Create a failing job with no retries
        @fastjob.job(retries=0)
        async def failing_job():
            raise Exception("This job always fails")

        job_id = await fastjob.enqueue(failing_job)

        # Process the job (it will fail)
        from fastjob.core.processor import process_jobs

        pool = await get_pool()
        async with pool.acquire() as conn:
            await process_jobs(conn)

        # Verify job failed
        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT status FROM fastjob_jobs WHERE id = $1", job_id
            )
            assert result is not None, "Job should exist after failure"
            assert (
                result["status"] == "dead_letter"
            ), "Job should have status 'dead_letter'"

        # Wait past TTL expiration
        await asyncio.sleep(1.5)

        # Run cleanup
        async with pool.acquire() as conn:
            cleaned = await conn.execute(
                "DELETE FROM fastjob_jobs WHERE status = 'done' AND expires_at < NOW()"
            )
            cleaned_count = (
                int(cleaned.split()[-1]) if cleaned.split()[-1].isdigit() else 0
            )

            assert cleaned_count == 0, "Should not clean up failed jobs"

        # Verify failed job still exists
        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT status FROM fastjob_jobs WHERE id = $1", job_id
            )
            assert result is not None, "Failed job should still exist"
            assert (
                result["status"] == "dead_letter"
            ), "Failed job should remain in dead_letter status"

    finally:
        # Restore original TTL
        settings.result_ttl = original_ttl
