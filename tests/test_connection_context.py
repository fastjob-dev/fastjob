"""
Test suite for context-aware database connection management

This addresses concerns about global state making testing/integration difficult
by verifying the new connection context system works correctly.

The new system provides:
1. Backward compatibility with existing global pool usage
2. Context-local connection pools for better test isolation
3. Proper cleanup and context management
4. Integration with FastJob's existing functionality

Example usage for better test isolation:

    # Old approach (global pool, shared state)
    await enqueue(some_job)
    # Tests could interfere with each other

    # New approach (isolated contexts)
    async with DatabaseContext() as pool:
        await enqueue(some_job)  # Uses isolated pool
        # Each test gets its own database context
"""

import pytest
import asyncio
import asyncpg
import contextvars
from unittest.mock import patch, AsyncMock

from fastjob.db.connection import (
    get_pool, 
    close_pool, 
    connection_context, 
    DatabaseContext,
    create_pool,
    _context_pool,
    _pool
)
from fastjob.settings import FASTJOB_DATABASE_URL
from tests.db_utils import create_test_database, clear_table


@pytest.mark.asyncio
async def test_backward_compatibility_global_pool():
    """Test that the global pool still works for backward compatibility"""
    await create_test_database()
    
    # Reset global state
    await close_pool()
    
    # First call should create global pool
    pool1 = await get_pool()
    assert pool1 is not None
    assert isinstance(pool1, asyncpg.Pool)
    
    # Second call should return same pool
    pool2 = await get_pool()
    assert pool2 is pool1  # Same object reference
    
    # Pool should work for database operations
    async with pool1.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
        assert result == 1
    
    # Clean up
    await close_pool()


@pytest.mark.asyncio
async def test_context_manager_isolated_connections():
    """Test that the context manager provides isolated database connections"""
    await create_test_database()
    
    # Reset global state
    await close_pool()
    
    # First, get a reference to what would be the global pool (outside context)
    global_pool = await get_pool()
    await close_pool()  # Close it so we can test context isolation
    
    async with connection_context() as context_pool:
        # get_pool() inside context should return context pool, not global
        current_pool = await get_pool()
        assert current_pool is context_pool
        assert current_pool is not global_pool
        
        # Context pool should work for database operations
        async with context_pool.acquire() as conn:
            result = await conn.fetchval("SELECT 2")
            assert result == 2
    
    # After context exit, should fall back to global pool behavior
    # (will create a new global pool since we closed the previous one)
    fallback_pool = await get_pool()
    assert fallback_pool is not context_pool
    
    # Clean up
    await close_pool()


@pytest.mark.asyncio
async def test_context_local_pools_take_precedence():
    """Test that context-local pools take precedence over global pools"""
    await create_test_database()
    
    # Reset global state
    await close_pool()
    
    # Create global pool first
    global_pool = await get_pool()
    
    async with connection_context() as context_pool:
        # Inside context, get_pool should return context pool
        current_pool = await get_pool()
        assert current_pool is context_pool
        assert current_pool is not global_pool
        
        # Nested contexts should work too
        async with connection_context() as nested_context_pool:
            nested_pool = await get_pool()
            assert nested_pool is nested_context_pool
            assert nested_pool is not context_pool
            assert nested_pool is not global_pool
        
        # After nested context, should return to outer context
        outer_pool = await get_pool()
        assert outer_pool is context_pool
    
    # After all contexts, should return to global
    final_pool = await get_pool()
    assert final_pool is global_pool
    
    # Clean up
    await close_pool()


@pytest.mark.asyncio
async def test_database_context_class():
    """Test that the DatabaseContext class works correctly"""
    await create_test_database()
    
    # Reset global state
    await close_pool()
    
    async with DatabaseContext() as pool:
        assert isinstance(pool, asyncpg.Pool)
        
        # Should be able to use the pool
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 3")
            assert result == 3
        
        # get_pool() should return this context pool
        current_pool = await get_pool()
        assert current_pool is pool
    
    # After context exit, should not have context pool
    context_pool_value = _context_pool.get(None)
    assert context_pool_value is None
    
    # Clean up
    await close_pool()


@pytest.mark.asyncio
async def test_database_context_with_custom_url():
    """Test DatabaseContext with custom database URL"""
    await create_test_database()
    
    custom_url = "postgresql://postgres@localhost/fastjob_test"
    
    async with DatabaseContext(custom_url) as pool:
        # Should work with custom URL
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 4")
            assert result == 4


@pytest.mark.asyncio
async def test_connection_cleanup_happens_properly():
    """Test that connection cleanup happens properly"""
    await create_test_database()
    
    # Reset global state
    await close_pool()
    
    pool_refs = []
    
    # Create multiple contexts and track pool references
    async with connection_context() as pool1:
        pool_refs.append(pool1)
        
        async with connection_context() as pool2:
            pool_refs.append(pool2)
            
            # Both pools should be different instances
            assert pool1 is not pool2
    
    # After contexts exit, pools should be closed
    # Note: We can't directly test if pools are closed since asyncpg
    # doesn't expose that state, but we can test that context variables are reset
    context_pool_value = _context_pool.get(None)
    assert context_pool_value is None
    
    # Clean up
    await close_pool()


@pytest.mark.asyncio
async def test_improved_testability_with_isolation():
    """Show how this improves testability by allowing test isolation"""
    await create_test_database()
    
    # Reset global state
    await close_pool()
    
    # Test 1: Isolated test environment
    async with connection_context() as test_pool1:
        async with test_pool1.acquire() as conn:
            # Create some test data
            await conn.execute("CREATE TEMP TABLE test_data (id INT)")
            await conn.execute("INSERT INTO test_data (id) VALUES (1)")
            
            # Verify data exists
            result = await conn.fetchval("SELECT COUNT(*) FROM test_data")
            assert result == 1
    
    # Test 2: Another isolated test environment
    async with connection_context() as test_pool2:
        async with test_pool2.acquire() as conn:
            # This connection won't have the temp table from test 1
            with pytest.raises(asyncpg.UndefinedTableError):
                await conn.fetchval("SELECT COUNT(*) FROM test_data")
            
            # Create different test data
            await conn.execute("CREATE TEMP TABLE test_data (id INT)")
            await conn.execute("INSERT INTO test_data (id) VALUES (2), (3)")
            
            result = await conn.fetchval("SELECT COUNT(*) FROM test_data")
            assert result == 2
    
    # Tests are completely isolated from each other
    # Clean up
    await close_pool()


@pytest.mark.asyncio
async def test_concurrent_contexts_are_isolated():
    """Test that concurrent contexts don't interfere with each other"""
    await create_test_database()
    
    # Reset global state
    await close_pool()
    
    async def worker_with_context(worker_id: int, results: list):
        """Worker function that uses its own database context"""
        async with connection_context() as pool:
            async with pool.acquire() as conn:
                # Each worker gets its own connection
                result = await conn.fetchval(f"SELECT {worker_id}")
                results.append(result)
    
    # Run multiple workers concurrently
    results = []
    tasks = [
        worker_with_context(1, results),
        worker_with_context(2, results),
        worker_with_context(3, results),
        worker_with_context(4, results),
    ]
    
    await asyncio.gather(*tasks)
    
    # All workers should have completed successfully
    assert set(results) == {1, 2, 3, 4}
    
    # Clean up
    await close_pool()


@pytest.mark.asyncio
async def test_create_pool_utility_function():
    """Test the create_pool utility function"""
    await create_test_database()
    
    # create_pool should not affect global state
    await close_pool()
    
    # Create a standalone pool
    standalone_pool = await create_pool()
    
    # Global pool should still be None
    global _pool
    assert _pool is None
    
    # get_pool() should create a new global pool, different from standalone
    global_pool = await get_pool()
    assert global_pool is not standalone_pool
    
    # Standalone pool should work
    async with standalone_pool.acquire() as conn:
        result = await conn.fetchval("SELECT 5")
        assert result == 5
    
    # Clean up both pools
    await standalone_pool.close()
    await close_pool()


@pytest.mark.asyncio 
async def test_context_var_token_management():
    """Test that context variable tokens are managed correctly"""
    await create_test_database()
    
    # Reset global state
    await close_pool()
    
    # Initial state - no context pool
    assert _context_pool.get(None) is None
    
    async with connection_context() as pool1:
        # Should have context pool set
        assert _context_pool.get(None) is pool1
        
        async with connection_context() as pool2:
            # Should have new context pool
            assert _context_pool.get(None) is pool2
            assert pool2 is not pool1
        
        # Should restore previous context pool
        assert _context_pool.get(None) is pool1
    
    # Should restore to no context pool
    assert _context_pool.get(None) is None
    
    # Clean up
    await close_pool()


@pytest.mark.asyncio
async def test_database_context_exception_handling():
    """Test that DatabaseContext properly handles exceptions"""
    await create_test_database()
    
    # Reset global state
    await close_pool()
    
    pool_ref = None
    
    try:
        async with DatabaseContext() as pool:
            pool_ref = pool
            # Simulate an exception
            raise ValueError("Test exception")
    except ValueError:
        pass  # Expected exception
    
    # Context should still be cleaned up despite exception
    assert _context_pool.get(None) is None
    
    # Note: We can't easily test if the pool is closed since asyncpg
    # doesn't expose that information, but the cleanup should happen
    
    # Clean up
    await close_pool()


@pytest.mark.asyncio
async def test_fastjob_integration_with_contexts():
    """Test integration with FastJob functionality using contexts"""
    await create_test_database()
    
    # Import here to avoid circular imports during test discovery
    from fastjob import job, enqueue
    from fastjob.core.processor import process_jobs
    
    @job()
    async def test_context_job(value: int):
        return value * 2
    
    # Reset global state
    await close_pool()
    
    async with connection_context() as pool:
        # Clear any existing jobs
        await clear_table(pool)
        
        # Enqueue a job (this should use the context pool)
        job_id = await enqueue(test_context_job, value=21)
        
        # Process the job using the context pool connection
        async with pool.acquire() as conn:
            processed = await process_jobs(conn, queue="default")
            assert processed is True
        
        # Verify job was processed
        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT status FROM fastjob_jobs WHERE id = $1", job_id
            )
            assert result['status'] == 'done'
    
    # Clean up
    await close_pool()


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__])