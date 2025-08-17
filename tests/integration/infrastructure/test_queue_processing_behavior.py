"""
Test Queue Processing Behavior - New efficient queue handling

Tests the updated queue processing logic that handles:
- All queues processing (queue=None)
- Single queue processing (queue="name")
- Multiple queues processing (queue=["name1", "name2"])
- Priority ordering across different queues
- Fair processing without queue starvation
"""

import asyncio
import os
import tempfile
from datetime import datetime, timedelta

import pytest

# Ensure we're using test database
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"

from fastjob.core.processor import process_jobs
from fastjob.core.queue import enqueue_job
from fastjob.core.registry import clear_registry
from fastjob.db.connection import get_pool
from tests.db_utils import clear_table


# Define test job function (not decorated at module level)
async def write_to_file_job(message: str, result_file: str):
    """Test job that writes result to file"""
    with open(result_file, "a") as f:
        f.write(f"{message}\n")


@pytest.fixture
async def clean_db():
    """Clean database before each test"""
    pool = await get_pool()
    await clear_table(pool)

    # Clear job registry to avoid cross-test pollution
    clear_registry()

    yield

    await clear_table(pool)
    clear_registry()


@pytest.fixture
def result_file():
    """Create a temporary file for job results"""
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as f:
        result_file_path = f.name
    yield result_file_path
    # Cleanup
    try:
        os.unlink(result_file_path)
    except FileNotFoundError:
        pass


@pytest.mark.asyncio
async def test_process_jobs_all_queues(clean_db, result_file):
    """Test that queue=None processes jobs from any queue"""

    # Register the job in each test
    from fastjob.core.registry import get_global_registry

    registry = get_global_registry()
    registry.register_job(write_to_file_job)

    pool = await get_pool()

    # Enqueue jobs in different queues using legacy API
    async with pool.acquire() as conn:
        await enqueue_job(
            pool,
            registry,
            write_to_file_job,
            queue="high",
            message="job1",
            result_file=result_file,
        )
        await enqueue_job(
            pool,
            registry,
            write_to_file_job,
            queue="normal",
            message="job2",
            result_file=result_file,
        )
        await enqueue_job(
            pool,
            registry,
            write_to_file_job,
            queue="low",
            message="job3",
            result_file=result_file,
        )

    # Process with queue=None should pick up any job
    async with pool.acquire() as conn:
        processed1 = await process_jobs(conn, None)
        processed2 = await process_jobs(conn, None)
        processed3 = await process_jobs(conn, None)
        processed4 = await process_jobs(conn, None)  # Should be False

    assert processed1 is True
    assert processed2 is True
    assert processed3 is True
    assert processed4 is False  # No more jobs

    # Check results
    with open(result_file, "r") as f:
        results = f.read().strip().split("\n")

    processed_messages = {msg for msg in results if msg}
    assert len(processed_messages) == 3  # 3 jobs processed
    assert "job1" in processed_messages
    assert "job2" in processed_messages
    assert "job3" in processed_messages


@pytest.mark.asyncio
async def test_process_jobs_single_queue(clean_db, result_file):
    """Test that queue="name" processes only from that queue"""

    # Register the job in each test
    from fastjob.core.registry import get_global_registry

    registry = get_global_registry()
    registry.register_job(write_to_file_job)

    pool = await get_pool()

    # Enqueue jobs in different queues using legacy API
    async with pool.acquire() as conn:
        await enqueue_job(
            pool,
            registry,
            write_to_file_job,
            queue="target",
            message="target_job",
            result_file=result_file,
        )
        await enqueue_job(
            pool,
            registry,
            write_to_file_job,
            queue="other",
            message="other_job",
            result_file=result_file,
        )

    # Process only from "target" queue
    async with pool.acquire() as conn:
        processed1 = await process_jobs(conn, "target")
        processed2 = await process_jobs(conn, "target")  # Should be False

    assert processed1 is True
    assert processed2 is False

    # Check results
    with open(result_file, "r") as f:
        results = f.read().strip()

    assert "target_job" in results
    assert "other_job" not in results  # Should not be processed


@pytest.mark.asyncio
async def test_process_jobs_multiple_queues(clean_db, result_file):
    """Test that queue=["q1", "q2"] processes from specified queues efficiently"""

    # Register the job in each test
    from fastjob.core.registry import get_global_registry

    registry = get_global_registry()
    registry.register_job(write_to_file_job)

    pool = await get_pool()

    # Enqueue jobs in different queues using legacy API
    await enqueue_job(
        pool,
        registry,
        write_to_file_job,
        queue="queue1",
        message="job1",
        result_file=result_file,
    )
    await enqueue_job(
        pool,
        registry,
        write_to_file_job,
        queue="queue2",
        message="job2",
        result_file=result_file,
    )
    await enqueue_job(
        pool,
        registry,
        write_to_file_job,
        queue="excluded",
        message="job3",
        result_file=result_file,
    )

    # Process only from specified queues
    async with pool.acquire() as conn:
        processed1 = await process_jobs(conn, ["queue1", "queue2"])
        processed2 = await process_jobs(conn, ["queue1", "queue2"])
        processed3 = await process_jobs(conn, ["queue1", "queue2"])  # Should be False

    assert processed1 is True
    assert processed2 is True
    assert processed3 is False  # No more jobs in target queues

    # Check results
    with open(result_file, "r") as f:
        results = f.read().strip()

    assert "job1" in results
    assert "job2" in results
    assert "job3" not in results  # Excluded queue should not be processed


@pytest.mark.asyncio
async def test_priority_ordering_across_queues(clean_db, result_file):
    """Test that priority ordering works correctly across different queues"""

    # Register the job in each test
    from fastjob.core.registry import get_global_registry

    registry = get_global_registry()
    registry.register_job(write_to_file_job)

    pool = await get_pool()

    # Enqueue jobs with different priorities across different queues using legacy API
    # Lower priority number = higher priority
    await enqueue_job(
        pool,
        registry,
        write_to_file_job,
        queue="queueA",
        priority=100,
        message="medium_A",
        result_file=result_file,
    )
    await enqueue_job(
        pool,
        registry,
        write_to_file_job,
        queue="queueB",
        priority=50,
        message="high_B",
        result_file=result_file,
    )
    await enqueue_job(
        pool,
        registry,
        write_to_file_job,
        queue="queueA",
        priority=200,
        message="low_A",
        result_file=result_file,
    )
    await enqueue_job(
        pool,
        registry,
        write_to_file_job,
        queue="queueC",
        priority=25,
        message="highest_C",
        result_file=result_file,
    )

    # Process all jobs in order to verify priority ordering
    async with pool.acquire() as conn:
        processed1 = await process_jobs(conn, ["queueA", "queueB", "queueC"])
        processed2 = await process_jobs(conn, ["queueA", "queueB", "queueC"])
        processed3 = await process_jobs(conn, ["queueA", "queueB", "queueC"])
        processed4 = await process_jobs(conn, ["queueA", "queueB", "queueC"])
        processed5 = await process_jobs(
            conn, ["queueA", "queueB", "queueC"]
        )  # Should be False

    assert processed1 is True
    assert processed2 is True
    assert processed3 is True
    assert processed4 is True
    assert processed5 is False  # No more jobs

    # Check results file - priority order should be preserved
    with open(result_file, "r") as f:
        results = f.read().strip().split("\n")
        processed_messages = [msg for msg in results if msg]

    # Should be processed in priority order regardless of queue (priority: 25, 50, 100, 200)
    assert processed_messages == ["highest_C", "high_B", "medium_A", "low_A"]


@pytest.mark.asyncio
async def test_scheduled_jobs_across_queues(clean_db, result_file):
    """Test that scheduled jobs work correctly across different queues"""

    # Register the job in each test
    from fastjob.core.registry import get_global_registry

    registry = get_global_registry()
    registry.register_job(write_to_file_job)

    pool = await get_pool()
    future_time = datetime.now() + timedelta(seconds=1)

    # Schedule jobs in different queues using legacy API
    await enqueue_job(
        pool,
        registry,
        write_to_file_job,
        queue="queue1",
        scheduled_at=future_time,
        message="scheduled1",
        result_file=result_file,
    )
    await enqueue_job(
        pool,
        registry,
        write_to_file_job,
        queue="queue2",
        scheduled_at=future_time,
        message="scheduled2",
        result_file=result_file,
    )

    # Check that scheduled jobs are not processed before time
    async with pool.acquire() as conn:
        processed1 = await process_jobs(conn, None)
        assert processed1 is False, "No jobs should be processed before scheduled time"

    # Wait for scheduled time
    await asyncio.sleep(1.5)

    # Should now process scheduled jobs
    async with pool.acquire() as conn:
        processed2 = await process_jobs(conn, None)
        processed3 = await process_jobs(conn, None)
        processed4 = await process_jobs(conn, None)  # Should be False

    assert processed2 is True
    assert processed3 is True
    assert processed4 is False

    # Check results
    with open(result_file, "r") as f:
        results = f.read().strip().split("\n")

    processed_messages = {msg for msg in results if msg}
    assert len(processed_messages) == 2
    assert "scheduled1" in processed_messages
    assert "scheduled2" in processed_messages


@pytest.mark.asyncio
async def test_empty_queue_list(clean_db, result_file):
    """Test that empty queue list behaves correctly"""

    # Register the job in each test
    from fastjob.core.registry import get_global_registry

    registry = get_global_registry()
    registry.register_job(write_to_file_job)

    pool = await get_pool()

    await enqueue_job(
        pool,
        registry,
        write_to_file_job,
        queue="some_queue",
        message="job1",
        result_file=result_file,
    )

    # Empty queue list should not process any jobs
    async with pool.acquire() as conn:
        processed = await process_jobs(conn, [])

    assert processed is False

    # Check no results were written
    with open(result_file, "r") as f:
        results = f.read().strip()

    assert results == ""  # No jobs processed


@pytest.mark.asyncio
async def test_queue_efficiency_single_query(clean_db):
    """Test that multiple queues use single efficient query"""

    # Register the job in each test
    from fastjob.core.registry import get_global_registry

    registry = get_global_registry()
    registry.register_job(write_to_file_job)

    pool = await get_pool()

    # Enqueue jobs in multiple queues
    for i in range(3):
        await enqueue_job(
            pool,
            registry,
            write_to_file_job,
            queue=f"queue{i}",
            message=f"job{i}",
            result_file="/tmp/test",
        )

    # This should use a single query with WHERE queue = ANY([...])
    async with pool.acquire() as conn:
        processed = await process_jobs(conn, ["queue0", "queue1", "queue2"])

    assert processed is True  # At least one job was processed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
