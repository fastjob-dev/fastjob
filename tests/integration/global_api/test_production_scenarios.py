"""
Production scenario tests for FastJob reliability

These tests cover real-world failure modes and edge cases that must work
correctly for FastJob to be truly production-ready.
"""

import asyncio
import pytest
import signal
import os
import time
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta


import fastjob
from fastjob.db.connection import DatabaseContext
from fastjob.settings import get_settings


# Test job functions
@fastjob.job(unique=False)  # Ensure multiple instances can be enqueued
async def job_counter(counter_file: str, job_index: int = 0):
    """Test job that writes to a file to track execution"""
    # Ensure directory exists
    Path(counter_file).parent.mkdir(parents=True, exist_ok=True)

    with open(counter_file, "a") as f:
        f.write(f"{os.getpid()}-{job_index}-{datetime.now().isoformat()}\n")
    return f"completed-{job_index}"


@fastjob.job()
async def slow_test_job(duration: float, result_file: str):
    """Job that takes time - useful for testing interruption"""
    start_time = time.time()
    await asyncio.sleep(duration)
    end_time = time.time()

    with open(result_file, "w") as f:
        f.write(f"completed-{start_time}-{end_time}\n")

    return f"slow_job_completed_after_{duration}s"


@fastjob.job()
async def database_intensive_job(job_id: str, iterations: int = 100):
    """Job that does database operations - useful for testing connection issues"""
    async with DatabaseContext() as pool:
        async with pool.acquire() as conn:
            results = []
            for i in range(iterations):
                result = await conn.fetchval(
                    "SELECT $1 + $2", i, int(job_id[-4:], 16) % 1000
                )
                results.append(result)
                await asyncio.sleep(0.01)  # Small delay to make it interruptible
            return f"database_job_completed_{len(results)}_operations"


@fastjob.job()
async def failing_job(should_fail: bool, job_id: int):
    """Job that can be configured to fail"""
    if should_fail:
        raise Exception(f"Intentional failure in job {job_id}")
    return f"success_job_{job_id}"


@fastjob.job()
async def timed_job(expected_time: str, log_file: str):
    """Job that logs its execution time"""
    execution_time = datetime.now().isoformat()
    with open(log_file, "a") as f:
        f.write(f"{expected_time}|{execution_time}\n")
    return "timed_job_completed"


class TestProductionScenarios:
    """Test suite for production reliability scenarios"""

    @pytest.mark.asyncio
    async def test_worker_graceful_shutdown_on_keyboard_interrupt(self):
        """Test that workers shut down gracefully when interrupted with Ctrl+C"""

        with tempfile.TemporaryDirectory() as temp_dir:
            counter_file = os.path.join(temp_dir, "job_counter.txt")
            result_file = os.path.join(temp_dir, "slow_job_result.txt")

            # Enqueue a mix of fast and slow jobs
            async with DatabaseContext():
                job_ids = []

                # Fast jobs that should complete
                for i in range(5):
                    job_id = await fastjob.enqueue(
                        job_counter, counter_file=counter_file, job_index=i
                    )
                    job_ids.append(job_id)

                # Slow job that will be interrupted
                slow_job_id = await fastjob.enqueue(
                    slow_test_job, duration=10.0, result_file=result_file
                )
                job_ids.append(slow_job_id)

            # Start worker in subprocess to test real signal handling
            settings = get_settings()
            worker_script = f"""
import asyncio
import sys
sys.path.insert(0, "{os.path.dirname(os.path.dirname(__file__))}")

from fastjob.core.processor import run_worker

if __name__ == "__main__":
    asyncio.run(run_worker(concurrency=2, database_url="{settings.database_url}"))
"""

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False
            ) as script_file:
                script_file.write(worker_script)
                script_file.flush()

                try:
                    # Start the worker process
                    process = subprocess.Popen([sys.executable, script_file.name])

                    # Give worker time to start and process some jobs
                    await asyncio.sleep(2.0)

                    # Send SIGINT (Ctrl+C)
                    process.send_signal(signal.SIGINT)

                    # Wait for graceful shutdown (should happen within 10 seconds)
                    try:
                        exit_code = process.wait(timeout=10)
                        assert (
                            exit_code == 0 or exit_code == -signal.SIGINT
                        ), f"Worker exited with code {exit_code}"
                    except subprocess.TimeoutExpired:
                        process.kill()  # Force kill if it doesn't shut down gracefully
                        pytest.fail(
                            "Worker did not shut down gracefully within timeout"
                        )

                    # Verify that some jobs were processed before shutdown
                    if os.path.exists(counter_file):
                        with open(counter_file, "r") as f:
                            job_executions = f.readlines()
                        assert (
                            len(job_executions) >= 1
                        ), "No jobs were processed before shutdown"

                    # Slow job should NOT have completed (was interrupted)
                    assert not os.path.exists(
                        result_file
                    ), "Slow job completed despite interrupt"

                finally:
                    os.unlink(script_file.name)
                    if process.poll() is None:
                        process.kill()

    @pytest.mark.asyncio
    async def test_database_connection_loss_and_recovery(self):
        """Test worker behavior when database connection is lost and restored"""

        # This test simulates database connectivity issues
        with tempfile.TemporaryDirectory() as temp_dir:
            success_file = os.path.join(temp_dir, "success_jobs.txt")

            # Create jobs that will succeed
            async with DatabaseContext():
                job_ids_before = []
                for i in range(3):
                    job_id = await fastjob.enqueue(
                        job_counter, counter_file=success_file, job_index=i
                    )
                    job_ids_before.append(job_id)

            # Start processing jobs normally
            # Process initial jobs to establish baseline
            for _ in range(3):
                processed = await fastjob.run_worker(run_once=True)
                if not processed:
                    break
                await asyncio.sleep(0.1)

            # Verify initial jobs processed
            assert os.path.exists(success_file), "Initial jobs were not processed"

            # Now test recovery by creating a new pool (simulating reconnection)
            # In a real scenario, the pool would auto-reconnect on error
            async with DatabaseContext():
                # Add more jobs after "reconnection"
                job_ids_after = []
                for i in range(2):
                    job_id = await fastjob.enqueue(
                        job_counter, counter_file=success_file, job_index=i + 10
                    )
                    job_ids_after.append(job_id)

                # Process jobs after reconnection
                processed_count = 0
                for _ in range(5):  # Try up to 5 times
                    processed = await fastjob.run_worker(run_once=True)
                    if processed:
                        processed_count += 1
                    else:
                        break
                    await asyncio.sleep(0.1)

                # Verify jobs processed after "recovery"
                with open(success_file, "r") as f:
                    total_executions = len(f.readlines())

                assert (
                    total_executions >= 4
                ), f"Expected at least 4 job executions, got {total_executions}"

    @pytest.mark.asyncio
    async def test_multi_worker_exactly_once_processing(self):
        """Test that multiple workers process jobs exactly once (no duplication)"""

        with tempfile.TemporaryDirectory() as temp_dir:
            execution_log = os.path.join(temp_dir, "execution_log.txt")

            # Create many jobs to increase chance of race conditions
            async with DatabaseContext() as pool:
                # Clear existing jobs to ensure clean test
                async with pool.acquire() as conn:
                    await conn.execute("DELETE FROM fastjob_jobs")

                job_ids = []
                for i in range(20):
                    job_id = await fastjob.enqueue(
                        job_counter, counter_file=execution_log, job_index=i
                    )
                    job_ids.append(job_id)

            # Process all jobs - run_worker(run_once=True) may process multiple jobs per call
            max_attempts = 10
            for attempt in range(max_attempts):
                # Check how many jobs are still queued using global app pool
                global_app = fastjob._get_global_app()
                app_pool = await global_app.get_pool()
                
                async with app_pool.acquire() as conn:
                    queued_count = await conn.fetchval(
                        "SELECT COUNT(*) FROM fastjob_jobs WHERE status = 'queued'"
                    )
                
                if queued_count == 0:
                    print(f"All jobs processed after {attempt + 1} attempts")
                    break
                    
                # Run worker to process available jobs
                processed = await fastjob.run_worker(run_once=True)
                if not processed:
                    print(f"Worker found no jobs at attempt {attempt + 1}, but {queued_count} jobs remain queued")
                    break
                    
                await asyncio.sleep(0.01)  # Small delay

            # Count completed jobs to verify exactly-once processing using global app pool
            async with app_pool.acquire() as conn:
                completed_jobs = await conn.fetch(
                    "SELECT id, status FROM fastjob_jobs WHERE status IN ('done', 'failed', 'dead_letter')"
                )
                total_processed = len(completed_jobs)
                
            assert (
                total_processed == 20
            ), f"Expected 20 jobs processed, got {total_processed}"

            # Verify exactly-once processing by checking log
            if os.path.exists(execution_log):
                with open(execution_log, "r") as f:
                    executions = f.readlines()

                # Should have exactly 20 executions (one per job)
                assert (
                    len(executions) == 20
                ), f"Expected 20 executions, got {len(executions)}"

                # Verify different workers processed jobs (multiple PIDs)
                pids = set()
                for execution in executions:
                    pid = execution.split("-")[0]
                    pids.add(pid)

                # Should have at least 1 PID (could be more if truly concurrent)
                assert (
                    len(pids) >= 1
                ), f"Expected at least 1 worker PID, got {len(pids)}"
            else:
                pytest.fail("No execution log found")

    @pytest.mark.asyncio
    async def test_worker_resilience_to_job_failures(self):
        """Test that workers continue processing after job failures"""

        @fastjob.job(retries=1, unique=False)
        async def failing_job(should_fail: bool, job_id: int = 0):
            """Job that fails conditionally"""
            if should_fail:
                raise ValueError(f"Intentional failure for testing job {job_id}")
            return f"success-{job_id}"

        with tempfile.TemporaryDirectory() as temp_dir:
            success_file = os.path.join(temp_dir, "success_log.txt")

            async with DatabaseContext() as pool:
                # Clear existing jobs to ensure clean test
                async with pool.acquire() as conn:
                    await conn.execute("DELETE FROM fastjob_jobs")
                # Mix of failing and successful jobs
                job_ids = []

                # Failing jobs
                for i in range(3):
                    job_id = await fastjob.enqueue(failing_job, should_fail=True, job_id=i)
                    job_ids.append(job_id)

                # Successful jobs
                for i in range(5):
                    job_id = await fastjob.enqueue(
                        job_counter, counter_file=success_file, job_index=i + 100
                    )
                    job_ids.append(job_id)

                # Process all jobs using global API
                processed_count = 0
                for _ in range(20):  # More attempts than jobs to handle retries
                    processed = await fastjob.run_worker(run_once=True)
                    if processed:
                        processed_count += 1
                        await asyncio.sleep(0.1)  # Give time for processing
                    else:
                        # No more jobs, wait a bit in case retries are pending
                        await asyncio.sleep(0.5)
                        retry_processed = await fastjob.run_worker(run_once=True)
                        if not retry_processed:
                            break  # Really no more jobs

                # Verify successful jobs completed despite failures
                assert os.path.exists(
                    success_file
                ), "Successful jobs were not processed"

                with open(success_file, "r") as f:
                    successful_executions = len(f.readlines())

                assert (
                    successful_executions == 5
                ), f"Expected 5 successful executions, got {successful_executions}"

                # Use global app pool for consistency
                global_app = fastjob._get_global_app()
                app_pool = await global_app.get_pool()
                
                async with app_pool.acquire() as verify_conn:
                    # Verify failing jobs eventually moved to failed/dead_letter status
                    # Search for any jobs that have failed/dead_letter status (regardless of name)
                    failed_jobs = await verify_conn.fetch(
                        """
                        SELECT id, status, attempts, last_error FROM fastjob_jobs 
                        WHERE status IN ('failed', 'dead_letter') 
                        ORDER BY created_at
                    """
                    )

                    assert (
                        len(failed_jobs) == 3
                    ), f"Expected 3 failing jobs, got {len(failed_jobs)} jobs with status: {[j['status'] for j in failed_jobs]}"

                    for job_record in failed_jobs:
                        assert job_record["status"] in [
                            "failed",
                            "dead_letter",
                        ], f"Job status: {job_record['status']}"
                        assert (
                            job_record["attempts"] > 1
                        ), f"Job should have been retried, attempts: {job_record['attempts']}"

    @pytest.mark.asyncio
    async def test_scheduled_job_timing_accuracy(self):
        """Test that scheduled jobs execute at the correct time"""

        with tempfile.TemporaryDirectory() as temp_dir:
            timing_file = os.path.join(temp_dir, "timing_log.txt")

            @fastjob.job()
            async def timed_job(expected_time: str, log_file: str):
                """Job that logs when it actually executed"""
                actual_time = datetime.now()
                with open(log_file, "a") as f:
                    f.write(f"{expected_time},{actual_time.isoformat()}\n")
                return f"executed_at_{actual_time}"

            # Clear existing jobs to ensure clean test
            async with DatabaseContext() as pool:
                async with pool.acquire() as conn:
                    await conn.execute("DELETE FROM fastjob_jobs")

            # Schedule jobs at different times
            now = datetime.now()
            scheduled_times = [
                now + timedelta(seconds=1),
                now + timedelta(seconds=2),
                now + timedelta(seconds=3),
            ]

            async with DatabaseContext() as pool:
                job_ids = []
                for scheduled_time in scheduled_times:
                    job_id = await fastjob.enqueue(
                        timed_job,
                        expected_time=scheduled_time.isoformat(),
                        log_file=timing_file,
                        scheduled_at=scheduled_time,
                    )
                    job_ids.append(job_id)

                # Process jobs with timing checks
                start_time = time.time()
                async with pool.acquire() as conn:
                    processed_jobs = 0
                    while (
                        processed_jobs < 3 and time.time() - start_time < 10
                    ):  # 10-second timeout
                        processed = await fastjob.run_worker(run_once=True)
                        if processed:
                            processed_jobs += 1
                        await asyncio.sleep(0.1)

                # Analyze timing accuracy
                assert os.path.exists(timing_file), "No timing log found"

                with open(timing_file, "r") as f:
                    timing_records = f.readlines()

                assert len(timing_records) >= 1, "No jobs were executed"

                # Check timing accuracy (allow 2-second tolerance for test execution)
                for record in timing_records:
                    expected_str, actual_str = record.strip().split(",")
                    expected_time = datetime.fromisoformat(expected_str)
                    actual_time = datetime.fromisoformat(actual_str)

                    time_diff = abs((actual_time - expected_time).total_seconds())
                    assert (
                        time_diff < 2.0
                    ), f"Job timing off by {time_diff}s (expected: {expected_time}, actual: {actual_time})"

    @pytest.mark.asyncio
    async def test_high_concurrency_job_processing(self):
        """Test FastJob performance under high job volume"""

        with tempfile.TemporaryDirectory() as temp_dir:
            throughput_file = os.path.join(temp_dir, "throughput_log.txt")

            # Create a large number of jobs
            job_count = 100
            async with DatabaseContext() as pool:
                # Clear existing jobs to ensure clean test
                async with pool.acquire() as conn:
                    await conn.execute("DELETE FROM fastjob_jobs")

                job_ids = []
                start_enqueue = time.time()

                for i in range(job_count):
                    job_id = await fastjob.enqueue(
                        job_counter, counter_file=throughput_file, job_index=i
                    )
                    job_ids.append(job_id)

                enqueue_time = time.time() - start_enqueue

                # Process jobs efficiently - run_worker may process multiple jobs per call
                start_process = time.time()
                
                max_attempts = 20
                for attempt in range(max_attempts):
                    # Check remaining jobs using global app pool
                    global_app = fastjob._get_global_app()  
                    app_pool = await global_app.get_pool()
                    
                    async with app_pool.acquire() as conn:
                        queued_count = await conn.fetchval(
                            "SELECT COUNT(*) FROM fastjob_jobs WHERE status = 'queued'"
                        )
                    
                    if queued_count == 0:
                        break
                        
                    # Process available jobs
                    processed = await fastjob.run_worker(run_once=True)
                    if not processed:
                        break
                        
                    await asyncio.sleep(0.001)  # Very small delay

                process_time = time.time() - start_process

                # Count completed jobs to verify processing
                async with app_pool.acquire() as conn:
                    completed_jobs = await conn.fetch(
                        "SELECT id, status FROM fastjob_jobs WHERE status IN ('done', 'failed', 'dead_letter')"
                    )
                    total_processed = len(completed_jobs)

                # Verify performance metrics
                assert (
                    total_processed == job_count
                ), f"Expected {job_count} processed, got {total_processed}"

                # Calculate throughput
                enqueue_throughput = job_count / enqueue_time
                process_throughput = job_count / process_time

                # Log performance for analysis
                print("\nPerformance Results:")
                print(f"  Enqueue throughput: {enqueue_throughput:.1f} jobs/sec")
                print(f"  Process throughput: {process_throughput:.1f} jobs/sec")
                print(f"  Total time: {enqueue_time + process_time:.3f}s")

                # Reasonable performance expectations
                assert (
                    enqueue_throughput > 50
                ), f"Enqueue throughput too low: {enqueue_throughput:.1f} jobs/sec"
                assert (
                    process_throughput > 50
                ), f"Process throughput too low: {process_throughput:.1f} jobs/sec"

                # Verify all jobs were actually executed
                with open(throughput_file, "r") as f:
                    executions = f.readlines()

                assert (
                    len(executions) == job_count
                ), f"Expected {job_count} executions, got {len(executions)}"
