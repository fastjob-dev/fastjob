"""
Database connection management with context support
"""

import asyncpg
from typing import Optional, AsyncContextManager
from contextlib import asynccontextmanager
import contextvars

from fastjob.settings import FASTJOB_DATABASE_URL

# Global pool for backward compatibility
_pool: Optional[asyncpg.Pool] = None

# Context variable for thread-local pool management
_context_pool: contextvars.ContextVar[Optional[asyncpg.Pool]] = contextvars.ContextVar('fastjob_pool', default=None)


async def get_pool() -> asyncpg.Pool:
    """
    Get connection pool with context awareness.
    
    First checks for context-local pool, then falls back to global pool.
    This allows for better testing and integration while maintaining backward compatibility.
    """
    # Check if we have a context-local pool first
    context_pool = _context_pool.get(None)
    if context_pool is not None:
        return context_pool
    
    # Fall back to global pool for backward compatibility
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(FASTJOB_DATABASE_URL)
    return _pool


async def close_pool():
    """Close the global connection pool"""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def connection_context(database_url: Optional[str] = None) -> AsyncContextManager[asyncpg.Pool]:
    """
    Context manager for database connections.
    
    This provides better control over connection lifecycle for testing and integration.
    
    Args:
        database_url: Optional database URL. Uses FASTJOB_DATABASE_URL if not provided.
        
    Usage:
        async with connection_context() as pool:
            async with pool.acquire() as conn:
                # Use connection
    """
    db_url = database_url or FASTJOB_DATABASE_URL
    pool = await asyncpg.create_pool(db_url)
    
    # Set context-local pool
    token = _context_pool.set(pool)
    
    try:
        yield pool
    finally:
        # Clean up context and close pool
        _context_pool.reset(token)
        await pool.close()


class DatabaseContext:
    """
    Database context manager for applications that need explicit control.
    
    This is the recommended approach for new applications and testing.
    """
    
    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or FASTJOB_DATABASE_URL
        self.pool: Optional[asyncpg.Pool] = None
        self._token = None
    
    async def __aenter__(self) -> asyncpg.Pool:
        """Enter the context and create pool"""
        self.pool = await asyncpg.create_pool(self.database_url)
        self._token = _context_pool.set(self.pool)
        return self.pool
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context and cleanup"""
        if self._token:
            _context_pool.reset(self._token)
        if self.pool:
            await self.pool.close()


async def create_pool(database_url: Optional[str] = None) -> asyncpg.Pool:
    """Create a new connection pool without affecting global state"""
    db_url = database_url or FASTJOB_DATABASE_URL
    return await asyncpg.create_pool(db_url)