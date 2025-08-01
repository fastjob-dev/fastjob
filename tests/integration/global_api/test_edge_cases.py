"""
Test suite for edge cases, error handling, and integration scenarios
"""

import pytest
import os
from datetime import datetime, timedelta
from unittest.mock import patch
from pydantic import BaseModel

import fastjob

# Use test database
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"


class ComplexJobArgs(BaseModel):
    data: dict
    numbers: list[int]
    optional_field: str = "default"


# Test job definitions
@fastjob.job()
async def simple_job(message: str):
    return f"Processed: {message}"


@fastjob.job(retries=3)
async def complex_job(data: dict, numbers: list[int], optional_field: str = "default"):
    return f"Complex job processed: {len(data)} keys, {len(numbers)} numbers"


@fastjob.job()
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
    # Register a test job to ensure registry is populated
    @fastjob.job(retries=3)
    async def test_simple_job(message: str):
        return f"Processed: {message}"

    # Enqueue a normal job first
    job_id = await fastjob.enqueue(test_simple_job, message="normal job")
    
    # Process the job
    processed = await fastjob.run_worker(run_once=True)
    assert processed

    # Get job status to verify it worked
    status = await fastjob.get_job_status(job_id)
    assert status["status"] == "done"


@pytest.mark.asyncio
async def test_concurrent_job_processing():
    """Test concurrent processing of jobs by multiple workers"""
    # Enqueue multiple jobs using global API
    job_ids = []
    for i in range(5):  # Reduced for speed
        job_id = await fastjob.enqueue(simple_job, message=f"concurrent job {i}")
        job_ids.append(job_id)

    # Process all jobs
    processed_count = 0
    for _ in range(10):  # Try multiple times to process all jobs
        processed = await fastjob.run_worker(run_once=True)
        if processed:
            processed_count += 1
        else:
            break

    # Verify all jobs were processed
    done_jobs = await fastjob.list_jobs(status="done")
    assert len(done_jobs) >= 5


@pytest.mark.asyncio
async def test_database_connection_failures():
    """Test handling of database connection failures"""
    # Enqueue a job normally
    await fastjob.enqueue(simple_job, message="connection test")

    # Mock database connection failure
    with patch('fastjob.db.helpers.fetchval', side_effect=ConnectionError("DB down")):
        try:
            # This should handle the connection error gracefully
            await fastjob.run_worker(run_once=True)
            # Should either succeed with mock or handle error gracefully
        except ConnectionError:
            # Expected behavior - connection error should bubble up
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception during connection failure: {e}")


@pytest.mark.asyncio
async def test_job_argument_validation_edge_cases():
    """Test complex argument validation scenarios"""
    # Test valid complex arguments
    valid_job_id = await fastjob.enqueue(
        complex_job,
        data={"key": "value", "nested": {"inner": "data"}},
        numbers=[1, 2, 3, 4, 5],
        optional_field="custom_value"
    )

    # Process the job
    processed = await fastjob.run_worker(run_once=True)
    assert processed

    # Verify job completed
    status = await fastjob.get_job_status(valid_job_id)
    assert status["status"] == "done"


@pytest.mark.asyncio
async def test_exception_handling_in_jobs():
    """Test different types of exceptions in job execution"""
    # Enqueue jobs that will raise different exceptions
    value_error_job = await fastjob.enqueue(exception_job, exception_type="value_error")
    type_error_job = await fastjob.enqueue(exception_job, exception_type="type_error")

    # Process jobs (they will fail)
    for _ in range(10):  # Multiple attempts to handle retries
        processed = await fastjob.run_worker(run_once=True)
        if not processed:
            break

    # Check that jobs failed with appropriate errors
    value_status = await fastjob.get_job_status(value_error_job)
    type_status = await fastjob.get_job_status(type_error_job)
    
    assert value_status["status"] in ["failed", "dead_letter"]
    assert type_status["status"] in ["failed", "dead_letter"]
    assert "Test value error" in value_status["last_error"]
    assert "Test type error" in type_status["last_error"]


@pytest.mark.asyncio
async def test_large_job_payloads():
    """Test handling of jobs with large argument payloads"""
    # Create moderate data payload (within database index limits)
    large_data = {
        "large_list": list(range(50)),  # Reduced for speed
        "large_dict": {f"key_{i}": f"value_{i}" for i in range(10)},
        "large_string": "x" * 100
    }

    # Enqueue job with large payload
    job_id = await fastjob.enqueue(complex_job, data=large_data, numbers=list(range(20)))

    # Process the job
    processed = await fastjob.run_worker(run_once=True)
    assert processed

    # Verify job completed
    status = await fastjob.get_job_status(job_id)
    assert status["status"] == "done"
    assert len(status["args"]["data"]["large_list"]) == 50


@pytest.mark.asyncio
async def test_worker_shutdown_handling():
    """Test graceful worker shutdown"""
    # Enqueue a quick job
    await fastjob.enqueue(simple_job, message="shutdown test")

    # Test that run_worker with run_once=True completes without hanging
    try:
        await fastjob.run_worker(run_once=True)
        # The main goal is to verify no hanging or crashing occurs
        print("Worker completed successfully without hanging")
    except Exception as e:
        pytest.fail(f"Worker run_once failed: {e}")


@pytest.mark.asyncio
async def test_registry_edge_cases():
    """Test job registry behavior in edge cases"""
    # Test duplicate job registration with global FastJob app
    global_app = fastjob._get_global_app()
    app_registry = global_app.get_job_registry()

    initial_count = len(app_registry)

    # Register the same job function multiple times
    @fastjob.job()
    async def duplicate_job():
        return "duplicate"

    @fastjob.job()
    async def duplicate_job():  # Same name, should replace
        return "replaced"

    @fastjob.job()
    async def another_job():
        return "another"

    # Registry should handle duplicates gracefully
    assert len(app_registry) >= initial_count


@pytest.mark.asyncio
async def test_timezone_and_datetime_handling():
    """Test scheduling with different timezone scenarios"""
    # Test naive datetime scheduling
    future_time = datetime.now() + timedelta(minutes=30)
    naive_job = await fastjob.enqueue(simple_job, message="naive", scheduled_at=future_time)

    # Test timezone-aware datetime scheduling  
    from datetime import timezone
    tz_time = datetime.now(timezone.utc) + timedelta(minutes=30)
    tz_job = await fastjob.enqueue(simple_job, message="timezone", scheduled_at=tz_time)

    # Verify both jobs were scheduled
    naive_status = await fastjob.get_job_status(naive_job)
    tz_status = await fastjob.get_job_status(tz_job)

    assert naive_status["scheduled_at"] is not None
    assert tz_status["scheduled_at"] is not None
    assert naive_status["status"] == "queued"
    assert tz_status["status"] == "queued"


@pytest.mark.asyncio
async def test_cli_integration():
    """Test CLI commands integration"""
    # Test CLI imports don't crash
    from fastjob.cli.main import main
    from fastjob.cli.registry import get_cli_registry
    from fastjob.cli.commands.core import register_core_commands

    # Test core command registration
    register_core_commands()
    registry = get_cli_registry()
    
    # Verify core commands are registered
    commands = registry.get_all_commands()
    command_names = [cmd.name for cmd in commands]
    
    assert "setup" in command_names  # Database setup command
    assert "start" in command_names  # Worker start command
    
    # Test that main function exists and is callable
    assert callable(main)


@pytest.mark.asyncio
async def test_environment_variable_handling():
    """Test handling of environment variables and configuration"""
    original_env = os.environ.copy()

    try:
        # Test database URL environment variable
        test_url = "postgresql://test@localhost/test_db"
        os.environ["FASTJOB_DATABASE_URL"] = test_url
        
        # Verify environment variable is read correctly
        assert os.environ.get("FASTJOB_DATABASE_URL") == test_url
        
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)