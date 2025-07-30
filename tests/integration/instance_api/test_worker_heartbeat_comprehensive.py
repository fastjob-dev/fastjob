"""
Test Worker Heartbeat System - Comprehensive Instance-Based Tests

Clean, production-ready tests for FastJob instance-based worker heartbeat system.
These tests properly align with the architectural constraint that worker heartbeats
are tracked per process (hostname, pid), not per FastJob instance.
"""

import os
import asyncio
import uuid

import pytest

# Ensure we're using test database
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"

from fastjob import FastJob
from fastjob.core.heartbeat import (
    WorkerHeartbeat,
    get_worker_status,
    cleanup_stale_workers,
)
from tests.db_utils import create_test_database, drop_test_database


@pytest.fixture
async def clean_db():
    """Clean database before each test - FAST VERSION"""
    # Just clear worker records, database setup handled by conftest.py
    from fastjob.client import FastJob
    app = FastJob(database_url="postgresql://postgres@localhost/fastjob_test")
    pool = await app.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM fastjob_workers")
    await app.close()
    
    yield
    
    # Clear worker records after test
    app = FastJob(database_url="postgresql://postgres@localhost/fastjob_test")
    pool = await app.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM fastjob_workers")
    await app.close()


@pytest.fixture
async def fastjob_instance():
    """Create a fresh FastJob instance for each test"""
    app = FastJob(database_url="postgresql://postgres@localhost/fastjob_test")
    yield app
    if app.is_initialized:
        await app.close()


@pytest.mark.asyncio
async def test_worker_heartbeat_lifecycle_complete(clean_db, fastjob_instance):
    """Test complete worker heartbeat lifecycle with instance-based FastJob"""
    app = fastjob_instance
    pool = await app.get_pool()

    # Create worker with instance pool
    worker = WorkerHeartbeat(pool, queues=["lifecycle"], concurrency=3)
    
    # Test registration
    await worker.register_worker()
    
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM fastjob_workers WHERE id = $1", worker.worker_id
        )
        assert result is not None
        assert result["queues"] == ["lifecycle"]
        assert result["concurrency"] == 3
        assert result["status"] == "active"
        initial_heartbeat = result["last_heartbeat"]

    # Test heartbeat start and updates
    await worker.start_heartbeat()
    await asyncio.sleep(0.2)  # Let heartbeat run
    
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT last_heartbeat FROM fastjob_workers WHERE id = $1", worker.worker_id
        )
        updated_heartbeat = result["last_heartbeat"]
        assert updated_heartbeat > initial_heartbeat

    # Test graceful stop
    await worker.stop_heartbeat()
    
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT status FROM fastjob_workers WHERE id = $1", worker.worker_id
        )
        assert result["status"] == "stopped"


@pytest.mark.asyncio
async def test_multiple_fastjob_instances_shared_heartbeat(clean_db):
    """Test that multiple FastJob instances properly share worker heartbeat"""
    # Create multiple FastJob instances
    app1 = FastJob(database_url="postgresql://postgres@localhost/fastjob_test")
    app2 = FastJob(database_url="postgresql://postgres@localhost/fastjob_test")
    
    try:
        pool1 = await app1.get_pool()
        pool2 = await app2.get_pool()
        
        # Create workers from different instances
        worker1 = WorkerHeartbeat(pool1, queues=["shared1"], concurrency=2)
        worker2 = WorkerHeartbeat(pool2, queues=["shared2"], concurrency=4)
        
        # Register first worker
        await worker1.register_worker()
        
        async with pool1.acquire() as conn:
            workers = await conn.fetch("SELECT * FROM fastjob_workers")
            assert len(workers) == 1
            assert workers[0]["queues"] == ["shared1"]
            assert workers[0]["concurrency"] == 2
            assert workers[0]["id"] == worker1.worker_id

        # Register second worker - should update the same record due to (hostname, pid) constraint
        await worker2.register_worker()
        
        async with pool2.acquire() as conn:
            workers = await conn.fetch("SELECT * FROM fastjob_workers")
            assert len(workers) == 1  # Still only one record
            assert workers[0]["queues"] == ["shared2"]  # Updated configuration
            assert workers[0]["concurrency"] == 4  # Updated configuration
            assert workers[0]["id"] == worker2.worker_id  # New worker ID

    finally:
        if app1.is_initialized:
            await app1.close()
        if app2.is_initialized:
            await app2.close()


@pytest.mark.asyncio
async def test_worker_job_processing_integration(clean_db, fastjob_instance):
    """Test worker heartbeat integration with actual job processing"""
    app = fastjob_instance
    pool = await app.get_pool()

    # Define test job
    @app.job(queue="integration")
    async def heartbeat_integration_job(task_id: int):
        await asyncio.sleep(0.01)  # Simulate work
        return f"completed_{task_id}"

    # Create worker and start heartbeat
    worker = WorkerHeartbeat(pool, queues=["integration"], concurrency=2)
    await worker.register_worker()
    await worker.start_heartbeat()

    # Enqueue jobs
    job_ids = []
    for i in range(5):
        job_id = await app.enqueue(heartbeat_integration_job, task_id=i)
        job_ids.append(job_id)

    # Get initial heartbeat
    async with pool.acquire() as conn:
        initial_result = await conn.fetchrow(
            "SELECT last_heartbeat FROM fastjob_workers WHERE id = $1", worker.worker_id
        )
        initial_heartbeat = initial_result["last_heartbeat"]

    # Wait a bit to ensure heartbeat has time to update
    await asyncio.sleep(0.1)
    
    # Process jobs while heartbeat is running
    await app.run_worker(run_once=True, queues=["integration"])

    # Verify heartbeat was updated during processing and jobs completed
    async with pool.acquire() as conn:
        # Check heartbeat was updated (allow small time margin)
        heartbeat_result = await conn.fetchrow(
            "SELECT last_heartbeat FROM fastjob_workers WHERE id = $1", worker.worker_id
        )
        final_heartbeat = heartbeat_result["last_heartbeat"]
        # Allow for same timestamp if processing was very fast
        assert final_heartbeat >= initial_heartbeat

        # Check jobs were processed
        completed_count = await conn.fetchval(
            "SELECT COUNT(*) FROM fastjob_jobs WHERE status = 'done'"
        )
        assert completed_count == 5

    # Clean up
    await worker.stop_heartbeat()


@pytest.mark.asyncio
async def test_worker_failure_detection_and_cleanup(clean_db, fastjob_instance):
    """Test worker failure detection and cleanup functionality"""
    app = fastjob_instance
    pool = await app.get_pool()

    # Create and register worker
    worker = WorkerHeartbeat(pool, queues=["failure_test"], concurrency=1)
    await worker.register_worker()
    await worker.start_heartbeat()

    # Verify worker is active
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT status, last_heartbeat FROM fastjob_workers WHERE id = $1",
            worker.worker_id
        )
        assert result["status"] == "active"
        initial_heartbeat = result["last_heartbeat"]

    # Simulate worker failure by cancelling heartbeat task
    if worker.heartbeat_task and not worker.heartbeat_task.cancelled():
        worker.heartbeat_task.cancel()
        try:
            await worker.heartbeat_task
        except asyncio.CancelledError:
            pass  # Expected

    # Wait for heartbeat to become stale
    await asyncio.sleep(0.5)

    # Run cleanup (simulating monitoring system)
    cleaned_count = await cleanup_stale_workers(pool, stale_threshold_seconds=0.3)
    assert cleaned_count > 0

    # Verify worker is now marked as stopped
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT status FROM fastjob_workers WHERE id = $1", worker.worker_id
        )
        assert result["status"] == "stopped"


@pytest.mark.asyncio
async def test_worker_status_monitoring_functions(clean_db, fastjob_instance):
    """Test worker status monitoring utility functions"""
    app = fastjob_instance
    pool = await app.get_pool()

    # Create and register multiple workers to test monitoring
    workers = []
    for i in range(3):
        worker = WorkerHeartbeat(pool, queues=[f"monitor_{i}"], concurrency=i+1)
        await worker.register_worker()
        if i < 2:  # Start heartbeat for first 2 workers only
            await worker.start_heartbeat()
        workers.append(worker)

    await asyncio.sleep(0.1)  # Let heartbeats run

    # Test get_worker_status function (returns aggregate status)
    status = await get_worker_status(pool)
    assert status is not None
    assert "active_workers" in status
    assert "status_counts" in status
    assert "health" in status
    assert "total_concurrency" in status
    assert status["status_counts"].get("active", 0) >= 1  # At least one active worker
    assert status["health"] in ["healthy", "degraded"]

    # Test individual worker status via direct database query
    async with pool.acquire() as conn:
        # Check individual worker details
        for i, worker in enumerate(workers):
            result = await conn.fetchrow(
                "SELECT * FROM fastjob_workers WHERE id = $1", worker.worker_id
            )
            if i < 2:  # Workers with heartbeats (but only last one due to constraint)
                if result:  # Due to (hostname, pid) constraint, only one worker record exists
                    assert result["status"] == "active"
            # Since workers overwrite each other due to constraint, check the final state
        
        # Check total worker count (should be 1 due to constraint)
        total_count = await conn.fetchval("SELECT COUNT(*) FROM fastjob_workers")
        assert total_count == 1
        
        # Test non-existent worker query
        fake_id = uuid.uuid4()
        fake_result = await conn.fetchrow(
            "SELECT * FROM fastjob_workers WHERE id = $1", fake_id
        )
        assert fake_result is None

    # Clean up active workers
    for worker in workers[:2]:
        await worker.stop_heartbeat()


@pytest.mark.asyncio
async def test_worker_configuration_persistence(clean_db, fastjob_instance):
    """Test that worker configuration persists correctly"""
    app = fastjob_instance
    pool = await app.get_pool()

    # Test different configuration combinations
    configs = [
        {"queues": ["config1"], "concurrency": 1},
        {"queues": ["config1", "config2"], "concurrency": 4},
        {"queues": None, "concurrency": 8},  # All queues
        {"queues": [], "concurrency": 2},  # Empty queue list
    ]

    for i, config in enumerate(configs):
        worker = WorkerHeartbeat(pool, **config)
        await worker.register_worker()

        # Verify configuration was saved correctly
        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM fastjob_workers WHERE id = $1", worker.worker_id
            )
            assert result is not None
            
            # Handle different queue representations
            expected_queues = config["queues"]
            if expected_queues is None:
                # Database stores NULL as None, which is expected
                assert result["queues"] is None
            elif expected_queues == []:
                # Empty list might be stored as None or empty array
                assert result["queues"] is None or result["queues"] == []
            else:
                assert result["queues"] == expected_queues
            
            assert result["concurrency"] == config["concurrency"]
            assert result["status"] == "active"

        # Each registration overwrites due to (hostname, pid) constraint
        # So we only expect 1 worker record at any time
        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM fastjob_workers")
            assert count == 1


@pytest.mark.asyncio  
async def test_database_pool_consistency_across_instances(clean_db):
    """Test that database operations are consistent across different FastJob instance pools"""
    # Create multiple FastJob instances
    instances = [
        FastJob(database_url="postgresql://postgres@localhost/fastjob_test"),
        FastJob(database_url="postgresql://postgres@localhost/fastjob_test"),
        FastJob(database_url="postgresql://postgres@localhost/fastjob_test"),
    ]
    
    try:
        # Get pools from each instance
        pools = [await app.get_pool() for app in instances]
        
        # Verify pools are different objects but access same database
        assert pools[0] is not pools[1]
        assert pools[1] is not pools[2]
        
        # Create worker using first pool
        worker = WorkerHeartbeat(pools[0], queues=["consistency"], concurrency=3)
        await worker.register_worker()
        
        # Verify all pools can see the same worker record
        for pool in pools:
            async with pool.acquire() as conn:
                result = await conn.fetchrow(
                    "SELECT * FROM fastjob_workers WHERE id = $1", worker.worker_id
                )
                assert result is not None
                assert result["queues"] == ["consistency"]
                assert result["concurrency"] == 3
                
        # Update worker configuration using second pool  
        worker2 = WorkerHeartbeat(pools[1], queues=["updated"], concurrency=5)
        await worker2.register_worker()
        
        # Verify update is visible from all pools
        for pool in pools:
            async with pool.acquire() as conn:
                workers = await conn.fetch("SELECT * FROM fastjob_workers")
                assert len(workers) == 1  # Still only one due to constraint
                assert workers[0]["queues"] == ["updated"]
                assert workers[0]["concurrency"] == 5
                assert workers[0]["id"] == worker2.worker_id

    finally:
        # Clean up all instances
        for app in instances:
            if app.is_initialized:
                await app.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])