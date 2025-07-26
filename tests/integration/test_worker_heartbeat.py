"""
Test Worker Heartbeat System

Tests worker registration, heartbeat updates, and monitoring functionality.
"""

import os
import asyncio
import time

import pytest

# Ensure we're using test database
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"

import fastjob
from fastjob.db.connection import get_pool
from fastjob.core.heartbeat import WorkerHeartbeat, get_worker_status, cleanup_stale_workers


@pytest.fixture
async def clean_db():
    """Clean database before each test"""
    from tests.db_utils import clear_table
    pool = await get_pool()
    
    # Clear both jobs and workers tables
    await clear_table(pool)
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM fastjob_workers")
    
    yield
    
    # Clean up after test - clear jobs first to avoid FK violation
    await clear_table(pool)
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM fastjob_workers")
    await clear_table(pool)


@pytest.mark.asyncio
async def test_worker_registration(clean_db):
    """Test worker registration creates database record"""
    pool = await get_pool()
    
    # Create heartbeat instance
    heartbeat = WorkerHeartbeat(pool, queues=["test_queue"], concurrency=2)
    
    # Register worker
    await heartbeat.register_worker()
    
    # Verify worker was registered
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM fastjob_workers WHERE id = $1", heartbeat.worker_id
        )
        
        assert result is not None
        assert result['hostname'] == heartbeat.hostname
        assert result['pid'] == heartbeat.pid
        assert result['queues'] == ["test_queue"]
        assert result['concurrency'] == 2
        assert result['status'] == 'active'
        assert result['started_at'] is not None
        assert result['last_heartbeat'] is not None


@pytest.mark.asyncio
async def test_worker_heartbeat_updates(clean_db):
    """Test heartbeat updates timestamp"""
    pool = await get_pool()
    
    # Create and register worker
    heartbeat = WorkerHeartbeat(pool, queues=None, concurrency=1)
    await heartbeat.register_worker()
    
    # Get initial heartbeat time
    async with pool.acquire() as conn:
        initial_result = await conn.fetchrow(
            "SELECT last_heartbeat FROM fastjob_workers WHERE id = $1", 
            heartbeat.worker_id
        )
        initial_time = initial_result['last_heartbeat']
    
    # Wait a small amount and send heartbeat
    await asyncio.sleep(0.1)
    await heartbeat._send_heartbeat()
    
    # Verify heartbeat was updated
    async with pool.acquire() as conn:
        updated_result = await conn.fetchrow(
            "SELECT last_heartbeat FROM fastjob_workers WHERE id = $1", 
            heartbeat.worker_id
        )
        updated_time = updated_result['last_heartbeat']
    
    assert updated_time > initial_time


@pytest.mark.asyncio
async def test_worker_stop_heartbeat(clean_db):
    """Test worker stopping marks status correctly"""
    pool = await get_pool()
    
    # Create and register worker
    heartbeat = WorkerHeartbeat(pool, queues=["queue1", "queue2"], concurrency=4)
    await heartbeat.register_worker()
    
    # Start heartbeat briefly
    await heartbeat.start_heartbeat()
    await asyncio.sleep(0.1)
    
    # Stop heartbeat
    await heartbeat.stop_heartbeat()
    
    # Verify worker is marked as stopped
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT status FROM fastjob_workers WHERE id = $1", heartbeat.worker_id
        )
        assert result['status'] == 'stopped'


@pytest.mark.asyncio
async def test_get_worker_status(clean_db):
    """Test worker status monitoring functionality"""
    pool = await get_pool()
    
    # Create and register a worker
    heartbeat = WorkerHeartbeat(pool, queues=["monitoring_test"], concurrency=2)
    await heartbeat.register_worker()
    
    # Get worker status
    status = await get_worker_status(pool)
    
    assert "status_counts" in status
    assert "active_workers" in status
    assert "total_concurrency" in status
    assert "health" in status
    
    # Check status counts
    assert status["status_counts"]["active"] == 1
    assert status["total_concurrency"] == 2
    assert status["health"] == "healthy"
    
    # Check active worker details
    active_workers = status["active_workers"]
    assert len(active_workers) == 1
    
    worker = active_workers[0]
    assert worker["hostname"] == heartbeat.hostname
    assert worker["pid"] == heartbeat.pid
    assert worker["queues"] == ["monitoring_test"]
    assert worker["concurrency"] == 2
    assert "uptime_seconds" in worker
    assert "metadata" in worker


@pytest.mark.asyncio
async def test_cleanup_stale_workers(clean_db):
    """Test cleanup of stale worker records"""
    pool = await get_pool()
    
    # Create and register a worker
    heartbeat = WorkerHeartbeat(pool, queues=["stale_test"], concurrency=1)
    await heartbeat.register_worker()
    
    # Manually set heartbeat to old time to simulate stale worker
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE fastjob_workers 
            SET last_heartbeat = NOW() - INTERVAL '10 minutes'
            WHERE id = $1
            """,
            heartbeat.worker_id
        )
    
    # Cleanup stale workers (threshold 5 minutes)
    cleaned_count = await cleanup_stale_workers(pool, stale_threshold_seconds=300)
    
    assert cleaned_count == 1
    
    # Verify worker was marked as stopped
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT status FROM fastjob_workers WHERE id = $1", heartbeat.worker_id
        )
        assert result['status'] == 'stopped'


@pytest.mark.asyncio
async def test_worker_job_tracking(clean_db):
    """Test that jobs are tracked to workers"""
    pool = await get_pool()
    
    # Create simple test job
    @fastjob.job()
    async def heartbeat_test_job(message: str):
        return f"processed: {message}"
    
    # Create and register worker
    heartbeat = WorkerHeartbeat(pool, queues=None, concurrency=1)
    await heartbeat.register_worker()
    
    # Enqueue a job
    job_id = await fastjob.enqueue(heartbeat_test_job, message="test_tracking")
    
    # Process job with heartbeat tracking
    from fastjob.core.processor import process_jobs
    async with pool.acquire() as conn:
        processed = await process_jobs(conn, None, heartbeat)
    
    assert processed  # Job should be processed
    
    # Verify job was assigned to worker
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT worker_id FROM fastjob_jobs WHERE id = $1", job_id
        )
        assert result['worker_id'] == heartbeat.worker_id


@pytest.mark.asyncio
async def test_multiple_workers_status(clean_db):
    """Test status with multiple workers"""
    pool = await get_pool()
    
    # Create multiple workers with different PIDs to avoid conflicts
    worker1 = WorkerHeartbeat(pool, queues=["queue1"], concurrency=2)
    worker1.pid = 12345  # Override PID to make unique
    
    worker2 = WorkerHeartbeat(pool, queues=["queue2"], concurrency=4)
    worker2.pid = 12346  # Different PID
    
    worker3 = WorkerHeartbeat(pool, queues=None, concurrency=1)  # All queues
    worker3.pid = 12347  # Different PID
    
    await worker1.register_worker()
    await worker2.register_worker()
    await worker3.register_worker()
    
    # Get status
    status = await get_worker_status(pool)
    
    assert status["status_counts"]["active"] == 3
    assert status["total_concurrency"] == 7  # 2 + 4 + 1
    assert len(status["active_workers"]) == 3
    assert status["health"] == "healthy"
    
    # Stop one worker
    await worker2.stop_heartbeat()
    
    # Check updated status
    status = await get_worker_status(pool)
    assert status["status_counts"]["active"] == 2
    assert status["status_counts"]["stopped"] == 1
    assert status["total_concurrency"] == 3  # 2 + 1 (worker2 stopped)


@pytest.mark.asyncio 
async def test_worker_metadata_collection(clean_db):
    """Test worker metadata is collected properly"""
    pool = await get_pool()
    
    # Create worker
    heartbeat = WorkerHeartbeat(pool, queues=["metadata_test"], concurrency=1)
    await heartbeat.register_worker()
    
    # Get metadata
    metadata = await heartbeat._get_worker_metadata()
    
    # Should always have basic metadata
    assert "python_version" in metadata
    assert "platform" in metadata
    
    # May or may not have psutil data depending on installation
    if "psutil_available" not in metadata:
        # psutil is available
        assert "cpu_percent" in metadata or "memory_mb" in metadata
    else:
        # psutil not available, should be gracefully handled
        assert metadata["psutil_available"] is False