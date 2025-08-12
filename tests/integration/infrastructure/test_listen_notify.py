"""
LISTEN/NOTIFY Integration Tests for FastJob (Fixed Version)

This test suite verifies that the PostgreSQL LISTEN/NOTIFY implementation
provides instant job processing without polling delays.

This version avoids the complex isolation issues of the original by:
1. Using instance-based API for better isolation
2. Properly managing job registration per test
3. Avoiding global state conflicts
4. Using cleaner resource management

Author: Abhinav Saxena <abhinav@apiclabs.com>
"""

import pytest
import asyncio
import time
import statistics
import os
from datetime import datetime
from typing import List, Dict, Any

from fastjob import FastJob
from tests.db_utils import create_test_database, drop_test_database, clear_table


# Global state for test results (cleared before each test)
test_results: List[Dict[str, Any]] = []


@pytest.fixture(scope="module")
async def test_db():
    """Set up test database for all tests"""
    await create_test_database()
    yield
    await drop_test_database()


@pytest.fixture
async def clean_app():
    """Create a clean FastJob instance for testing with proper isolation"""
    # Clear previous test results
    test_results.clear()
    
    # Disable plugins to avoid conflicts
    from fastjob.testing import disable_plugins
    disable_plugins()
    
    # Create isolated FastJob instance
    app = FastJob(
        database_url=os.environ.get("FASTJOB_DATABASE_URL", "postgresql://postgres@localhost/fastjob_test")
    )
    
    # Clear the jobs table
    pool = await app.get_pool()
    await clear_table(pool)
    
    yield app
    
    # Cleanup
    await app.close()
    test_results.clear()


@pytest.mark.asyncio
async def test_instant_job_processing_instance_api(test_db, clean_app):
    """Test that LISTEN/NOTIFY provides instant job processing using instance API"""
    app = clean_app
    
    # Define job function that records timing
    @app.job()
    async def timing_job(message: str, enqueue_timestamp: float):
        processing_delay = time.time() - enqueue_timestamp
        test_results.append({
            "message": message,
            "delay_ms": processing_delay * 1000,
            "enqueue_timestamp": enqueue_timestamp,
            "process_timestamp": time.time(),
        })
    
    # Start worker in background
    worker_task = asyncio.create_task(app.run_worker(concurrency=1, run_once=False))
    
    try:
        # Give worker time to start and set up LISTEN
        await asyncio.sleep(1.0)
        
        # Enqueue jobs for testing
        job_count = 3
        enqueue_times = []
        
        for i in range(job_count):
            enqueue_time = time.time()
            enqueue_times.append(enqueue_time)
            await app.enqueue(
                timing_job,
                message=f"instant_job_{i}",
                enqueue_timestamp=enqueue_time,
            )
            await asyncio.sleep(0.1)  # Small delay between enqueues
        
        # Wait for jobs to be processed with reasonable timeout
        timeout = 10
        start_wait = time.time()
        
        while len(test_results) < job_count and (time.time() - start_wait) < timeout:
            await asyncio.sleep(0.1)
        
        # Verify all jobs were processed
        assert len(test_results) == job_count, f"Expected {job_count} jobs, got {len(test_results)}"
        
        # Verify timing performance (LISTEN/NOTIFY should be fast)
        delays_ms = [result["delay_ms"] for result in test_results]
        avg_delay_ms = statistics.mean(delays_ms)
        max_delay_ms = max(delays_ms)
        
        print(f"✅ Processed {len(test_results)} jobs:")
        print(f"   Average delay: {avg_delay_ms:.1f}ms")
        print(f"   Maximum delay: {max_delay_ms:.1f}ms")
        
        # Performance assertions - LISTEN/NOTIFY should provide fast processing
        assert avg_delay_ms < 500, f"Average delay too high: {avg_delay_ms:.1f}ms"
        assert max_delay_ms < 1000, f"Maximum delay too high: {max_delay_ms:.1f}ms"
        
    finally:
        # Cleanup worker
        worker_task.cancel()
        try:
            await asyncio.wait_for(worker_task, timeout=3.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass


@pytest.mark.asyncio  
async def test_scheduled_job_timing(test_db, clean_app):
    """Test that scheduled jobs are processed at the correct time with LISTEN/NOTIFY"""
    app = clean_app
    
    @app.job()
    async def scheduled_job(message: str, expected_time: float):
        actual_time = time.time()
        timing_error_ms = (actual_time - expected_time) * 1000
        test_results.append({
            "message": message,
            "expected_time": expected_time,
            "actual_time": actual_time,
            "timing_error_ms": timing_error_ms,
        })
    
    # Start worker
    worker_task = asyncio.create_task(app.run_worker(concurrency=1, run_once=False))
    
    try:
        await asyncio.sleep(1.0)  # Let worker start
        
        # Schedule jobs for near future
        current_time = time.time()
        schedule_delays = [1.0, 2.0, 3.0]  # seconds from now
        
        for i, delay in enumerate(schedule_delays):
            schedule_time = datetime.fromtimestamp(current_time + delay)
            await app.schedule(
                scheduled_job,
                run_at=schedule_time,
                message=f"scheduled_{i}",
                expected_time=current_time + delay,
            )
        
        # Wait for all scheduled jobs to execute
        total_wait = max(schedule_delays) + 5  # Extra buffer
        await asyncio.sleep(total_wait)
        
        # Verify all jobs executed
        assert len(test_results) == len(schedule_delays), \
            f"Expected {len(schedule_delays)} jobs, got {len(test_results)}"
        
        # Check timing accuracy
        timing_errors = [abs(result["timing_error_ms"]) for result in test_results]
        avg_error_ms = statistics.mean(timing_errors)
        max_error_ms = max(timing_errors)
        
        print(f"✅ Scheduled {len(test_results)} jobs:")
        print(f"   Average timing error: {avg_error_ms:.1f}ms")
        print(f"   Maximum timing error: {max_error_ms:.1f}ms")
        
        # Timing should be reasonably accurate (within 5 seconds due to worker timeout mechanism)
        assert max_error_ms < 6000, f"Timing error too high: {max_error_ms:.1f}ms"
        
    finally:
        worker_task.cancel()
        try:
            await asyncio.wait_for(worker_task, timeout=3.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass


@pytest.mark.asyncio
async def test_multiple_queue_processing(test_db, clean_app):
    """Test LISTEN/NOTIFY with multiple queues"""
    app = clean_app
    
    @app.job(queue="high")
    async def high_priority_job(message: str, enqueue_time: float):
        test_results.append({
            "message": message,
            "queue": "high",
            "delay_ms": (time.time() - enqueue_time) * 1000,
        })
    
    @app.job(queue="normal")
    async def normal_job(message: str, enqueue_time: float):
        test_results.append({
            "message": message,
            "queue": "normal", 
            "delay_ms": (time.time() - enqueue_time) * 1000,
        })
    
    # Start worker that processes both queues
    worker_task = asyncio.create_task(
        app.run_worker(concurrency=2, queues=["high", "normal"], run_once=False)
    )
    
    try:
        await asyncio.sleep(1.0)  # Let worker start
        
        # Enqueue jobs to both queues
        jobs_per_queue = 3
        enqueue_tasks = []
        
        for i in range(jobs_per_queue):
            enqueue_time = time.time()
            enqueue_tasks.extend([
                app.enqueue(high_priority_job, message=f"high_{i}", enqueue_time=enqueue_time),
                app.enqueue(normal_job, message=f"normal_{i}", enqueue_time=enqueue_time),
            ])
        
        await asyncio.gather(*enqueue_tasks)
        
        # Wait for processing
        total_jobs = jobs_per_queue * 2
        timeout = 10
        start_wait = time.time()
        
        while len(test_results) < total_jobs and (time.time() - start_wait) < timeout:
            await asyncio.sleep(0.1)
        
        # Verify all jobs processed
        assert len(test_results) == total_jobs, f"Expected {total_jobs} jobs, got {len(test_results)}"
        
        # Verify both queues processed
        high_jobs = [r for r in test_results if r["queue"] == "high"]
        normal_jobs = [r for r in test_results if r["queue"] == "normal"]
        
        assert len(high_jobs) == jobs_per_queue, f"Expected {jobs_per_queue} high priority jobs"
        assert len(normal_jobs) == jobs_per_queue, f"Expected {jobs_per_queue} normal jobs"
        
        # Verify performance across both queues
        all_delays = [r["delay_ms"] for r in test_results]
        avg_delay = statistics.mean(all_delays)
        
        print(f"✅ Multi-queue processing:")
        print(f"   High priority jobs: {len(high_jobs)}")
        print(f"   Normal priority jobs: {len(normal_jobs)}")
        print(f"   Average delay: {avg_delay:.1f}ms")
        
        assert avg_delay < 500, f"Multi-queue delay too high: {avg_delay:.1f}ms"
        
    finally:
        worker_task.cancel()
        try:
            await asyncio.wait_for(worker_task, timeout=3.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass


@pytest.mark.asyncio
async def test_rapid_job_processing(test_db, clean_app):
    """Test LISTEN/NOTIFY performance with rapid job enqueueing"""
    app = clean_app
    
    @app.job()
    async def rapid_job(job_id: int, enqueue_time: float):
        test_results.append({
            "job_id": job_id,
            "delay_ms": (time.time() - enqueue_time) * 1000,
        })
    
    # Start worker with higher concurrency
    worker_task = asyncio.create_task(app.run_worker(concurrency=3, run_once=False))
    
    try:
        await asyncio.sleep(1.0)  # Let worker start
        
        # Rapidly enqueue many jobs
        job_count = 20
        enqueue_start = time.time()
        
        enqueue_tasks = []
        for i in range(job_count):
            enqueue_time = time.time()
            enqueue_tasks.append(
                app.enqueue(rapid_job, job_id=i, enqueue_time=enqueue_time)
            )
        
        await asyncio.gather(*enqueue_tasks)
        enqueue_duration = time.time() - enqueue_start
        
        # Wait for all jobs to complete
        timeout = 15
        start_wait = time.time()
        
        while len(test_results) < job_count and (time.time() - start_wait) < timeout:
            await asyncio.sleep(0.1)
        
        total_processing_time = time.time() - start_wait
        
        # Verify all jobs processed
        assert len(test_results) == job_count, f"Only {len(test_results)}/{job_count} jobs processed"
        
        # Calculate performance metrics
        delays = [r["delay_ms"] for r in test_results]
        avg_delay = statistics.mean(delays)
        throughput = job_count / total_processing_time
        
        print(f"✅ Rapid processing performance:")
        print(f"   Jobs: {job_count}")
        print(f"   Enqueue time: {enqueue_duration:.2f}s") 
        print(f"   Processing time: {total_processing_time:.2f}s")
        print(f"   Throughput: {throughput:.1f} jobs/sec")
        print(f"   Average delay: {avg_delay:.1f}ms")
        
        # Performance assertions
        assert avg_delay < 300, f"Average delay too high: {avg_delay:.1f}ms"
        assert throughput > 3, f"Throughput too low: {throughput:.1f} jobs/sec"
        
    finally:
        worker_task.cancel()
        try:
            await asyncio.wait_for(worker_task, timeout=3.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass


@pytest.mark.asyncio
async def test_listen_notify_performance_comparison(test_db, clean_app):
    """Performance comparison showing LISTEN/NOTIFY advantage over theoretical polling"""
    app = clean_app
    
    @app.job()
    async def perf_job(job_id: int, enqueue_time: float):
        test_results.append({
            "job_id": job_id,
            "delay_ms": (time.time() - enqueue_time) * 1000,
        })
    
    # Start worker
    worker_task = asyncio.create_task(app.run_worker(concurrency=2, run_once=False))
    
    try:
        await asyncio.sleep(1.0)
        
        # Process moderate job load
        job_count = 10
        
        enqueue_tasks = []
        for i in range(job_count):
            enqueue_time = time.time()
            enqueue_tasks.append(
                app.enqueue(perf_job, job_id=i, enqueue_time=enqueue_time)
            )
        
        await asyncio.gather(*enqueue_tasks)
        
        # Wait for processing
        while len(test_results) < job_count:
            await asyncio.sleep(0.1)
        
        # Performance analysis
        delays = [r["delay_ms"] for r in test_results]
        avg_delay = statistics.mean(delays)
        
        # Compare with theoretical 1-second polling (average 500ms delay)
        theoretical_polling_delay = 500  # ms
        performance_improvement = (
            theoretical_polling_delay / avg_delay if avg_delay > 0 else float("inf")
        )
        
        print(f"✅ Performance comparison:")
        print(f"   LISTEN/NOTIFY delay: {avg_delay:.1f}ms")
        print(f"   Theoretical polling: {theoretical_polling_delay}ms")
        print(f"   Performance improvement: {performance_improvement:.1f}x faster")
        
        # LISTEN/NOTIFY should be significantly faster than polling
        assert avg_delay < 400, f"LISTEN/NOTIFY not fast enough: {avg_delay:.1f}ms"
        assert performance_improvement > 2, f"Only {performance_improvement:.1f}x improvement"
        
    finally:
        worker_task.cancel()
        try:
            await asyncio.wait_for(worker_task, timeout=3.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass