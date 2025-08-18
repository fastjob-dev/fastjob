"""
Test suite for FastJob core functionality
"""

import json
import logging
import os
import uuid

import pytest
from pydantic import BaseModel

import fastjob
from fastjob.core.registry import get_job
from fastjob.db.connection import close_pool
from tests.db_utils import create_test_database, drop_test_database

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)

# Set test database URL for all tests
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"


class SampleJobArgs(BaseModel):
    x: int
    y: int


_flaky_job_fail_counts = {}


@pytest.mark.asyncio
async def test_enqueue_and_run_job():
    """Test job enqueue and processing with instance-based architecture"""
    await create_test_database()

    try:
        # Create a FastJob instance for testing (not using global)
        app = fastjob.FastJob(
            database_url="postgresql://postgres@localhost/fastjob_test"
        )

        # Register job with the instance
        @app.job(retries=5, args_model=SampleJobArgs)
        async def instance_sample_job(x, y):
            return x + y

        # Clear test table using instance pool to ensure consistency
        instance_pool = await app.get_pool()
        async with instance_pool.acquire() as conn:
            await conn.execute("DELETE FROM fastjob_jobs")

        # Enqueue job using instance API
        job_id = await app.enqueue(instance_sample_job, x=1, y=2)
        assert job_id

        # Process the job using instance worker
        await app.run_worker(run_once=True)

        # Check job status using instance pool
        async with instance_pool.acquire() as conn:
            job_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id)
            )

            assert job_record is not None, f"Job {job_id} not found in database"
            assert (
                job_record["job_name"]
                == "tests.integration.instance_api.test_core.instance_sample_job"
            )
            assert json.loads(job_record["args"]) == {"x": 1, "y": 2}
            assert job_record["max_attempts"] == 6  # retries=5 -> max_attempts=6
            assert job_record["status"] == "done"

        # Clean up the instance
        await app.close()

    finally:
        await drop_test_database()


@pytest.mark.asyncio
async def test_enqueue_job_invalid_args():
    await create_test_database()
    try:
        # Configure global app to use test database
        fastjob.configure(database_url="postgresql://postgres@localhost/fastjob_test")

        # Define job with args validation
        @fastjob.job(retries=5, args_model=SampleJobArgs)
        async def sample_job(x, y):
            return x + y

        # Clear test table using global app pool
        global_app = fastjob._get_global_app()
        global_pool = await global_app.get_pool()
        async with global_pool.acquire() as conn:
            await conn.execute("DELETE FROM fastjob_jobs")

        with pytest.raises(ValueError, match="Invalid arguments for job"):
            await fastjob.enqueue(sample_job, x=1, y="invalid")

        # Clean up global app
        if global_app.is_initialized:
            await global_app.close()

    finally:
        await drop_test_database()


@pytest.mark.asyncio
async def test_retry_mechanism():
    global _flaky_job_fail_counts
    _flaky_job_fail_counts = {}  # Reset for this test

    await create_test_database()
    try:
        # Configure global app to use test database
        fastjob.configure(database_url="postgresql://postgres@localhost/fastjob_test")

        # Define flaky job that fails first 2 times then succeeds
        @fastjob.job(retries=3)
        async def flaky_job(job_id: str, should_fail: bool):
            if should_fail:
                _flaky_job_fail_counts[job_id] = (
                    _flaky_job_fail_counts.get(job_id, 0) + 1
                )
                if _flaky_job_fail_counts[job_id] <= 2:
                    raise ValueError("Simulated failure")
            return "Success"

        # Define job that always fails
        @fastjob.job(retries=3)
        async def always_fail_job(job_id: str):
            raise ValueError("Always fails")

        # Clear test table using global app pool
        global_app = fastjob._get_global_app()
        global_pool = await global_app.get_pool()
        async with global_pool.acquire() as conn:
            await conn.execute("DELETE FROM fastjob_jobs")

        # Test job that succeeds after retries
        job_id_1 = str(uuid.uuid4())
        actual_job_id_1 = await fastjob.enqueue(
            flaky_job, job_id=job_id_1, should_fail=True
        )

        # Process job using global worker (will retry until success or max attempts)
        await fastjob.run_worker(run_once=True)

        # Check final status - should have succeeded after 3 attempts (2 failures + 1 success)
        async with global_pool.acquire() as conn:
            job_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(actual_job_id_1)
            )
            assert job_record["status"] == "done"
            assert job_record["attempts"] == 2  # 2 failed attempts, then success

        # Test job that exceeds max retries
        job_id_2 = str(uuid.uuid4())
        actual_job_id_2 = await fastjob.enqueue(always_fail_job, job_id=job_id_2)

        # Process job using global worker (will retry until max attempts reached)
        await fastjob.run_worker(run_once=True)

        async with global_pool.acquire() as conn:
            job_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(actual_job_id_2)
            )
            assert job_record["status"] == "dead_letter"
            assert job_record["attempts"] == 4  # retries=3 means max_attempts=4
            assert "Always fails" in job_record["last_error"]

        # Clean up global app
        if global_app.is_initialized:
            await global_app.close()

    finally:
        await drop_test_database()


@pytest.mark.asyncio
async def test_embedded_worker():
    await create_test_database()
    try:
        # Configure global app to use test database
        fastjob.configure(database_url="postgresql://postgres@localhost/fastjob_test")

        # Define sample job
        @fastjob.job(retries=5, args_model=SampleJobArgs)
        async def sample_job(x, y):
            return x + y

        # Clear test table using global app pool
        global_app = fastjob._get_global_app()
        global_pool = await global_app.get_pool()
        async with global_pool.acquire() as conn:
            await conn.execute("DELETE FROM fastjob_jobs")

        # Enqueue job using global API
        job_id = await fastjob.enqueue(sample_job, x=10, y=20)

        # Process job using global worker
        await fastjob.run_worker(run_once=True)

        # Check job status using global pool
        async with global_pool.acquire() as conn:
            job_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id)
            )
            assert job_record["status"] == "done"

        # Clean up global app
        if global_app.is_initialized:
            await global_app.close()

    finally:
        await drop_test_database()


@pytest.mark.asyncio
async def test_cli_worker():
    # Test that CLI worker module can be imported and executed
    # This verifies the CLI structure is correct

    # Test importing the CLI main function
    from fastjob.cli.main import main

    assert main is not None

    # Test that we can access run_worker through global API (which uses FastJob instance)
    import fastjob

    assert fastjob.run_worker is not None
    
    # Test that FastJob instances have run_worker method
    from fastjob import FastJob
    app = FastJob(database_url="postgresql://postgres@localhost/fastjob_test")
    assert app.run_worker is not None


@pytest.mark.asyncio
async def test_task_discovery():
    await create_test_database()
    try:
        # Configure global app to use test database
        fastjob.configure(database_url="postgresql://postgres@localhost/fastjob_test")

        # Clear test table using global app pool
        global_app = fastjob._get_global_app()
        global_pool = await global_app.get_pool()
        async with global_pool.acquire() as conn:
            await conn.execute("DELETE FROM fastjob_jobs")

        # Temporarily set the environment variable for task discovery
        original_env = os.environ.copy()
        os.environ["FASTJOB_JOBS_MODULE"] = "jobs"

        # Import the discovery module to trigger discovery
        from fastjob.core.discovery import discover_jobs

        discover_jobs()

        # Verify that the discovered job is registered
        discovered_job_meta = get_job("jobs.my_tasks.discovered_job")
        assert discovered_job_meta is not None

        # Enqueue the discovered job using global API
        await fastjob.enqueue(
            discovered_job_meta["func"], message="Hello from discovered job!"
        )

        # Process using global worker
        await fastjob.run_worker(run_once=True)

        # Check job status using global pool
        async with global_pool.acquire() as conn:
            job_record = await conn.fetchrow(
                "SELECT * FROM fastjob_jobs WHERE job_name = 'jobs.my_tasks.discovered_job'"
            )
            assert job_record["status"] == "done"

        # Clean up global app
        global_app = fastjob._get_global_app()
        if global_app.is_initialized:
            await global_app.close()

    finally:
        # Restore original environment variables
        os.environ.clear()
        os.environ.update(original_env)
        await close_pool()
        await drop_test_database()
