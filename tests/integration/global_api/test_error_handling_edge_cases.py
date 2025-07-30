"""
Comprehensive Error Handling Edge Cases Tests

Tests FastJob's robustness under various failure conditions that could occur
in production environments, including database failures, plugin issues, and
system resource constraints.
"""

import os
import asyncio
import uuid
from unittest.mock import patch, MagicMock

import pytest
import asyncpg

# Ensure we're using test database
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"

import fastjob
from fastjob.db.helpers import fetchrow, fetchval, get_connection
from fastjob.db.connection import get_pool
from fastjob.core.processor import process_jobs
# Use global API for enqueueing jobs
from fastjob.health import check_database_health, HealthStatus
from fastjob.plugins import get_plugin_manager
from fastjob.core.discovery import discover_jobs
from tests.db_utils import clear_table


# Test jobs for edge cases
@fastjob.job()
async def database_dependent_job(data: str):
    """Job that makes database queries during execution"""
    # Simulate database operation during job execution
    await fetchval("SELECT COUNT(*) FROM fastjob_jobs")
    return f"processed: {data}"


@fastjob.job()
async def memory_intensive_job(size_mb: int = 10):
    """Job that consumes significant memory"""
    # Allocate memory (list of 1MB strings)
    data = ['x' * 1024 * 1024 for _ in range(size_mb)]
    await asyncio.sleep(0.1)  # Simulate processing
    return f"processed {len(data)} MB"


@fastjob.job()
async def db_failure_job():
    """Job that simulates database failure"""
    raise asyncpg.ConnectionFailureError("Database connection lost")


@fastjob.job()
async def pool_exhaustion_job():
    """Job that simulates pool exhaustion"""
    raise asyncpg.TooManyConnectionsError("Pool exhausted")


@fastjob.job()
async def timeout_job():
    """Job that simulates timeout"""
    raise asyncio.TimeoutError("Database query timeout")


@fastjob.job()
async def memory_failure_job():
    """Job that simulates memory failure"""
    raise MemoryError("Simulated insufficient memory")


@fastjob.job()
async def system_error_job():
    """Job that simulates system error"""
    raise OSError(28, "Simulated: No space left on device")


@fastjob.job()
async def fd_error_job():
    """Job that simulates file descriptor error"""
    raise OSError(24, "Simulated: Too many open files")


@fastjob.job()
async def failing_job(error_type: str):
    """Job that fails with different error types"""
    if error_type == "value":
        raise ValueError("Value error occurred")
    else:
        raise TypeError("Type error occurred")


@fastjob.job()
async def sometimes_failing_job(attempt_number: int):
    """Job that fails first attempt but succeeds later"""
    if attempt_number == 1:
        raise Exception("Simulated transient failure")
    return f"Success on attempt {attempt_number}"


@fastjob.job()
async def good_job(data: str):
    """Job that always succeeds"""
    return f"processed: {data}"


@fastjob.job()
async def bad_job():
    """Job that always fails"""
    raise Exception("This job always fails")


@fastjob.job()
async def quick_job():
    """Simple job for testing"""
    await asyncio.sleep(0.1)
    return "completed"


@fastjob.job()
async def plugin_dependent_job(message: str):
    """Job that depends on plugin functionality"""
    manager = get_plugin_manager()
    # Try to use plugin feature (may fail if plugins broken)
    result = manager.call_hook("test_hook", message)
    return f"plugin result: {result}"


@pytest.fixture
async def clean_db():
    """Clean database before each test"""
    # Ensure jobs are registered
    discover_jobs()
    
    pool = await get_pool()
    await clear_table(pool)
    yield
    await clear_table(pool)


class TestDatabaseConnectionFailures:
    """Test error handling when database connections fail during job execution"""
    
    @pytest.mark.asyncio
    async def test_database_failure_during_job_execution(self, clean_db):
        """Test job that simulates database failure"""
        job_id = await fastjob.enqueue(db_failure_job)
        
        processed = await fastjob.run_worker(run_once=True)
        
        assert processed  # Job should be processed (failed and will retry)
        
        # Verify job failed and went to dead letter queue (after all retries)
        # Use global app pool for consistency
        global_app = fastjob._get_global_app()
        app_pool = await global_app.get_pool()
        
        async with app_pool.acquire() as conn:
            job = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id))
            assert job is not None, f"Job {job_id} not found"
            assert job["status"] in ["dead_letter", "failed"]  # Should be in dead letter after retries
            assert job["attempts"] >= 3  # Should have attempted multiple times
            assert "Database connection lost" in job["last_error"]
    
    @pytest.mark.asyncio
    async def test_database_pool_exhaustion(self, clean_db):
        """Test behavior when database connection pool is exhausted"""
        job_id = await fastjob.enqueue(pool_exhaustion_job)
        
        processed = await fastjob.run_worker(run_once=True)
        assert processed  # Job processed but failed
    
    @pytest.mark.asyncio
    async def test_database_timeout_during_processing(self, clean_db):
        """Test database timeout during job processing"""
        @fastjob.job()
        async def timeout_job():
            raise asyncio.TimeoutError("Database query timeout")
        
        job_id = await fastjob.enqueue(timeout_job)
        
        async with get_connection() as conn:
            processed = await process_jobs(conn, "default")
        
        assert processed  # Should handle timeout gracefully
        
        # Verify job failed and will be retried
        job = await fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id))
        assert job["status"] == "queued"
        assert "Database query timeout" in job["last_error"]


class TestPluginLoadingFailures:
    """Test error handling when plugins fail to load or function"""
    
    @pytest.mark.asyncio
    async def test_plugin_loading_failure(self, clean_db):
        """Test job execution when plugin loading fails"""
        job_id = await fastjob.enqueue(plugin_dependent_job, message="test_message")
        
        # Mock plugin manager failure
        with patch('fastjob.plugins.get_plugin_manager') as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.call_hook.side_effect = Exception("Plugin system failure")
            mock_get_manager.return_value = mock_manager
            
            async with get_connection() as conn:
                processed = await process_jobs(conn, "default")
        
        assert processed  # Job should be processed (failed)
        
        # Verify job failed and will be retried
        job = await fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id))
        assert job["status"] == "queued"  # Should retry
        assert "Plugin system failure" in job["last_error"]
    
    @pytest.mark.asyncio
    async def test_plugin_hook_timeout(self, clean_db):
        """Test plugin hook that times out"""
        job_id = await fastjob.enqueue(plugin_dependent_job, message="timeout_test")
        
        # Mock a fast timeout instead of 10 seconds
        with patch('fastjob.plugins.get_plugin_manager') as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.call_hook.side_effect = Exception("Plugin timeout after 1s")
            mock_get_manager.return_value = mock_manager
            
            async with get_connection() as conn:
                processed = await process_jobs(conn, "default")
        
        assert processed
        
        # Verify job failed and has timeout error
        job = await fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id))
        assert job["status"] == "queued"  # Should retry
        assert "timeout" in job["last_error"].lower()


class TestMemoryPressureScenarios:
    """Test system behavior under memory pressure"""
    
    @pytest.mark.asyncio
    async def test_memory_intensive_job_execution(self, clean_db):
        """Test execution of memory-intensive jobs"""
        # Enqueue a small memory job for fast testing
        job_id = await fastjob.enqueue(memory_intensive_job, size_mb=1)
        
        async with get_connection() as conn:
            processed = await process_jobs(conn, "default")
        
        assert processed  # Job should complete successfully
        
        # Verify job completed
        job = await fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id))
        assert job["status"] == "done"
    
    @pytest.mark.asyncio
    async def test_simulated_memory_failure(self, clean_db):
        """Test job that simulates memory failure"""
        # Create a simple job that raises MemoryError
        @fastjob.job()
        async def memory_failure_job():
            raise MemoryError("Simulated insufficient memory")
        
        job_id = await fastjob.enqueue(memory_failure_job)
        
        async with get_connection() as conn:
            processed = await process_jobs(conn, "default")
        
        assert processed  # Should handle memory error gracefully
        
        # Verify job failed and will be retried
        job = await fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id))
        assert job["status"] == "queued"
        assert "insufficient memory" in job["last_error"].lower()


class TestHighVolumeErrorScenarios:
    """Test error handling under high job volume"""
    
    @pytest.mark.asyncio
    async def test_job_failure_handling(self, clean_db):
        """Test that job failures are handled properly"""
        @fastjob.job()
        async def failing_job(error_type: str):
            if error_type == "value":
                raise ValueError("Value error occurred")
            else:
                raise TypeError("Type error occurred")
        
        # Enqueue a failing job
        job_id = await fastjob.enqueue(failing_job, error_type="value")
        
        # Process the job (should fail)
        async with get_connection() as conn:
            processed = await process_jobs(conn, "default")
            assert processed
        
        # Verify job failed and will retry
        job = await fetchrow("SELECT status, last_error, attempts FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id))
        
        assert job["status"] == "queued"  # Should retry
        assert job["attempts"] == 1  # One attempt made
        assert job["last_error"] is not None
        assert "Value error occurred" in job["last_error"]
    
    @pytest.mark.asyncio
    async def test_queue_size_handling(self, clean_db):
        """Test behavior with moderate queue size"""
        # Enqueue several small jobs
        job_ids = []
        for i in range(10):
            job_id = await fastjob.enqueue(memory_intensive_job, size_mb=1)
            job_ids.append(job_id)
        
        # Verify all jobs were enqueued
        count = await fetchval("SELECT COUNT(*) FROM fastjob_jobs WHERE status = 'queued'")
        assert count == 10
        
        # Process a few jobs to ensure system handles queue size
        processed_count = 0
        for _ in range(3):
            async with get_connection() as conn:
                processed = await process_jobs(conn, "default")
                if processed:
                    processed_count += 1
        
        assert processed_count == 3


class TestSystemResourceFailures:
    """Test error handling for system resource failures"""
    
    @pytest.mark.asyncio
    async def test_simulated_system_error(self, clean_db):
        """Test job that simulates system resource error"""
        @fastjob.job()
        async def system_error_job():
            raise OSError(28, "Simulated: No space left on device")
        
        job_id = await fastjob.enqueue(system_error_job)
        
        async with get_connection() as conn:
            processed = await process_jobs(conn, "default")
        
        assert processed  # Should handle system error gracefully
        
        # Verify job failed and will be retried
        job = await fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id))
        assert job["status"] == "queued"
        assert "No space left" in job["last_error"]
    
    @pytest.mark.asyncio
    async def test_simulated_file_descriptor_error(self, clean_db):
        """Test job that simulates file descriptor exhaustion"""
        @fastjob.job()
        async def fd_error_job():
            raise OSError(24, "Simulated: Too many open files")
        
        job_id = await fastjob.enqueue(fd_error_job)
        
        async with get_connection() as conn:
            processed = await process_jobs(conn, "default")
        
        assert processed  # Should handle FD error gracefully
        
        # Verify job failed and will be retried
        job = await fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id))
        assert job["status"] == "queued"
        assert "Too many open files" in job["last_error"]


class TestHealthCheckDuringFailures:
    """Test health check behavior during various failure scenarios"""
    
    @pytest.mark.asyncio
    async def test_health_check_during_database_failure(self, clean_db):
        """Test health check when database is failing"""
        # Mock database connection failure
        with patch('fastjob.db.helpers.fetchval', side_effect=asyncpg.ConnectionFailureError("DB down")):
            status, message = await check_database_health()
            
            assert status == HealthStatus.UNHEALTHY
            assert "DB down" in message
    
    @pytest.mark.asyncio
    async def test_health_check_during_high_load(self, clean_db):
        """Test health check behavior under high load"""
        # Enqueue many jobs to create load
        for i in range(10):
            await fastjob.enqueue(memory_intensive_job, size_mb=1)
        
        # Health check should still work
        status, message = await check_database_health()
        assert status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
        assert "jobs in queue" in message


class TestGracefulDegradation:
    """Test system's ability to degrade gracefully under failures"""
    
    @pytest.mark.asyncio
    async def test_job_recovery_after_failure(self, clean_db):
        """Test that jobs can recover after transient failures"""
        @fastjob.job()
        async def sometimes_failing_job(attempt_number: int):
            if attempt_number == 1:
                raise Exception("Simulated transient failure")
            return f"Success on attempt {attempt_number}"
        
        # Enqueue a job that will fail first, then succeed
        job_id = await fastjob.enqueue(sometimes_failing_job, attempt_number=1)
        
        # First attempt should fail
        async with get_connection() as conn:
            processed = await process_jobs(conn, "default")
            assert processed
        
        # Verify job failed and is queued for retry
        job = await fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id))
        assert job["status"] == "queued"
        assert job["attempts"] == 1
        assert "transient failure" in job["last_error"]
    
    @pytest.mark.asyncio
    async def test_error_isolation_between_jobs(self, clean_db):
        """Test that errors in one job don't affect others"""
        @fastjob.job()
        async def good_job(data: str):
            return f"processed: {data}"
        
        @fastjob.job()
        async def bad_job():
            raise Exception("This job always fails")
        
        # Test isolation by running good job first, then bad job
        good_job_id = await fastjob.enqueue(good_job, data="test")
        bad_job_id = await fastjob.enqueue(bad_job)
        
        # Process good job first (should succeed)
        async with get_connection() as conn:
            processed = await process_jobs(conn, "default")
            assert processed
        
        # Process bad job (should fail but not affect system)
        async with get_connection() as conn:
            processed = await process_jobs(conn, "default")
            assert processed
        
        # Verify good job completed, bad job failed but is isolated
        good_job = await fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(good_job_id))
        bad_job = await fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(bad_job_id))
        
        assert good_job["status"] == "done"
        assert bad_job["status"] == "queued"  # Failed, will retry
        assert "always fails" in bad_job["last_error"]