"""
Test suite for FastJob core functionality
"""

import pytest
import json
import uuid
import asyncio
import os
import logging
from pydantic import BaseModel

from fastjob import job, enqueue, start_embedded_worker, stop_embedded_worker
from fastjob.core.processor import process_jobs
from fastjob.core.registry import get_job
from fastjob.db.connection import get_pool, close_pool
from tests.db_utils import create_test_database, drop_test_database, clear_table

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)

# Set test database URL for all tests

os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"


class SampleJobArgs(BaseModel):
    x: int
    y: int


_flaky_job_fail_counts = {}


@job(retries=5, args_model=SampleJobArgs)
async def sample_job(x, y):
    return x + y


@job(retries=3)
async def flaky_job(job_id: str, should_fail: bool):
    if should_fail:
        _flaky_job_fail_counts[job_id] = _flaky_job_fail_counts.get(job_id, 0) + 1
        if _flaky_job_fail_counts[job_id] <= 2:
            raise ValueError("Simulated failure")
    return "Success"


@job(retries=3)
async def always_fail_job(job_id: str):
    raise ValueError("Always fails")


@pytest.mark.asyncio
async def test_enqueue_and_run_job():

    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)

        # Enqueue job using new API
        job_id = await enqueue(sample_job, x=1, y=2)
        assert job_id

        # Process the job
        async with pool.acquire() as conn:
            processed = await process_jobs(conn)
            assert processed is True

        # Check job status
        async with pool.acquire() as conn:
            job_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id)
            )
            assert job_record["job_name"] == "tests.integration.test_core.sample_job"
            assert json.loads(job_record["args"]) == {"x": 1, "y": 2}
            assert job_record["max_attempts"] == 6  # retries=5 -> max_attempts=6
            assert job_record["status"] == "done"
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_enqueue_job_invalid_args():
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)

        with pytest.raises(ValueError, match="Invalid arguments for job"):
            await enqueue(sample_job, x=1, y="invalid")
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_retry_mechanism():
    global _flaky_job_fail_counts
    _flaky_job_fail_counts = {}  # Reset for this test

    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)

        # Test job that succeeds after retries
        job_id_1 = str(uuid.uuid4())
        actual_job_id_1 = await enqueue(flaky_job, job_id=job_id_1, should_fail=True)

        async with pool.acquire() as conn:
            # First attempt (should fail)
            processed = await process_jobs(conn)
            assert processed is True

            job_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(actual_job_id_1)
            )
            assert job_record["status"] == "queued"
            assert job_record["attempts"] == 1

            # Second attempt (should fail)
            processed = await process_jobs(conn)
            assert processed is True

            job_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(actual_job_id_1)
            )
            assert job_record["status"] == "queued"
            assert job_record["attempts"] == 2

            # Third attempt (should succeed)
            processed = await process_jobs(conn)
            assert processed is True

            job_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(actual_job_id_1)
            )
            assert job_record["status"] == "done"
            assert job_record["attempts"] == 2  # Attempts don't increment on success

        # Test job that exceeds max retries
        job_id_2 = str(uuid.uuid4())
        actual_job_id_2 = await enqueue(always_fail_job, job_id=job_id_2)

        async with pool.acquire() as conn:
            # Process 4 times (should fail permanently after 4th attempt, since retries=3 means max_attempts=4)
            for i in range(4):
                processed = await process_jobs(conn)
                assert processed is True

            job_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(actual_job_id_2)
            )
            assert job_record["status"] == "dead_letter"
            assert job_record["attempts"] == 4
            assert "Always fails" in job_record["last_error"]
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_embedded_worker():
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)

        # Enqueue job
        job_id = await enqueue(sample_job, x=10, y=20)

        # Start embedded worker
        start_embedded_worker()
        await asyncio.sleep(2)  # Give worker time to process
        await stop_embedded_worker()

        # Check job status
        async with pool.acquire() as conn:
            job_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id)
            )
            assert job_record["status"] == "done"
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_cli_worker():
    # Test that CLI worker module can be imported and executed
    # This verifies the CLI structure is correct

    # Test importing the CLI main function
    from fastjob.cli.main import main

    assert main is not None

    # Test that we can import the run_worker function
    from fastjob.core.processor import run_worker

    assert run_worker is not None


@pytest.mark.asyncio
async def test_task_discovery():

    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)

        # Temporarily set the environment variable for task discovery
        original_env = os.environ.copy()
        os.environ["FASTJOB_JOBS_MODULE"] = "jobs"

        # Import the discovery module to trigger discovery
        from fastjob.core.discovery import discover_jobs

        discover_jobs()

        # Verify that the discovered job is registered
        discovered_job_meta = get_job("jobs.my_tasks.discovered_job")
        assert discovered_job_meta is not None

        # Enqueue the discovered job
        job_id = await enqueue(
            discovered_job_meta["func"], message="Hello from discovered job!"
        )

        # Process using embedded worker
        start_embedded_worker()
        await asyncio.sleep(2)
        await stop_embedded_worker()

        # Check job status
        async with pool.acquire() as conn:
            job_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE job_name = 'jobs.my_tasks.discovered_job'"
            )
            assert job_record["status"] == "done"
    finally:
        # Restore original environment variables
        os.environ.clear()
        os.environ.update(original_env)
        await close_pool()
        await drop_test_database()
