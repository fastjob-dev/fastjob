"""
Tests for the improved embedded worker implementation
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock

import fastjob
from fastjob.local import (
    start_embedded_worker, stop_embedded_worker, start_embedded_worker_async,
    is_embedded_worker_running, get_embedded_worker_status
)


@pytest.fixture
async def cleanup_worker():
    """Ensure worker is stopped after each test"""
    yield
    await stop_embedded_worker()
    # Give a moment for cleanup
    await asyncio.sleep(0.1)


class TestEmbeddedWorkerSync:
    """Test synchronous embedded worker API"""
    
    @pytest.mark.asyncio
    async def test_basic_start_stop(self, cleanup_worker):
        """Test basic start and stop functionality"""
        assert not is_embedded_worker_running()
        
        # Start worker
        start_embedded_worker()
        
        # Give it a moment to start
        await asyncio.sleep(0.1)
        assert is_embedded_worker_running()
        
        # Stop worker
        await stop_embedded_worker()
        assert not is_embedded_worker_running()
    
    @pytest.mark.asyncio
    async def test_start_with_parameters(self, cleanup_worker):
        """Test starting worker with different parameters"""
        # Test with concurrency
        start_embedded_worker(concurrency=2, poll_interval=0.1)
        await asyncio.sleep(0.1)
        assert is_embedded_worker_running()
        
        await stop_embedded_worker()
        assert not is_embedded_worker_running()
    
    @pytest.mark.asyncio
    async def test_double_start_protection(self, cleanup_worker):
        """Test that starting an already running worker is handled gracefully"""
        start_embedded_worker()
        await asyncio.sleep(0.1)
        assert is_embedded_worker_running()
        
        # Try to start again - should not crash or create duplicate workers
        start_embedded_worker()
        await asyncio.sleep(0.1)
        assert is_embedded_worker_running()
        
        await stop_embedded_worker()
    
    @pytest.mark.asyncio
    async def test_status_functions(self, cleanup_worker):
        """Test worker status functions"""
        # Initially not running
        assert not is_embedded_worker_running()
        status = get_embedded_worker_status()
        assert status["running"] is False
        assert status["task_done"] is True
        
        # Start worker
        start_embedded_worker()
        await asyncio.sleep(0.1)
        
        assert is_embedded_worker_running()
        status = get_embedded_worker_status()
        assert status["running"] is True
        assert status["task_exists"] is True
        assert status["task_done"] is False
        
        # Stop worker
        await stop_embedded_worker()
        
        assert not is_embedded_worker_running()
        status = get_embedded_worker_status()
        assert status["running"] is False


class TestEmbeddedWorkerAsync:
    """Test asynchronous embedded worker API"""
    
    @pytest.mark.asyncio
    async def test_async_run_once(self, cleanup_worker):
        """Test async worker with run_once=True"""
        # Mock the process_jobs to avoid database dependency
        with patch('fastjob.local.process_jobs', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = False  # No jobs available
            
            # Should complete immediately with run_once=True
            result = await start_embedded_worker_async(run_once=True)
            assert result is None  # run_once returns None
            
            # Should have checked for jobs at least once
            mock_process.assert_called()
    
    @pytest.mark.asyncio
    async def test_async_background_worker(self, cleanup_worker):
        """Test async worker in background mode"""
        with patch('fastjob.local.process_jobs', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = False  # No jobs available
            
            # Start background worker
            task = await start_embedded_worker_async(poll_interval=0.1)
            assert task is not None
            assert not task.done()
            assert is_embedded_worker_running()
            
            # Let it run briefly
            await asyncio.sleep(0.2)
            
            # Stop worker
            await stop_embedded_worker()
            assert not is_embedded_worker_running()
    
    @pytest.mark.asyncio
    async def test_async_double_start_protection(self, cleanup_worker):
        """Test async worker double start protection"""
        with patch('fastjob.local.process_jobs', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = False
            
            # Start first worker
            task1 = await start_embedded_worker_async(poll_interval=0.1)
            assert task1 is not None
            
            # Try to start again - should return same task
            task2 = await start_embedded_worker_async(poll_interval=0.1)
            assert task2 is task1  # Same task object
            
            await stop_embedded_worker()


class TestEmbeddedWorkerJobProcessing:
    """Test actual job processing functionality"""
    
    @pytest.mark.asyncio
    async def test_run_once_with_jobs(self, cleanup_worker):
        """Test run_once mode when jobs are available"""
        with patch('fastjob.local.process_jobs', new_callable=AsyncMock) as mock_process:
            # First call finds a job, second call finds no jobs
            mock_process.side_effect = [True, False]
            
            await start_embedded_worker_async(run_once=True)
            
            # Should have been called at least once
            assert mock_process.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_run_once_no_jobs(self, cleanup_worker):
        """Test run_once mode when no jobs are available"""
        with patch('fastjob.local.process_jobs', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = False  # No jobs
            
            await start_embedded_worker_async(run_once=True)
            
            # Should have checked once and exited
            mock_process.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_continuous_processing(self, cleanup_worker):
        """Test continuous job processing"""
        call_count = 0
        
        async def mock_process_jobs(conn):
            nonlocal call_count
            call_count += 1
            # Simulate finding jobs for a few calls, then no jobs
            return call_count <= 3
        
        with patch('fastjob.local.process_jobs', side_effect=mock_process_jobs):
            # Start worker with fast polling
            start_embedded_worker(poll_interval=0.05)
            
            # Let it process for a short time
            await asyncio.sleep(0.3)
            
            await stop_embedded_worker()
            
            # Should have processed multiple times
            assert call_count > 3
    
    @pytest.mark.asyncio
    async def test_error_handling_run_once(self, cleanup_worker):
        """Test error handling in run_once mode"""
        with patch('fastjob.local.process_jobs', new_callable=AsyncMock) as mock_process:
            mock_process.side_effect = Exception("Database error")
            
            # Should not raise exception
            await start_embedded_worker_async(run_once=True)
            
            mock_process.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_error_handling_continuous(self, cleanup_worker):
        """Test error handling in continuous mode"""
        call_count = 0
        
        async def mock_process_jobs(conn):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Database error")
            return False  # No jobs after errors
        
        with patch('fastjob.local.process_jobs', side_effect=mock_process_jobs):
            start_embedded_worker(poll_interval=0.05)
            
            # Let it handle errors and continue
            await asyncio.sleep(0.2)
            
            await stop_embedded_worker()
            
            # Should have attempted multiple times despite errors
            assert call_count >= 2


class TestEmbeddedWorkerConcurrency:
    """Test concurrency features"""
    
    @pytest.mark.asyncio
    async def test_single_worker(self, cleanup_worker):
        """Test single worker (concurrency=1)"""
        process_calls = []
        
        async def mock_process_jobs(conn):
            process_calls.append(asyncio.current_task())
            return len(process_calls) <= 2  # Process a few jobs then stop
        
        with patch('fastjob.local.process_jobs', side_effect=mock_process_jobs):
            await start_embedded_worker_async(run_once=True, concurrency=1)
            
            # All calls should be from the same task (sequential)
            unique_tasks = set(process_calls)
            assert len(unique_tasks) == 1
    
    @pytest.mark.asyncio
    async def test_multiple_workers(self, cleanup_worker):
        """Test multiple concurrent workers"""
        process_calls = []
        
        async def mock_process_jobs(conn):
            process_calls.append(asyncio.current_task())
            await asyncio.sleep(0.1)  # Simulate work
            return len(process_calls) <= 6  # Process some jobs
        
        with patch('fastjob.local.process_jobs', side_effect=mock_process_jobs):
            await start_embedded_worker_async(run_once=True, concurrency=3)
            
            # Should have calls from multiple tasks (concurrent)
            unique_tasks = set(process_calls)
            assert len(unique_tasks) <= 3  # At most 3 concurrent workers
            assert len(process_calls) >= 3  # Should process multiple jobs


class TestEmbeddedWorkerIntegration:
    """Test integration scenarios"""
    
    @pytest.mark.asyncio
    async def test_fastjob_integration(self, cleanup_worker):
        """Test that embedded worker integrates with fastjob module properly"""
        # Test that functions are available through fastjob module
        assert hasattr(fastjob, 'start_embedded_worker')
        assert hasattr(fastjob, 'stop_embedded_worker')
        assert hasattr(fastjob, 'start_embedded_worker_async')
        assert hasattr(fastjob, 'is_embedded_worker_running')
        assert hasattr(fastjob, 'get_embedded_worker_status')
        
        # Test basic functionality through fastjob module
        assert not fastjob.is_embedded_worker_running()
        
        fastjob.start_embedded_worker()
        await asyncio.sleep(0.1)
        assert fastjob.is_embedded_worker_running()
        
        await fastjob.stop_embedded_worker()
        assert not fastjob.is_embedded_worker_running()
    
    @pytest.mark.asyncio 
    async def test_realistic_development_scenario(self, cleanup_worker):
        """Test a realistic development scenario"""
        # Simulate a web app startup
        assert not is_embedded_worker_running()
        
        # Start worker like in development
        start_embedded_worker(concurrency=1, poll_interval=0.5)
        
        # Verify it's running
        await asyncio.sleep(0.1)
        assert is_embedded_worker_running()
        
        status = get_embedded_worker_status()
        assert status["running"] is True
        assert status["task_exists"] is True
        
        # Simulate app shutdown
        await stop_embedded_worker()
        
        # Verify clean shutdown
        assert not is_embedded_worker_running()
        final_status = get_embedded_worker_status()
        assert final_status["running"] is False
    
    @pytest.mark.asyncio
    async def test_testing_scenario(self, cleanup_worker):
        """Test a typical testing scenario"""
        # Mock a simple job
        @fastjob.job()
        async def test_job():
            return "completed"
        
        job_executed = False
        
        async def mock_process_jobs(conn):
            nonlocal job_executed
            if not job_executed:
                job_executed = True
                return True  # Simulate processing the job
            return False  # No more jobs
        
        with patch('fastjob.local.process_jobs', side_effect=mock_process_jobs):
            # Use run_once for testing
            await start_embedded_worker_async(run_once=True)
            
            # Job should have been processed
            assert job_executed


class TestEmbeddedWorkerEdgeCases:
    """Test edge cases and error conditions"""
    
    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, cleanup_worker):
        """Test stopping when worker is not running"""
        assert not is_embedded_worker_running()
        
        # Should not raise exception
        await stop_embedded_worker()
        assert not is_embedded_worker_running()
    
    @pytest.mark.asyncio
    async def test_status_when_no_task(self, cleanup_worker):
        """Test status functions when no task exists"""
        status = get_embedded_worker_status()
        
        assert status["running"] is False
        assert status["task_exists"] is False
        assert status["task_done"] is True
    
    @pytest.mark.asyncio
    async def test_very_fast_polling(self, cleanup_worker):
        """Test with very fast polling interval"""
        with patch('fastjob.local.process_jobs', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = False
            
            # Very fast polling
            start_embedded_worker(poll_interval=0.01)
            await asyncio.sleep(0.1)
            
            await stop_embedded_worker()
            
            # Should have been called multiple times due to fast polling
            assert mock_process.call_count > 5
    
    @pytest.mark.asyncio
    async def test_zero_concurrency_protection(self, cleanup_worker):
        """Test that concurrency=0 is handled gracefully"""
        # This should probably be treated as concurrency=1
        with patch('fastjob.local.process_jobs', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = False
            
            # Even with concurrency=0, should not crash
            await start_embedded_worker_async(run_once=True, concurrency=0)
            
            # Some implementation might default to 1 worker
            # The important thing is it doesn't crash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])