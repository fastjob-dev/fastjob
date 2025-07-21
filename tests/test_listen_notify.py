"""
LISTEN/NOTIFY Integration Tests for FastJob

This test suite verifies that the PostgreSQL LISTEN/NOTIFY implementation
provides instant job processing without polling delays.

Test Coverage:
- Instant job processing via LISTEN/NOTIFY
- Performance measurement and timing validation  
- Multiple queue handling with notifications
- Scheduled job processing accuracy
- Graceful fallback when notifications timeout
- Worker concurrency and isolation
- System resilience and error handling

Author: Abhinav Saxena <abhinav@apiclabs.com>
"""

import pytest
import asyncio
import time
import statistics
from datetime import datetime, timedelta
from typing import List, Dict, Any

from fastjob import job, enqueue, schedule_at, schedule_in
from fastjob.core.processor import run_worker
from tests.db_utils import create_test_database, drop_test_database, clear_table
from fastjob.db.connection import get_pool

# Test data collection
processed_jobs: List[Dict[str, Any]] = []
job_timing_data: List[float] = []

# Test job definitions with timing measurement
@job()
async def instant_timing_job(message: str, enqueue_timestamp: float):
    """Job that measures processing delay from enqueue to execution"""
    processing_delay = time.time() - enqueue_timestamp
    processed_jobs.append({
        'message': message,
        'enqueue_timestamp': enqueue_timestamp,
        'process_timestamp': time.time(),
        'delay_ms': processing_delay * 1000,
        'queue': 'default'
    })
    job_timing_data.append(processing_delay)

@job(queue="urgent")  
async def urgent_timing_job(message: str, enqueue_timestamp: float):
    """Job for urgent queue timing tests"""
    processing_delay = time.time() - enqueue_timestamp
    processed_jobs.append({
        'message': message,
        'enqueue_timestamp': enqueue_timestamp,
        'process_timestamp': time.time(),
        'delay_ms': processing_delay * 1000,
        'queue': 'urgent'
    })
    job_timing_data.append(processing_delay)

@job(queue="slow")
async def concurrent_test_job(job_id: str, duration: float):
    """Job for testing concurrent execution"""
    start_time = time.time()
    await asyncio.sleep(duration)
    end_time = time.time()
    
    processed_jobs.append({
        'job_id': job_id,
        'start_time': start_time,
        'end_time': end_time,
        'duration': end_time - start_time,
        'queue': 'slow'
    })

@job()
async def scheduled_timing_job(message: str, expected_time: float):
    """Job for testing scheduled execution accuracy"""
    actual_time = time.time()
    timing_error = actual_time - expected_time
    
    processed_jobs.append({
        'message': message,
        'expected_time': expected_time,
        'actual_time': actual_time,
        'timing_error_ms': timing_error * 1000,
        'queue': 'default'
    })

@pytest.fixture(scope="module")
async def test_db():
    """Set up test database for all tests"""
    await create_test_database()
    yield
    await drop_test_database()

@pytest.fixture
async def clean_db():
    """Clear jobs table before each test"""
    # Close any existing pools to prevent connection conflicts
    from fastjob.db.connection import close_pool
    await close_pool()
    
    # Get fresh pool and clear data
    pool = await get_pool()
    await clear_table(pool)
    processed_jobs.clear()
    job_timing_data.clear()
    yield
    
    # Additional cleanup
    processed_jobs.clear()
    job_timing_data.clear()
    await close_pool()

@pytest.fixture
async def background_worker():
    """Start a background worker for testing"""
    worker_tasks = []
    
    async def start_worker(queues=None, concurrency=2):
        if queues is None:
            queues = ["default", "urgent", "slow"]
        
        worker_task = asyncio.create_task(
            run_worker(
                concurrency=concurrency,
                run_once=False,
                queues=queues
            )
        )
        worker_tasks.append(worker_task)
        
        # Give worker time to start and set up LISTEN
        await asyncio.sleep(1.0)
        return worker_task
    
    yield start_worker
    
    # Cleanup all worker tasks
    for worker_task in worker_tasks:
        if not worker_task.done():
            worker_task.cancel()
            try:
                await asyncio.wait_for(worker_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

@pytest.mark.asyncio
async def test_instant_job_processing(test_db, clean_db, background_worker):
    """Test that LISTEN/NOTIFY provides instant job processing"""
    await background_worker()
    
    # Enqueue multiple jobs with precise timing
    job_count = 10
    enqueue_times = []
    
    for i in range(job_count):
        enqueue_time = time.time()
        enqueue_times.append(enqueue_time)
        await enqueue(instant_timing_job, message=f"instant_job_{i}", enqueue_timestamp=enqueue_time)
        # Small delay to prevent database contention
        await asyncio.sleep(0.01)
    
    # Wait for all jobs to be processed
    timeout = 10
    start_wait = time.time()
    
    while len(processed_jobs) < job_count and (time.time() - start_wait) < timeout:
        await asyncio.sleep(0.1)
    
    # Analyze results
    assert len(processed_jobs) == job_count, f"Expected {job_count} jobs, processed {len(processed_jobs)}"
    
    delays_ms = [job['delay_ms'] for job in processed_jobs]
    avg_delay_ms = statistics.mean(delays_ms)
    max_delay_ms = max(delays_ms)
    
    # Jobs should be processed very quickly with LISTEN/NOTIFY
    # Allow up to 500ms average (much better than 1s polling would provide)
    assert avg_delay_ms < 500, f"Average delay {avg_delay_ms:.1f}ms too high - LISTEN/NOTIFY may not be working"
    
    # At least 80% of jobs should be processed in under 200ms
    fast_jobs = len([d for d in delays_ms if d < 200])
    fast_percentage = (fast_jobs / job_count) * 100
    assert fast_percentage >= 80, f"Only {fast_percentage:.1f}% of jobs processed quickly (expected ≥80%)"
    
    print(f"✅ Processed {job_count} jobs with avg delay {avg_delay_ms:.1f}ms (max: {max_delay_ms:.1f}ms)")

@pytest.mark.asyncio
async def test_multiple_queue_notifications(test_db, clean_db, background_worker):
    """Test that LISTEN/NOTIFY works correctly with multiple queues"""
    await background_worker(queues=["default", "urgent"])
    
    # Enqueue jobs to different queues simultaneously
    job_count_per_queue = 5
    enqueue_tasks = []
    
    # Create jobs for both queues
    for i in range(job_count_per_queue):
        enqueue_time = time.time()
        enqueue_tasks.extend([
            enqueue(instant_timing_job, message=f"default_{i}", enqueue_timestamp=enqueue_time),
            enqueue(urgent_timing_job, message=f"urgent_{i}", enqueue_timestamp=enqueue_time)
        ])
    
    await asyncio.gather(*enqueue_tasks)
    
    # Wait for processing
    total_jobs = job_count_per_queue * 2
    timeout = 15
    start_wait = time.time()
    
    while len(processed_jobs) < total_jobs and (time.time() - start_wait) < timeout:
        await asyncio.sleep(0.1)
    
    # Verify all jobs processed
    assert len(processed_jobs) == total_jobs, f"Expected {total_jobs} jobs, got {len(processed_jobs)}"
    
    # Separate jobs by queue
    default_jobs = [j for j in processed_jobs if j['queue'] == 'default']
    urgent_jobs = [j for j in processed_jobs if j['queue'] == 'urgent']
    
    assert len(default_jobs) == job_count_per_queue, f"Expected {job_count_per_queue} default jobs"
    assert len(urgent_jobs) == job_count_per_queue, f"Expected {job_count_per_queue} urgent jobs"
    
    # Both queues should have good performance
    all_delays = [j['delay_ms'] for j in processed_jobs]
    avg_delay = statistics.mean(all_delays)
    assert avg_delay < 500, f"Multi-queue average delay {avg_delay:.1f}ms too high"
    
    print(f"✅ Processed {len(default_jobs)} default + {len(urgent_jobs)} urgent jobs (avg: {avg_delay:.1f}ms)")

@pytest.mark.asyncio
async def test_scheduled_job_processing(test_db, clean_db, background_worker):
    """Test that scheduled jobs are processed at the correct time"""
    await background_worker()
    
    # Schedule jobs for the near future
    current_time = time.time()
    schedule_delays = [1, 2, 3]  # seconds from now
    
    for i, delay in enumerate(schedule_delays):
        schedule_time = datetime.fromtimestamp(current_time + delay)
        await schedule_at(
            scheduled_timing_job,
            when=schedule_time,
            message=f"scheduled_{i}",
            expected_time=current_time + delay
        )
    
    # Wait for all jobs to execute (with buffer)
    await asyncio.sleep(max(schedule_delays) + 2)
    
    # Verify all scheduled jobs executed
    scheduled_jobs = [j for j in processed_jobs if 'timing_error_ms' in j]
    assert len(scheduled_jobs) == len(schedule_delays), f"Expected {len(schedule_delays)} scheduled jobs"
    
    # Check timing accuracy (should be within 1 second)
    timing_errors = [abs(j['timing_error_ms']) for j in scheduled_jobs]
    max_error_ms = max(timing_errors)
    avg_error_ms = statistics.mean(timing_errors)
    
    assert max_error_ms < 1000, f"Scheduled job timing error too high: {max_error_ms:.1f}ms"
    
    print(f"✅ Scheduled jobs executed with avg timing error: {avg_error_ms:.1f}ms")

@pytest.mark.asyncio 
async def test_worker_concurrency(test_db, clean_db, background_worker):
    """Test that multiple workers can process jobs concurrently"""
    await background_worker(queues=["slow"], concurrency=2)
    
    # Enqueue jobs that take time to complete
    job_count = 4
    job_duration = 1.0  # seconds
    
    enqueue_tasks = []
    for i in range(job_count):
        enqueue_tasks.append(
            enqueue(concurrent_test_job, job_id=f"concurrent_{i}", duration=job_duration)
        )
    
    start_time = time.time()
    await asyncio.gather(*enqueue_tasks)
    
    # Wait for jobs to complete
    await asyncio.sleep(job_duration + 2.0)  # Buffer time
    
    total_time = time.time() - start_time
    
    # Verify all jobs completed
    concurrent_jobs = [j for j in processed_jobs if j['queue'] == 'slow']
    assert len(concurrent_jobs) == job_count, f"Expected {job_count} concurrent jobs"
    
    # If jobs ran sequentially: ~4 seconds
    # If jobs ran concurrently with 2 workers: ~2-3 seconds
    sequential_time = job_count * job_duration
    assert total_time < (sequential_time * 0.8), f"Jobs may have run sequentially ({total_time:.1f}s vs expected ~{job_duration + 1:.1f}s for concurrent)"
    
    print(f"✅ {job_count} concurrent jobs completed in {total_time:.1f}s (saved ~{sequential_time - total_time:.1f}s)")

@pytest.mark.asyncio
async def test_notification_fallback_mechanism(test_db, clean_db, background_worker):
    """Test that the system works even when relying on timeout fallback"""
    await background_worker(concurrency=1)
    
    # This test verifies the 5-second timeout fallback works
    # We can't easily disable NOTIFY, but we can test that jobs
    # are processed even if there's a delay in notification handling
    
    enqueue_time = time.time()
    await enqueue(instant_timing_job, message="fallback_test", enqueue_timestamp=enqueue_time)
    
    # Wait for processing with generous timeout
    timeout = 8  # Longer than the 5-second worker timeout
    start_wait = time.time()
    
    while len(processed_jobs) == 0 and (time.time() - start_wait) < timeout:
        await asyncio.sleep(0.5)
    
    # Job should be processed within the timeout period
    assert len(processed_jobs) == 1, "Job not processed - fallback mechanism failed"
    
    delay_ms = processed_jobs[0]['delay_ms']
    
    # With LISTEN/NOTIFY working, should be fast
    # With only fallback, could be up to 5 seconds + processing time
    print(f"✅ Fallback test job processed with {delay_ms:.1f}ms delay")

@pytest.mark.asyncio
async def test_rapid_job_enqueueing(test_db, clean_db, background_worker):
    """Test system performance with rapid job enqueueing"""
    await background_worker(concurrency=3)
    
    # Rapidly enqueue many jobs to test LISTEN/NOTIFY efficiency
    job_count = 25
    enqueue_start = time.time()
    
    enqueue_tasks = []
    for i in range(job_count):
        enqueue_time = time.time()
        enqueue_tasks.append(
            enqueue(instant_timing_job, message=f"rapid_{i}", enqueue_timestamp=enqueue_time)
        )
    
    await asyncio.gather(*enqueue_tasks)
    enqueue_duration = time.time() - enqueue_start
    
    # Wait for all jobs to complete
    timeout = 15
    start_wait = time.time()
    
    while len(processed_jobs) < job_count and (time.time() - start_wait) < timeout:
        await asyncio.sleep(0.1)
    
    total_processing_time = time.time() - start_wait
    
    # Verify all jobs processed
    assert len(processed_jobs) == job_count, f"Only {len(processed_jobs)}/{job_count} jobs processed"
    
    # Calculate performance metrics
    delays_ms = [j['delay_ms'] for j in processed_jobs]
    avg_delay = statistics.mean(delays_ms)
    throughput = job_count / total_processing_time
    
    # Performance assertions
    assert avg_delay < 300, f"Average delay too high for rapid processing: {avg_delay:.1f}ms"
    assert throughput > 5, f"Throughput too low: {throughput:.1f} jobs/sec"
    
    print(f"✅ Rapid processing: {job_count} jobs in {total_processing_time:.2f}s")
    print(f"   Throughput: {throughput:.1f} jobs/sec, Avg delay: {avg_delay:.1f}ms")

@pytest.mark.asyncio
async def test_listen_notify_vs_polling_performance(test_db, clean_db, background_worker):
    """Performance comparison showing LISTEN/NOTIFY advantage over theoretical polling"""
    await background_worker(concurrency=2)
    
    # Test with moderate job load
    job_count = 15
    
    processing_start = time.time()
    enqueue_tasks = []
    
    for i in range(job_count):
        enqueue_time = time.time()
        enqueue_tasks.append(
            enqueue(instant_timing_job, message=f"perf_{i}", enqueue_timestamp=enqueue_time)
        )
    
    await asyncio.gather(*enqueue_tasks)
    
    # Wait for processing
    while len(processed_jobs) < job_count:
        await asyncio.sleep(0.1)
    
    # Performance analysis
    delays = job_timing_data
    avg_delay = statistics.mean(delays)
    
    # Compare with theoretical 1-second polling (average 500ms delay)
    theoretical_polling_delay = 0.5  # 500ms average
    performance_improvement = theoretical_polling_delay / avg_delay if avg_delay > 0 else float('inf')
    
    print(f"✅ Performance Analysis:")
    print(f"   LISTEN/NOTIFY delay: {avg_delay*1000:.1f}ms")
    print(f"   Theoretical polling: 500ms average")
    print(f"   Performance improvement: {performance_improvement:.1f}x faster")
    
    # LISTEN/NOTIFY should be significantly faster than polling
    assert avg_delay < 0.4, f"LISTEN/NOTIFY not providing expected performance benefit"
    assert performance_improvement > 2, f"Only {performance_improvement:.1f}x improvement over polling"

@pytest.mark.asyncio
async def test_worker_isolation(test_db, clean_db, background_worker):
    """Test that multiple workers don't interfere with each other"""
    await background_worker(concurrency=3, queues=["default"])
    
    # Enqueue jobs that should be processed by different workers
    job_count = 9  # Should distribute across 3 workers
    
    enqueue_tasks = []
    for i in range(job_count):
        enqueue_time = time.time()
        enqueue_tasks.append(
            enqueue(instant_timing_job, message=f"isolation_{i}", enqueue_timestamp=enqueue_time)
        )
    
    await asyncio.gather(*enqueue_tasks)
    
    # Wait for processing
    timeout = 10
    start_wait = time.time()
    
    while len(processed_jobs) < job_count and (time.time() - start_wait) < timeout:
        await asyncio.sleep(0.1)
    
    # All jobs should be processed
    assert len(processed_jobs) == job_count, f"Worker isolation failed - only {len(processed_jobs)} jobs processed"
    
    # Performance should be good (workers not blocking each other)
    delays_ms = [j['delay_ms'] for j in processed_jobs]
    avg_delay = statistics.mean(delays_ms)
    assert avg_delay < 400, f"Worker isolation may have performance issues: {avg_delay:.1f}ms avg delay"
    
    print(f"✅ Worker isolation test: {job_count} jobs processed with {avg_delay:.1f}ms avg delay")

# Performance summary test
@pytest.mark.asyncio
async def test_overall_listen_notify_performance(test_db, clean_db, background_worker):
    """Overall performance validation of LISTEN/NOTIFY implementation"""
    await background_worker(concurrency=2)
    
    # Comprehensive test with mixed job types
    test_jobs = [
        ("instant", 5),
        ("rapid", 10),
        ("mixed_queue", 8)
    ]
    
    all_results = []
    
    for test_type, count in test_jobs:
        processed_jobs.clear()
        job_timing_data.clear()
        
        # Enqueue jobs for this test
        for i in range(count):
            enqueue_time = time.time()
            await enqueue(instant_timing_job, message=f"{test_type}_{i}", enqueue_timestamp=enqueue_time)
        
        # Wait for processing
        start_wait = time.time()
        while len(processed_jobs) < count and (time.time() - start_wait) < 10:
            await asyncio.sleep(0.05)
        
        # Collect results
        if len(processed_jobs) == count:
            delays = [j['delay_ms'] for j in processed_jobs]
            all_results.append({
                'test_type': test_type,
                'job_count': count,
                'avg_delay_ms': statistics.mean(delays),
                'max_delay_ms': max(delays),
                'success': True
            })
        else:
            all_results.append({
                'test_type': test_type,
                'job_count': count,
                'processed': len(processed_jobs),
                'success': False
            })
    
    # Verify all tests passed
    successful_tests = [r for r in all_results if r['success']]
    assert len(successful_tests) == len(test_jobs), "Some performance tests failed"
    
    # Overall performance metrics
    overall_avg_delay = statistics.mean([r['avg_delay_ms'] for r in successful_tests])
    overall_max_delay = max([r['max_delay_ms'] for r in successful_tests])
    
    print(f"✅ Overall LISTEN/NOTIFY Performance:")
    print(f"   Average delay across all tests: {overall_avg_delay:.1f}ms")
    print(f"   Maximum delay observed: {overall_max_delay:.1f}ms") 
    
    # Final assertion: LISTEN/NOTIFY should provide excellent performance
    assert overall_avg_delay < 250, f"Overall performance not meeting expectations: {overall_avg_delay:.1f}ms"
    
    print("🎉 LISTEN/NOTIFY implementation working excellently!")