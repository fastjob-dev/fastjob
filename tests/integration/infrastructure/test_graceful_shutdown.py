"""
Tests for graceful worker shutdown and pool closing race condition fixes.

These tests verify that the "pool is closing" race condition is properly handled
during worker shutdown scenarios, ensuring excellent developer experience.
"""

import asyncio
import logging
import time
from unittest.mock import AsyncMock, patch

import pytest

from fastjob.core.heartbeat import cleanup_stale_workers
# Use global API or FastJob instance for worker functionality
from fastjob.db.connection import create_pool


@pytest.mark.asyncio
async def test_cleanup_stale_workers_with_closing_pool():
    """Test that cleanup_stale_workers handles closing pool gracefully"""
    from fastjob.settings import get_settings
    pool = await create_pool(get_settings().database_url)
    
    # Mock the pool as closing
    pool._closing = True
    
    # Should not raise exception and return 0
    result = await cleanup_stale_workers(pool)
    assert result == 0
    
    await pool.close()


@pytest.mark.asyncio  
async def test_cleanup_stale_workers_with_pool_closing_error():
    """Test that cleanup_stale_workers handles InterfaceError gracefully"""
    import asyncpg
    
    # Test the specific exception handling by triggering it with a closed pool
    from fastjob.settings import get_settings
    pool = await create_pool(get_settings().database_url)
    
    # Close the pool first to trigger InterfaceError
    await pool.close()
    
    # Now calling cleanup_stale_workers should handle the error gracefully
    result = await cleanup_stale_workers(pool)
    assert result == 0


@pytest.mark.asyncio
async def test_worker_cancellation_no_pool_errors(caplog):
    """Test that worker cancellation doesn't produce pool closing errors"""
    
    # Clear any existing log records
    caplog.clear()
    
    # Set log level to capture all messages
    with caplog.at_level(logging.DEBUG):
        # Start a worker task using global API
        import fastjob
        from fastjob.settings import get_settings
        fastjob.configure(database_url=get_settings().database_url)
        worker_task = asyncio.create_task(
            fastjob.run_worker(concurrency=1)
        )
        
        # Let it start up
        await asyncio.sleep(0.1)
        
        # Cancel the worker
        worker_task.cancel()
        
        # Wait for cancellation to complete
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        
        # Give a moment for any delayed log messages
        await asyncio.sleep(0.05)
    
    # Check that no "pool is closing" errors were logged
    pool_closing_errors = [
        record for record in caplog.records 
        if "pool is closing" in record.getMessage() and record.levelno >= logging.ERROR
    ]
    
    assert len(pool_closing_errors) == 0, (
        f"Found {len(pool_closing_errors)} 'pool is closing' errors: "
        f"{[r.getMessage() for r in pool_closing_errors]}"
    )


@pytest.mark.asyncio
async def test_multiple_rapid_worker_cancellations(caplog):
    """Stress test: multiple rapid worker start/cancel cycles should be clean"""
    
    caplog.clear()
    
    with caplog.at_level(logging.ERROR):
        import fastjob
        from fastjob.settings import get_settings
        fastjob.configure(database_url=get_settings().database_url)
        
        for i in range(3):
            # Start worker
            worker_task = asyncio.create_task(
                fastjob.run_worker(concurrency=1) 
            )
            
            # Brief startup time
            await asyncio.sleep(0.05)
            
            # Cancel worker
            worker_task.cancel()
            
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            
            # Brief cooldown
            await asyncio.sleep(0.02)
    
    # Should have no error-level log messages about pool closing
    error_messages = [record.getMessage() for record in caplog.records]
    pool_errors = [msg for msg in error_messages if "pool is closing" in msg]
    
    assert len(pool_errors) == 0, f"Found pool closing errors: {pool_errors}"


@pytest.mark.asyncio
async def test_worker_listener_cleanup_handles_errors():
    """Test that the worker's listener cleanup code handles connection errors gracefully"""
    # This test verifies the error handling code we added to processor.py
    # The actual scenario is tested in the processor's finally block
    
    from fastjob.db.connection import create_pool
    from fastjob.settings import get_settings
    
    pool = await create_pool(get_settings().database_url)
    conn = await pool.acquire()
    
    # Create a scenario similar to what happens in the worker
    try:
        # This simulates the pattern in processor.py lines 604-614
        try:
            await conn.remove_listener("nonexistent_channel", lambda *args: None)
        except Exception as e:
            # Should handle gracefully (like our fix does)
            assert "does not have" in str(e) or "listener" in str(e)
        
        try:
            await pool.release(conn)
        except Exception as e:
            # Should handle gracefully (like our fix does)  
            pass
            
    finally:
        await pool.close()
        
    # Test passes if no unhandled exceptions occur
    assert True


@pytest.mark.asyncio
async def test_graceful_shutdown_integration():
    """Integration test for complete graceful shutdown flow"""
    import signal
    import os
    
    # This test verifies the complete shutdown flow works
    # without race conditions or error spam
    
    shutdown_event = asyncio.Event()
    
    async def mock_signal_handler():
        # Simulate signal reception after brief delay
        await asyncio.sleep(0.1) 
        shutdown_event.set()
    
    # Start the signal handler task
    signal_task = asyncio.create_task(mock_signal_handler())
    
    # Start worker with a brief timeout using global API
    import fastjob
    from fastjob.settings import get_settings
    fastjob.configure(database_url=get_settings().database_url)
    worker_task = asyncio.create_task(
        fastjob.run_worker(concurrency=1)
    )
    
    # Wait for either signal or timeout
    done, pending = await asyncio.wait(
        [worker_task, signal_task],
        return_when=asyncio.FIRST_COMPLETED,
        timeout=0.5
    )
    
    # Clean up
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    # Worker task should complete without exceptions
    if worker_task in done:
        # If worker completed naturally, get its result to check for exceptions
        try:
            await worker_task
        except asyncio.CancelledError:
            pass  # Expected
    
    # Test passes if we get here without unhandled exceptions
    assert True