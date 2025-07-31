"""
Tests for job introspection and management

These tests cover the job management features that developers use to check on their jobs,
retry failed ones, cancel long-running ones, etc. Real-world stuff that matters.
"""

import pytest

import fastjob


async def process_test_jobs():
    """Helper to process jobs from all test queues using global API"""
    # Use the global API worker to process jobs from all relevant test queues
    await fastjob.run_worker(run_once=True, queues=["test", "unique_test", "priority_test", "default"])


# Set up test environment
import os

os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"


# Some test jobs to work with
@fastjob.job(retries=2, priority=50, queue="test")
async def simple_task(message: str):
    return f"Processed: {message}"


@fastjob.job(retries=1, priority=10, queue="unique_test", unique=True)
async def unique_task(task_id: str):
    return f"Unique task: {task_id}"


@fastjob.job(retries=3, priority=1, queue="priority_test")
async def priority_task(data: str):
    return f"Priority task: {data}"


class TestJobIntrospection:
    """Test job status and introspection features"""

    # Database setup handled by conftest.py

    @pytest.mark.asyncio
    async def test_get_job_status_existing_job(self):
        """Getting status for a job that exists should work as expected"""

        # Table clearing handled by conftest.py

        # Put a job in the queue
        job_id = await fastjob.enqueue(simple_task, message="test")

        # Now check its status
        status = await fastjob.get_job_status(job_id)

        # Should get back all the details we expect
        assert status is not None
        assert status["id"] == job_id
        # Job name includes the full module path
        expected_job_name = "tests.integration.global_api.test_job_introspection.simple_task"
        assert status["job_name"] == expected_job_name
        assert status["status"] == "queued"
        assert status["queue"] == "test"
        assert status["priority"] == 50
        assert status["attempts"] == 0
        assert status["max_attempts"] == 3  # retries=2 -> max_attempts=3
        assert status["args"] == {"message": "test"}
        assert "created_at" in status
        assert "updated_at" in status

    @pytest.mark.asyncio
    async def test_get_job_status_nonexistent_job(self):
        """Test getting status of non-existent job"""
        status = await fastjob.get_job_status("00000000-0000-0000-0000-000000000000")
        assert status is None

    @pytest.mark.asyncio
    async def test_cancel_queued_job(self):
        """Test cancelling a queued job"""
        # Enqueue a job
        job_id = await fastjob.enqueue(simple_task, message="cancel_me")

        # Cancel the job
        success = await fastjob.cancel_job(job_id)
        assert success is True

        # Verify job is cancelled
        status = await fastjob.get_job_status(job_id)
        assert status["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_job(self):
        """Test cancelling non-existent job"""
        success = await fastjob.cancel_job("00000000-0000-0000-0000-000000000000")
        assert success is False

    @pytest.mark.asyncio
    async def test_cancel_processed_job(self):
        """Test that completed jobs cannot be cancelled"""
        # Enqueue and process a job
        job_id = await fastjob.enqueue(simple_task, message="process_me")

        await process_test_jobs()

        # Try to cancel the completed job
        success = await fastjob.cancel_job(job_id)
        assert success is False, "Should not be able to cancel completed job"

        # Verify job is still done
        status = await fastjob.get_job_status(job_id)
        assert status["status"] == "done"

    @pytest.mark.asyncio
    async def test_retry_failed_job(self):
        """Test retrying a failed job"""

        # Create a job that will fail
        @fastjob.job(retries=1, queue="test")
        async def failing_task():
            raise Exception("Intentional failure")

        job_id = await fastjob.enqueue(failing_task)

        # Process to make it fail - need to process twice since retries=1 means max_attempts=2
        await process_test_jobs()  # First attempt (fails, retries)
        await process_test_jobs()  # Second attempt (fails, goes to dead_letter)

        # Verify it failed
        status = await fastjob.get_job_status(job_id)
        assert status["status"] in ["failed", "dead_letter"]

        # Retry the job
        success = await fastjob.retry_job(job_id)
        assert success is True

        # Verify job is queued again
        status = await fastjob.get_job_status(job_id)
        assert status["status"] == "queued"
        assert status["attempts"] == 0
        assert status["last_error"] is None

    @pytest.mark.asyncio
    async def test_retry_queued_job(self):
        """Test that queued jobs cannot be retried"""
        job_id = await fastjob.enqueue(simple_task, message="queued_job")

        success = await fastjob.retry_job(job_id)
        assert success is False

    @pytest.mark.asyncio
    async def test_delete_job(self):
        """Test deleting a job"""
        job_id = await fastjob.enqueue(simple_task, message="delete_me")

        # Delete the job
        success = await fastjob.delete_job(job_id)
        assert success is True

        # Verify job is gone
        status = await fastjob.get_job_status(job_id)
        assert status is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_job(self):
        """Test deleting non-existent job"""
        success = await fastjob.delete_job("00000000-0000-0000-0000-000000000000")
        assert success is False


class TestJobListing:
    """Test job listing and filtering features"""

    # Database setup handled by conftest.py

    @pytest.mark.asyncio
    async def test_list_all_jobs(self):
        """Test listing all jobs"""
        # Enqueue multiple jobs
        job1 = await fastjob.enqueue(simple_task, message="job1")
        job2 = await fastjob.enqueue(priority_task, data="job2")
        job3 = await fastjob.enqueue(unique_task, task_id="job3")

        # List all jobs
        jobs = await fastjob.list_jobs(limit=10)

        assert len(jobs) == 3
        job_ids = {job["id"] for job in jobs}
        assert {job1, job2, job3}.issubset(job_ids)

    @pytest.mark.asyncio
    async def test_list_jobs_by_queue(self):
        """Test filtering jobs by queue"""
        # Enqueue jobs in different queues
        await fastjob.enqueue(simple_task, message="test_queue_job")  # test queue
        await fastjob.enqueue(
            priority_task, data="priority_queue_job"
        )  # priority_test queue

        # Filter by test queue
        test_jobs = await fastjob.list_jobs(queue="test")
        assert len(test_jobs) == 1
        assert test_jobs[0]["queue"] == "test"

        # Filter by priority_test queue
        priority_jobs = await fastjob.list_jobs(queue="priority_test")
        assert len(priority_jobs) == 1
        assert priority_jobs[0]["queue"] == "priority_test"

    @pytest.mark.asyncio
    async def test_list_jobs_by_status(self):
        """Test filtering jobs by status"""
        # Enqueue jobs - one will be processed, one scheduled for future
        await fastjob.enqueue(simple_task, message="immediate_job")
        from datetime import datetime, timedelta
        future_time = datetime.now() + timedelta(hours=1)
        await fastjob.enqueue(simple_task, message="future_job", scheduled_at=future_time)

        # Process jobs - only immediate job should be processed
        await process_test_jobs()

        # List queued jobs (should include the future job)
        queued_jobs = await fastjob.list_jobs(status="queued")
        assert len(queued_jobs) >= 1
        assert all(job["status"] == "queued" for job in queued_jobs)

        # List done jobs (should include the immediate job)
        done_jobs = await fastjob.list_jobs(status="done")
        assert len(done_jobs) >= 1
        assert all(job["status"] == "done" for job in done_jobs)

    @pytest.mark.asyncio
    async def test_list_jobs_with_limit(self):
        """Test job listing with limit"""
        # Enqueue multiple jobs
        for i in range(5):
            await fastjob.enqueue(simple_task, message=f"job_{i}")

        # List with limit
        jobs = await fastjob.list_jobs(limit=3)
        assert len(jobs) == 3

    @pytest.mark.asyncio
    async def test_list_jobs_with_offset(self):
        """Test job listing with offset"""
        # Enqueue jobs
        job_ids = []
        for i in range(5):
            job_id = await fastjob.enqueue(simple_task, message=f"offset_job_{i}")
            job_ids.append(job_id)

        # Get first 2 jobs
        first_batch = await fastjob.list_jobs(limit=2, offset=0)
        assert len(first_batch) == 2

        # Get next 2 jobs
        second_batch = await fastjob.list_jobs(limit=2, offset=2)
        assert len(second_batch) == 2

        # Ensure no overlap
        first_ids = {job["id"] for job in first_batch}
        second_ids = {job["id"] for job in second_batch}
        assert first_ids.isdisjoint(second_ids)


class TestUniqueJobs:
    """Test unique job functionality"""

    # Database setup handled by conftest.py

    @pytest.mark.asyncio
    async def test_unique_job_prevention(self):
        """Test that unique jobs prevent duplicates"""
        # Enqueue same unique job twice
        job1 = await fastjob.enqueue(unique_task, task_id="same_task")
        job2 = await fastjob.enqueue(unique_task, task_id="same_task")

        # Should return same job ID
        assert job1 == job2

        # Verify only one job exists
        jobs = await fastjob.list_jobs(queue="unique_test")
        assert len(jobs) == 1
        assert jobs[0]["id"] == job1

    @pytest.mark.asyncio
    async def test_unique_job_different_args(self):
        """Test that unique jobs with different args are allowed"""
        job1 = await fastjob.enqueue(unique_task, task_id="task1")
        job2 = await fastjob.enqueue(unique_task, task_id="task2")

        # Should be different job IDs
        assert job1 != job2

        # Verify both jobs exist
        jobs = await fastjob.list_jobs(queue="unique_test")
        assert len(jobs) == 2

    @pytest.mark.asyncio
    async def test_unique_job_after_completion(self):
        """Test that unique jobs can be re-enqueued after completion"""
        # Enqueue and process unique job
        job1 = await fastjob.enqueue(unique_task, task_id="completed_task")
        await process_test_jobs()

        # Verify job is done
        status = await fastjob.get_job_status(job1)
        assert status["status"] == "done"

        # Enqueue same unique job again
        job2 = await fastjob.enqueue(unique_task, task_id="completed_task")

        # Should be a new job ID
        assert job1 != job2

        # Verify new job is queued
        status = await fastjob.get_job_status(job2)
        assert status["status"] == "queued"

    @pytest.mark.asyncio
    async def test_non_unique_job_allows_duplicates(self):
        """Test that non-unique jobs allow duplicates"""
        # Table clearing handled by conftest.py

        # Enqueue same non-unique job twice
        job1 = await fastjob.enqueue(simple_task, message="same_message")
        job2 = await fastjob.enqueue(simple_task, message="same_message")

        # Should be different job IDs
        assert job1 != job2

        # Verify both jobs exist
        jobs = await fastjob.list_jobs(queue="test")
        assert len(jobs) == 2

    @pytest.mark.asyncio
    async def test_unique_override_parameter(self):
        """Test unique parameter override in enqueue"""
        # Non-unique job made unique via parameter
        job1 = await fastjob.enqueue(simple_task, unique=True, message="override_test")
        job2 = await fastjob.enqueue(simple_task, unique=True, message="override_test")

        # Should return same job ID
        assert job1 == job2

        # Verify only one job exists
        jobs = await fastjob.list_jobs(queue="test")
        task_jobs = [job for job in jobs if job["args"]["message"] == "override_test"]
        assert len(task_jobs) == 1


class TestQueueStats:
    """Test queue statistics functionality"""

    # Database setup handled by conftest.py

    @pytest.mark.asyncio
    async def test_empty_queue_stats(self):
        """Test queue stats when no jobs exist"""
        stats = await fastjob.get_queue_stats()
        assert stats == []

    @pytest.mark.asyncio
    async def test_queue_stats_with_jobs(self):
        """Test queue stats with various job states"""
        # Enqueue jobs in different queues
        await fastjob.enqueue(simple_task, message="test1")  # test queue
        await fastjob.enqueue(simple_task, message="test2")  # test queue
        await fastjob.enqueue(priority_task, data="priority1")  # priority_test queue

        # Cancel one job
        job_to_cancel = await fastjob.enqueue(simple_task, message="cancel_me")
        await fastjob.cancel_job(job_to_cancel)

        # Process some jobs
        await process_test_jobs()

        # Get queue stats
        stats = await fastjob.get_queue_stats()

        # Should have stats for both queues
        assert len(stats) == 2

        # Check test queue stats
        test_queue = next((q for q in stats if q["queue"] == "test"), None)
        assert test_queue is not None
        assert test_queue["total"] >= 3
        assert test_queue["cancelled"] >= 1

        # Check priority_test queue stats
        priority_queue = next((q for q in stats if q["queue"] == "priority_test"), None)
        assert priority_queue is not None
        assert priority_queue["total"] >= 1

    @pytest.mark.asyncio
    async def test_queue_stats_structure(self):
        """Test queue stats data structure"""
        # Enqueue a job
        await fastjob.enqueue(simple_task, message="stats_test")

        stats = await fastjob.get_queue_stats()
        assert len(stats) == 1

        queue_stat = stats[0]
        required_fields = [
            "queue",
            "total",
            "queued",
            "processing",
            "done",
            "dead_letter",
            "cancelled",
        ]

        for field in required_fields:
            assert field in queue_stat

        # Queue name should be a string
        assert isinstance(queue_stat["queue"], str)
        assert queue_stat["queue"] == "test"

        # Count fields should be integers
        count_fields = [
            "total",
            "queued",
            "processing",
            "done",
            "dead_letter",
            "cancelled",
        ]
        for field in count_fields:
            assert isinstance(queue_stat[field], int)

        assert queue_stat["total"] == 1
        assert queue_stat["queued"] == 1
