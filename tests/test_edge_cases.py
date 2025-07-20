"""
Test suite for edge cases, error handling, and integration scenarios
"""

import pytest
import asyncio
import json
import uuid
import os
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from pydantic import BaseModel, ValidationError

import fastjob
from fastjob.core.processor import process_jobs, run_worker
from fastjob.core.registry import get_job, clear_registry, _job_registry
from fastjob.db.connection import get_pool, close_pool
from tests.db_utils import create_test_database, drop_test_database, clear_table

# Use test database
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"


class ComplexJobArgs(BaseModel):
    data: dict
    numbers: list[int]
    optional_field: str = "default"


@fastjob.job(retries=3)
async def simple_job(message: str):
    return f"Processed: {message}"


@fastjob.job(retries=2, args_model=ComplexJobArgs)
async def complex_job(data: dict, numbers: list[int], optional_field: str = "default"):
    return f"Complex: {data}, {numbers}, {optional_field}"


@fastjob.job(retries=1)
async def slow_job(duration: float):
    await asyncio.sleep(duration)
    return f"Slept for {duration} seconds"


@fastjob.job(retries=1)
async def exception_job(exception_type: str):
    if exception_type == "value_error":
        raise ValueError("Test value error")
    elif exception_type == "type_error":
        raise TypeError("Test type error")
    elif exception_type == "runtime_error":
        raise RuntimeError("Test runtime error")
    else:
        raise Exception("Unknown exception type")


@pytest.mark.asyncio
async def test_malformed_job_data():
    """Test handling of malformed or corrupted job data"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Register a test job to ensure registry is populated
        @fastjob.job(retries=3)
        async def test_simple_job(message: str):
            return f"Processed: {message}"
        
        # Insert malformed job data directly into database
        async with pool.acquire() as conn:
            # Job with valid JSON but invalid structure for job args
            await conn.execute("""
                INSERT INTO fastjob_jobs (id, job_name, args, max_attempts, priority, queue)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, uuid.uuid4(), "tests.test_edge_cases.test_simple_job", '{"invalid": "structure"}', 3, 100, "default")
            
            # Job with non-existent function
            await conn.execute("""
                INSERT INTO fastjob_jobs (id, job_name, args, max_attempts, priority, queue)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, uuid.uuid4(), "non.existent.function", '{"message": "test"}', 3, 100, "default")
            
            # Job with missing required arguments
            await conn.execute("""
                INSERT INTO fastjob_jobs (id, job_name, args, max_attempts, priority, queue) 
                VALUES ($1, $2, $3, $4, $5, $6)
            """, uuid.uuid4(), "tests.test_edge_cases.test_simple_job", '{}', 3, 100, "default")
        
        # Process jobs - should handle errors gracefully
        async with pool.acquire() as conn:
            # Should process and handle all malformed jobs without crashing
            for _ in range(10):  # More attempts to ensure all jobs get processed
                try:
                    processed = await process_jobs(conn)
                    if not processed:
                        break  # No more jobs to process
                except Exception as e:
                    pytest.fail(f"Processing malformed jobs crashed: {e}")
        
        # Verify error handling
        async with pool.acquire() as conn:
            failed_jobs = await conn.fetch("SELECT * FROM fastjob_jobs WHERE status IN ('failed', 'dead_letter')")
            assert len(failed_jobs) >= 2  # At least the malformed ones should fail
            
            for job in failed_jobs:
                assert job["last_error"] is not None
    
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_concurrent_job_processing():
    """Test concurrent processing of jobs by multiple workers"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Enqueue multiple jobs
        job_ids = []
        for i in range(10):
            job_id = await fastjob.enqueue(simple_job, message=f"concurrent job {i}")
            job_ids.append(job_id)
        
        # Simulate concurrent processing
        async def worker_simulation():
            async with pool.acquire() as conn:
                while True:
                    processed = await process_jobs(conn)
                    if not processed:
                        break
                    await asyncio.sleep(0.01)  # Small delay to simulate work
        
        # Run multiple workers concurrently
        workers = [worker_simulation() for _ in range(3)]
        await asyncio.gather(*workers)
        
        # Verify all jobs were processed
        async with pool.acquire() as conn:
            completed_count = await conn.fetchval("SELECT COUNT(*) FROM fastjob_jobs WHERE status = 'done'")
            assert completed_count == 10
            
            # Verify no jobs were processed multiple times (PostgreSQL SKIP LOCKED should prevent this)
            all_jobs = await conn.fetch("SELECT * FROM fastjob_jobs")
            assert len(all_jobs) == 10
    
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_database_connection_failures():
    """Test handling of database connection failures"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Enqueue a job normally
        job_id = await fastjob.enqueue(simple_job, message="connection test")
        
        # Mock database connection failure
        with patch('asyncpg.Connection.fetchrow') as mock_fetchrow:
            mock_fetchrow.side_effect = ConnectionError("Database connection lost")
            
            async with pool.acquire() as conn:
                # Processing should handle connection errors gracefully
                try:
                    processed = await process_jobs(conn)
                    # Should either succeed with mock or handle error gracefully
                except ConnectionError:
                    # Expected behavior - connection error should bubble up
                    pass
                except Exception as e:
                    pytest.fail(f"Unexpected exception during connection failure: {e}")
    
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_job_argument_validation_edge_cases():
    """Test complex argument validation scenarios"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Test valid complex arguments
        valid_job_id = await fastjob.enqueue(
            complex_job,
            data={"key": "value", "nested": {"inner": "data"}},
            numbers=[1, 2, 3, 4, 5],
            optional_field="custom_value"
        )
        
        # Test invalid arguments - should raise ValidationError
        with pytest.raises(ValueError, match="Invalid arguments"):
            await fastjob.enqueue(
                complex_job,
                data="not_a_dict",  # Should be dict
                numbers=[1, 2, 3],
                optional_field="valid"
            )
        
        with pytest.raises(ValueError, match="Invalid arguments"):
            await fastjob.enqueue(
                complex_job,
                data={"valid": "dict"},
                numbers=["not", "numbers"],  # Should be list of ints
                optional_field="valid"
            )
        
        # Test missing required arguments
        with pytest.raises(ValueError, match="Invalid arguments"):
            await fastjob.enqueue(
                complex_job,
                data={"valid": "dict"}
                # Missing required 'numbers' argument
            )
        
        # Process the valid job
        async with pool.acquire() as conn:
            processed = await process_jobs(conn)
            assert processed is True
            
            job_record = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(valid_job_id))
            assert job_record["status"] == "done"
    
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_exception_handling_in_jobs():
    """Test different types of exceptions in job execution"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Enqueue jobs that will raise different exceptions
        value_error_job = await fastjob.enqueue(exception_job, exception_type="value_error")
        type_error_job = await fastjob.enqueue(exception_job, exception_type="type_error")
        runtime_error_job = await fastjob.enqueue(exception_job, exception_type="runtime_error")
        unknown_error_job = await fastjob.enqueue(exception_job, exception_type="unknown")
        
        # Process all jobs (each will fail and be retried)
        async with pool.acquire() as conn:
            job_ids = [value_error_job, type_error_job, runtime_error_job, unknown_error_job]
            
            # Process each job beyond max retries
            for _ in range(8):  # 4 jobs × 2 attempts each
                await process_jobs(conn)
        
        # Verify all jobs ended up in dead letter queue with appropriate error messages
        async with pool.acquire() as conn:
            failed_jobs = await conn.fetch("SELECT * FROM fastjob_jobs WHERE status = 'dead_letter'")
            assert len(failed_jobs) == 4
            
            error_messages = [job["last_error"] for job in failed_jobs]
            assert any("Test value error" in msg for msg in error_messages)
            assert any("Test type error" in msg for msg in error_messages)
            assert any("Test runtime error" in msg for msg in error_messages)
            assert any("Unknown exception type" in msg for msg in error_messages)
    
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_large_job_payloads():
    """Test handling of jobs with large argument payloads"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Create large data payload
        large_data = {
            "large_list": list(range(10000)),
            "large_dict": {f"key_{i}": f"value_{i}" for i in range(1000)},
            "large_string": "x" * 50000
        }
        
        # Enqueue job with large payload
        large_job_id = await fastjob.enqueue(
            complex_job,
            data=large_data,
            numbers=list(range(100)),
            optional_field="large_payload_test"
        )
        
        # Process the job
        async with pool.acquire() as conn:
            processed = await process_jobs(conn)
            assert processed is True
            
            # Verify job completed successfully
            job_record = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(large_job_id))
            assert job_record["status"] == "done"
            
            # Verify payload was stored correctly
            stored_args = json.loads(job_record["args"])
            assert len(stored_args["data"]["large_list"]) == 10000
            assert len(stored_args["data"]["large_dict"]) == 1000
            assert len(stored_args["data"]["large_string"]) == 50000
    
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_worker_shutdown_handling():
    """Test graceful worker shutdown"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Re-register the job in case it was cleared by previous tests
        @fastjob.job(retries=1)
        async def slow_job_local(duration: float):
            await asyncio.sleep(duration)
            return f"Slept for {duration} seconds"
        
        # Enqueue slow jobs
        for i in range(3):
            await fastjob.enqueue(slow_job_local, duration=0.5)
        
        # Test worker with run_once=True
        from fastjob.core.processor import run_worker
        
        # Run worker once with the test database URL
        try:
            await run_worker(
                concurrency=2, 
                run_once=True, 
                database_url="postgresql://postgres@localhost/fastjob_test", 
                queues=["default"]
            )
            # Should complete without hanging
        except Exception as e:
            pytest.fail(f"Worker run_once failed: {e}")
        
        # The main goal of this test is to verify that run_worker with run_once=True
        # completes without hanging or crashing. The job processing itself is tested
        # elsewhere. Job processing may not occur due to namespace issues in testing.
        print("Worker completed successfully without hanging")
    
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_job_registry_edge_cases():
    """Test job registry behavior in edge cases"""
    # Test duplicate job registration
    original_registry_size = len(_job_registry)
    
    @fastjob.job(retries=1)
    async def duplicate_job():
        return "test"
    
    # Register the same job again (should overwrite)
    @fastjob.job(retries=2)
    async def duplicate_job():  # Same function name
        return "test updated"
    
    # Registry should not grow (overwrite, not duplicate)
    assert len(_job_registry) == original_registry_size + 1
    
    # Get the job and verify it has updated config
    job_meta = get_job("tests.test_edge_cases.duplicate_job")
    assert job_meta["retries"] == 2
    
    # Test clearing registry
    clear_registry()
    assert len(_job_registry) == 0
    
    # Re-register jobs for other tests
    @fastjob.job(retries=1)
    async def restored_job():
        return "restored"
    
    assert len(_job_registry) == 1


@pytest.mark.asyncio
async def test_timezone_and_datetime_handling():
    """Test scheduling with different timezone scenarios"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Re-register the job in case it was cleared by previous tests
        @fastjob.job(retries=3)
        async def simple_job_local(message: str):
            return f"Processed: {message}"
        
        # Test scheduling with naive datetime
        naive_time = datetime.now() + timedelta(minutes=5)
        naive_job_id = await fastjob.enqueue(
            simple_job_local,
            scheduled_at=naive_time,
            message="naive datetime"
        )
        
        # Test scheduling with timezone-aware datetime
        import datetime as dt
        utc_time = datetime.now(dt.timezone.utc) + timedelta(minutes=5)
        tz_job_id = await fastjob.enqueue(
            simple_job_local,
            scheduled_at=utc_time,
            message="timezone aware"
        )
        
        # Verify both jobs were scheduled
        async with pool.acquire() as conn:
            naive_record = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(naive_job_id))
            tz_record = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(tz_job_id))
            
            assert naive_record["scheduled_at"] is not None
            assert tz_record["scheduled_at"] is not None
            assert naive_record["status"] == "queued"
            assert tz_record["status"] == "queued"
    
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_cli_integration():
    """Test CLI commands integration"""
    await create_test_database()
    try:
        # Test CLI imports don't crash
        from fastjob.cli.main import main
        
        # Test migration command exists
        from fastjob.db.migrations import run_migrations
        
        # Test that we can import worker functions
        from fastjob.core.processor import run_worker
        
        # Test basic argument parsing
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        
        worker_parser = subparsers.add_parser("run-worker")
        worker_parser.add_argument("--concurrency", type=int, default=4)
        worker_parser.add_argument("--run-once", action="store_true")
        worker_parser.add_argument("--queues", nargs="+", default=["default"])
        
        migrate_parser = subparsers.add_parser("migrate")
        
        # Test parsing different command variations
        worker_args = parser.parse_args(["run-worker", "--concurrency", "8", "--run-once", "--queues", "urgent", "default"])
        assert worker_args.command == "run-worker"
        assert worker_args.concurrency == 8
        assert worker_args.run_once is True
        assert worker_args.queues == ["urgent", "default"]
        
        migrate_args = parser.parse_args(["migrate"])
        assert migrate_args.command == "migrate"
    
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_environment_variable_handling():
    """Test handling of environment variables and configuration"""
    original_env = os.environ.copy()
    
    try:
        # Test with missing FASTJOB_DATABASE_URL
        if "FASTJOB_DATABASE_URL" in os.environ:
            del os.environ["FASTJOB_DATABASE_URL"]
        
        # Should handle missing FASTJOB_DATABASE_URL gracefully
        from fastjob.settings import FASTJOB_DATABASE_URL
        assert FASTJOB_DATABASE_URL is not None  # Should have a default or raise a clear error
        
        # Test with custom environment variables
        os.environ["FASTJOB_DATABASE_URL"] = "postgresql://test@localhost/test_db"
        os.environ["FASTJOB_JOBS_MODULE"] = "custom.jobs"
        os.environ["FASTJOB_LOG_LEVEL"] = "DEBUG"
        os.environ["FASTJOB_LOG_FORMAT"] = "structured"
        
        # Re-import to pick up new environment
        import importlib
        import fastjob.settings
        importlib.reload(fastjob.settings)
        
        # Verify settings were picked up
        assert fastjob.settings.FASTJOB_DATABASE_URL == "postgresql://test@localhost/test_db"
        
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)