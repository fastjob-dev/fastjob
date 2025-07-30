"""
Test Corrupted Job Data Handling

Tests graceful handling of corrupted JSON, validation errors, and argument mismatches
to ensure system robustness in production environments.
"""

import os
import json
import uuid
import unittest.mock
import json as json_module

import pytest
from pydantic import BaseModel

# Ensure we're using test database
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"

import fastjob
from fastjob.db.connection import get_pool


class JobArgsModel(BaseModel):
    message: str
    count: int = 1


# Register test jobs at module level
@fastjob.job(args_model=JobArgsModel)
async def validated_test_job(message: str, count: int = 1):
    """Test job with Pydantic validation"""
    return f"processed: {message} x{count}"


@fastjob.job()
async def simple_test_job(message: str):
    """Simple test job without validation"""
    return f"processed: {message}"


@pytest.fixture
async def clean_db():
    """Clean database before each test"""
    from tests.db_utils import clear_table
    from fastjob.core.discovery import discover_jobs

    # Ensure jobs are registered
    discover_jobs()

    pool = await get_pool()
    await clear_table(pool)
    yield
    await clear_table(pool)


@pytest.mark.asyncio
async def test_corrupted_json_data(clean_db):
    """Test handling of corrupted JSON in job args using mock approach"""
    from fastjob.core import processor

    # Use global app pool for consistency
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()

    # Insert valid JSON job first
    job_id = uuid.uuid4()
    async with app_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fastjob_jobs (id, job_name, args, queue, status, max_attempts)
            VALUES ($1, $2, $3, 'test', 'queued', 3)
            """,
            job_id,
            "tests.integration.global_api.test_corrupted_data_handling.simple_test_job",
            json.dumps({"message": "test"}),
        )

    # Mock json.loads to simulate corruption for this specific test
    original_loads = json_module.loads

    def mock_loads(s, *args, **kwargs):
        if isinstance(s, str) and "test" in s:
            raise json_module.JSONDecodeError("Simulated corruption", s, 0)
        return original_loads(s, *args, **kwargs)

    with unittest.mock.patch.object(processor, "json") as mock_json:
        mock_json.loads = mock_loads
        # Process the job
        async with app_pool.acquire() as conn:
            processed = await fastjob.run_worker(run_once=True, queues=["test"])

    assert processed  # Job should be processed (moved to dead letter)

    # Verify job was moved to dead letter
    async with app_pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] == "dead_letter"
        assert "Corrupted JSON data" in job["last_error"]
        assert job["attempts"] == 3  # Set to max attempts


@pytest.mark.asyncio
async def test_corrupted_validation_data(clean_db):
    """Test handling of data that fails Pydantic validation"""
    # Use global app pool for consistency
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()

    # Insert job with data that fails validation
    job_id = uuid.uuid4()
    async with app_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fastjob_jobs (id, job_name, args, queue, status, max_attempts)
            VALUES ($1, $2, $3, 'test', 'queued', 3)
            """,
            job_id,
            "tests.integration.global_api.test_corrupted_data_handling.validated_test_job",
            json.dumps({"message": 123, "count": "not_a_number"}),  # Wrong types
        )

    # Process the job
    async with app_pool.acquire() as conn:
        processed = await fastjob.run_worker(run_once=True, queues=["test"])

    assert processed  # Job should be processed (moved to dead letter)

    # Verify job was moved to dead letter
    async with app_pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] == "dead_letter"
        assert "Corrupted argument data" in job["last_error"]
        assert job["attempts"] == 3  # Set to max attempts


@pytest.mark.asyncio
async def test_missing_required_arguments(clean_db):
    """Test handling of missing required function arguments"""
    # Use global app pool for consistency
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()

    # Insert job with missing required arguments
    job_id = uuid.uuid4()
    async with app_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fastjob_jobs (id, job_name, args, queue, status, max_attempts)
            VALUES ($1, $2, $3, 'test', 'queued', 3)
            """,
            job_id,
            "tests.integration.global_api.test_corrupted_data_handling.simple_test_job",
            json.dumps({}),  # Missing required 'message' argument
        )

    # Process the job
    async with app_pool.acquire() as conn:
        processed = await fastjob.run_worker(run_once=True, queues=["test"])

    assert processed  # Job should be processed (moved to dead letter)

    # Verify job was moved to dead letter
    async with app_pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] == "dead_letter"
        assert "Function argument mismatch" in job["last_error"]
        assert job["attempts"] == 3  # Set to max attempts


@pytest.mark.asyncio
async def test_extra_unexpected_arguments(clean_db):
    """Test handling of extra unexpected function arguments"""
    # Use global app pool for consistency
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()

    # Insert job with extra unexpected arguments
    job_id = uuid.uuid4()
    async with app_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fastjob_jobs (id, job_name, args, queue, status, max_attempts)
            VALUES ($1, $2, $3, 'test', 'queued', 3)
            """,
            job_id,
            "tests.integration.global_api.test_corrupted_data_handling.simple_test_job",
            json.dumps(
                {
                    "message": "test",
                    "unexpected_arg": "value",
                    "another_unexpected": 123,
                }
            ),
        )

    # Process the job
    async with app_pool.acquire() as conn:
        processed = await fastjob.run_worker(run_once=True, queues=["test"])

    assert processed  # Job should be processed (moved to dead letter)

    # Verify job was moved to dead letter
    async with app_pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] == "dead_letter"
        assert "Function argument mismatch" in job["last_error"]
        assert job["attempts"] == 3  # Set to max attempts


@pytest.mark.asyncio
async def test_invalid_json_structure(clean_db):
    """Test handling of JSON with invalid structure"""
    # Use global app pool for consistency
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()

    # Insert job with valid JSON but that will cause parsing issues
    job_id = uuid.uuid4()
    async with app_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fastjob_jobs (id, job_name, args, queue, status, max_attempts)
            VALUES ($1, $2, $3, 'test', 'queued', 3)
            """,
            job_id,
            "tests.integration.global_api.test_corrupted_data_handling.simple_test_job",
            '"just a string not an object"',  # Valid JSON but not an object
        )

    # Process the job
    async with app_pool.acquire() as conn:
        processed = await fastjob.run_worker(run_once=True, queues=["test"])

    assert processed  # Job should be processed (moved to dead letter)

    # Verify job was moved to dead letter
    async with app_pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] == "dead_letter"
        # This might show up as argument mismatch rather than JSON corruption
        assert "Corrupted" in job["last_error"] or "argument" in job["last_error"]


@pytest.mark.asyncio
async def test_valid_job_still_processes_normally(clean_db):
    """Test that valid jobs are not affected by corruption handling"""
    # Use global app pool for consistency
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()

    # Enqueue a valid job
    job_id = await fastjob.enqueue(simple_test_job, message="valid_test")

    # Process the job
    async with app_pool.acquire() as conn:
        processed = await fastjob.run_worker(run_once=True, queues=["default"])

    assert processed  # Job should be processed successfully

    # Verify job completed successfully
    async with app_pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] in ["done", None]  # Either done or deleted (TTL=0)


@pytest.mark.asyncio
async def test_pydantic_validation_success(clean_db):
    """Test that Pydantic validation works for valid data"""
    # Use global app pool for consistency
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()

    # Debug: Check job registration
    print(f"Job function: {validated_test_job}")
    print(f"Job name: {validated_test_job._fastjob_name}")
    
    # Debug: Check global app database configuration
    global_app = fastjob._get_global_app()
    print(f"Global app database URL: {global_app.settings.database_url}")
    print("Test pool database from get_pool(): Expected test database")
    
    # Enqueue a valid job with Pydantic validation
    try:
        job_id = await fastjob.enqueue(validated_test_job, message="valid", count=5)
        print(f"Enqueued job ID: {job_id}")
    except Exception as e:
        print(f"Enqueue failed: {e}")
        import traceback
        traceback.print_exc()
        raise

    # Debug: Check database state from test pool
    async with app_pool.acquire() as conn:
        jobs = await conn.fetch("SELECT job_name, status FROM fastjob_jobs")
        print(f"Jobs in test database pool: {[dict(job) for job in jobs]}")
    
    # Debug: Check database state from global app pool
    global_app = fastjob._get_global_app()
    await global_app._ensure_initialized()
    async with global_app._pool.acquire() as conn:
        jobs_global = await conn.fetch("SELECT job_name, status FROM fastjob_jobs")
        print(f"Jobs in global app pool: {[dict(job) for job in jobs_global]}")
        
    # Debug: Check registry lookup
    if jobs:
        db_job_name = jobs[0]['job_name']
        from fastjob.core.registry import get_job
        job_meta = get_job(db_job_name)
        print(f"Job lookup for '{db_job_name}': {job_meta is not None}")
        
        if not job_meta:
            # Check both registries
            from fastjob.core.registry import _global_registry
            print(f"Global registry keys: {list(_global_registry._registry.keys())}")
            
            try:
                global_app = fastjob._get_global_app()
                app_registry = global_app.get_job_registry()
                print(f"App registry keys: {list(app_registry._registry.keys())}")
            except Exception as e:
                print(f"Error getting app registry: {e}")

    # Process the job
    async with app_pool.acquire() as conn:
        processed = await fastjob.run_worker(run_once=True, queues=["default"])
        print(f"Job processed: {processed}")

    assert processed  # Job should be processed successfully

    # Verify job completed successfully
    async with app_pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] in ["done", None]  # Either done or deleted (TTL=0)


@pytest.mark.asyncio
async def test_regular_job_exceptions_still_retry(clean_db):
    """Test that regular job exceptions still trigger retry logic"""

    @fastjob.job(retries=0)  # retries=0 means max_attempts=1
    async def failing_job(should_fail: bool = True):
        if should_fail:
            raise ValueError("Intentional failure for testing")
        return "success"

    # Use global app pool for consistency
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()

    # Enqueue a job that will fail (with retries=0 so max_attempts=1)
    job_id = await fastjob.enqueue(failing_job, should_fail=True)

    # Process the job (should fail and go to dead letter after 1 attempt)
    async with app_pool.acquire() as conn:
        processed = await fastjob.run_worker(run_once=True, queues=["default"])

    assert processed  # Job should be processed

    # With retries=0, job goes directly to dead letter after first failure
    async with app_pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] == "dead_letter"  # Should be in dead letter after max attempts
        assert job["attempts"] == 1  # Single attempt made
        assert "Intentional failure" in job["last_error"]


@pytest.mark.asyncio
async def test_mixed_corrupted_and_valid_jobs(clean_db):
    """Test processing queue with mix of corrupted and valid jobs"""
    # Use global app pool for consistency
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()

    # Insert corrupted job (use validation corruption instead of JSON corruption)
    corrupted_job_id = uuid.uuid4()
    async with app_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fastjob_jobs (id, job_name, args, queue, status, max_attempts)
            VALUES ($1, $2, $3, 'mixed', 'queued', 3)
            """,
            corrupted_job_id,
            "tests.integration.global_api.test_corrupted_data_handling.validated_test_job",
            json.dumps({"message": 123, "count": "not_a_number"}),  # Wrong types
        )

    # Enqueue valid job
    valid_job_id = await fastjob.enqueue(
        simple_test_job, message="valid", queue="mixed"
    )

    # Process jobs with run_once=True (processes all available jobs in single run)
    async with app_pool.acquire() as conn:
        processed = await fastjob.run_worker(run_once=True, queues=["mixed"])

    assert processed  # Jobs should be processed

    # Check corrupted job is in dead letter
    async with app_pool.acquire() as conn:
        corrupted_job = await conn.fetchrow(
            "SELECT * FROM fastjob_jobs WHERE id = $1", corrupted_job_id
        )
        assert corrupted_job["status"] == "dead_letter"

        # Check valid job completed
        valid_job = await conn.fetchrow(
            "SELECT * FROM fastjob_jobs WHERE id = $1", valid_job_id
        )
        assert valid_job["status"] in ["done", None]  # Either done or deleted (TTL=0)
