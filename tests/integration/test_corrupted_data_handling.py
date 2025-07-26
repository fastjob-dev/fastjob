"""
Test Corrupted Job Data Handling

Tests graceful handling of corrupted JSON, validation errors, and argument mismatches
to ensure system robustness in production environments.
"""

import os
import json
import uuid
from typing import Optional

import pytest
from pydantic import BaseModel

# Ensure we're using test database
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"

import fastjob
from fastjob.db.connection import get_pool
from fastjob.core.processor import process_jobs


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
    import unittest.mock
    import json as json_module
    from fastjob.core import processor
    
    pool = await get_pool()
    
    # Insert valid JSON job first
    job_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fastjob_jobs (id, job_name, args, queue, status, max_attempts)
            VALUES ($1, $2, $3, 'test', 'queued', 3)
            """,
            job_id,
            "tests.integration.test_corrupted_data_handling.simple_test_job",
            json.dumps({"message": "test"})
        )
    
    # Mock json.loads to simulate corruption for this specific test
    original_loads = json_module.loads
    def mock_loads(s, *args, **kwargs):
        if isinstance(s, str) and "test" in s:
            raise json_module.JSONDecodeError("Simulated corruption", s, 0)
        return original_loads(s, *args, **kwargs)
    
    with unittest.mock.patch.object(processor, 'json') as mock_json:
        mock_json.loads = mock_loads
        # Process the job
        async with pool.acquire() as conn:
            processed = await process_jobs(conn, "test")
    
    assert processed  # Job should be processed (moved to dead letter)
    
    # Verify job was moved to dead letter
    async with pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] == "dead_letter"
        assert "Corrupted JSON data" in job["last_error"]
        assert job["attempts"] == 3  # Set to max attempts


@pytest.mark.asyncio
async def test_corrupted_validation_data(clean_db):
    """Test handling of data that fails Pydantic validation"""
    pool = await get_pool()
    
    # Insert job with data that fails validation
    job_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fastjob_jobs (id, job_name, args, queue, status, max_attempts)
            VALUES ($1, $2, $3, 'test', 'queued', 3)
            """,
            job_id,
            "tests.integration.test_corrupted_data_handling.validated_test_job",
            json.dumps({"message": 123, "count": "not_a_number"})  # Wrong types
        )
    
    # Process the job
    async with pool.acquire() as conn:
        processed = await process_jobs(conn, "test")
    
    assert processed  # Job should be processed (moved to dead letter)
    
    # Verify job was moved to dead letter
    async with pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] == "dead_letter"
        assert "Corrupted argument data" in job["last_error"]
        assert job["attempts"] == 3  # Set to max attempts


@pytest.mark.asyncio
async def test_missing_required_arguments(clean_db):
    """Test handling of missing required function arguments"""
    pool = await get_pool()
    
    # Insert job with missing required arguments
    job_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fastjob_jobs (id, job_name, args, queue, status, max_attempts)
            VALUES ($1, $2, $3, 'test', 'queued', 3)
            """,
            job_id,
            "tests.integration.test_corrupted_data_handling.simple_test_job",
            json.dumps({})  # Missing required 'message' argument
        )
    
    # Process the job
    async with pool.acquire() as conn:
        processed = await process_jobs(conn, "test")
    
    assert processed  # Job should be processed (moved to dead letter)
    
    # Verify job was moved to dead letter
    async with pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] == "dead_letter"
        assert "Function argument mismatch" in job["last_error"]
        assert job["attempts"] == 3  # Set to max attempts


@pytest.mark.asyncio
async def test_extra_unexpected_arguments(clean_db):
    """Test handling of extra unexpected function arguments"""
    pool = await get_pool()
    
    # Insert job with extra unexpected arguments
    job_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fastjob_jobs (id, job_name, args, queue, status, max_attempts)
            VALUES ($1, $2, $3, 'test', 'queued', 3)
            """,
            job_id,
            "tests.integration.test_corrupted_data_handling.simple_test_job",
            json.dumps({
                "message": "test",
                "unexpected_arg": "value",
                "another_unexpected": 123
            })
        )
    
    # Process the job
    async with pool.acquire() as conn:
        processed = await process_jobs(conn, "test")
    
    assert processed  # Job should be processed (moved to dead letter)
    
    # Verify job was moved to dead letter
    async with pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] == "dead_letter"
        assert "Function argument mismatch" in job["last_error"]
        assert job["attempts"] == 3  # Set to max attempts


@pytest.mark.asyncio
async def test_invalid_json_structure(clean_db):
    """Test handling of JSON with invalid structure"""
    pool = await get_pool()
    
    # Insert job with valid JSON but that will cause parsing issues
    job_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fastjob_jobs (id, job_name, args, queue, status, max_attempts)
            VALUES ($1, $2, $3, 'test', 'queued', 3)
            """,
            job_id,
            "tests.integration.test_corrupted_data_handling.simple_test_job",
            '"just a string not an object"'  # Valid JSON but not an object
        )
    
    # Process the job
    async with pool.acquire() as conn:
        processed = await process_jobs(conn, "test")
    
    assert processed  # Job should be processed (moved to dead letter)
    
    # Verify job was moved to dead letter
    async with pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] == "dead_letter"
        # This might show up as argument mismatch rather than JSON corruption
        assert ("Corrupted" in job["last_error"] or "argument" in job["last_error"])


@pytest.mark.asyncio
async def test_valid_job_still_processes_normally(clean_db):
    """Test that valid jobs are not affected by corruption handling"""
    pool = await get_pool()
    
    # Enqueue a valid job
    job_id = await fastjob.enqueue(simple_test_job, message="valid_test")
    
    # Process the job
    async with pool.acquire() as conn:
        processed = await process_jobs(conn, "default")
    
    assert processed  # Job should be processed successfully
    
    # Verify job completed successfully
    async with pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] in ["done", None]  # Either done or deleted (TTL=0)


@pytest.mark.asyncio
async def test_pydantic_validation_success(clean_db):
    """Test that Pydantic validation works for valid data"""
    pool = await get_pool()
    
    # Enqueue a valid job with Pydantic validation
    job_id = await fastjob.enqueue(validated_test_job, message="valid", count=5)
    
    # Process the job
    async with pool.acquire() as conn:
        processed = await process_jobs(conn, "default")
    
    assert processed  # Job should be processed successfully
    
    # Verify job completed successfully
    async with pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] in ["done", None]  # Either done or deleted (TTL=0)


@pytest.mark.asyncio
async def test_regular_job_exceptions_still_retry(clean_db):
    """Test that regular job exceptions still trigger retry logic"""
    
    @fastjob.job()
    async def failing_job(should_fail: bool = True):
        if should_fail:
            raise ValueError("Intentional failure for testing")
        return "success"
    
    pool = await get_pool()
    
    # Enqueue a job that will fail
    job_id = await fastjob.enqueue(failing_job, should_fail=True)
    
    # Process the job (should fail and be queued for retry)
    async with pool.acquire() as conn:
        processed = await process_jobs(conn, "default")
    
    assert processed  # Job should be processed (failed, but queued for retry)
    
    # Verify job is queued for retry, not dead letter
    async with pool.acquire() as conn:
        job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", job_id)
        assert job["status"] == "queued"  # Should be queued for retry
        assert job["attempts"] == 1  # First attempt failed
        assert "Intentional failure" in job["last_error"]


@pytest.mark.asyncio
async def test_mixed_corrupted_and_valid_jobs(clean_db):
    """Test processing queue with mix of corrupted and valid jobs"""
    pool = await get_pool()
    
    # Insert corrupted job (use validation corruption instead of JSON corruption)
    corrupted_job_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fastjob_jobs (id, job_name, args, queue, status, max_attempts)
            VALUES ($1, $2, $3, 'mixed', 'queued', 3)
            """,
            corrupted_job_id,
            "tests.integration.test_corrupted_data_handling.validated_test_job",
            json.dumps({"message": 123, "count": "not_a_number"})  # Wrong types
        )
    
    # Enqueue valid job
    valid_job_id = await fastjob.enqueue(simple_test_job, message="valid", queue="mixed")
    
    # Process both jobs
    async with pool.acquire() as conn:
        processed1 = await process_jobs(conn, "mixed")
        processed2 = await process_jobs(conn, "mixed")
    
    assert processed1 and processed2  # Both jobs should be processed
    
    # Check corrupted job is in dead letter
    async with pool.acquire() as conn:
        corrupted_job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", corrupted_job_id)
        assert corrupted_job["status"] == "dead_letter"
        
        # Check valid job completed
        valid_job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", valid_job_id)
        assert valid_job["status"] in ["done", None]  # Either done or deleted (TTL=0)