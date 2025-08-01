"""
Database Context Management for FastJob

Provides a unified way to access database connections for both Global API 
and Instance-based API usage patterns. This allows Pro/Enterprise features
to work correctly with both --database-url CLI parameter and global configuration.
"""

from typing import Optional
import logging

import asyncpg

from ..client import FastJob
from .connection import get_pool as get_global_pool

logger = logging.getLogger(__name__)


class DatabaseContext:
    """
    Database context that provides unified access to database connections.
    
    Supports both global API and instance-based API patterns, allowing
    Pro/Enterprise features to work with either approach transparently.
    """
    
    def __init__(
        self, 
        fastjob_instance: Optional[FastJob] = None,
        database_url: Optional[str] = None
    ):
        """
        Initialize database context.
        
        Args:
            fastjob_instance: FastJob instance for instance-based API
            database_url: Database URL for direct connection (fallback)
        """
        self._fastjob_instance = fastjob_instance
        self._database_url = database_url
        self._pool: Optional[asyncpg.Pool] = None
        self._owns_pool = False
        
    @classmethod
    def from_global_api(cls) -> 'DatabaseContext':
        """Create context using global FastJob API."""
        return cls()
    
    @classmethod 
    def from_instance(cls, fastjob_instance: FastJob) -> 'DatabaseContext':
        """Create context from FastJob instance."""
        return cls(fastjob_instance=fastjob_instance)
    
    @classmethod
    def from_database_url(cls, database_url: str) -> 'DatabaseContext':
        """Create context from database URL directly.""" 
        return cls(database_url=database_url)
    
    async def get_pool(self) -> asyncpg.Pool:
        """
        Get database connection pool.
        
        Returns the appropriate pool based on the context:
        - Instance-based: uses FastJob instance's pool
        - Global API: uses global pool
        - Direct URL: creates dedicated pool
        """
        if self._fastjob_instance:
            # Use FastJob instance's pool
            return await self._fastjob_instance.get_pool()
        
        elif self._database_url:
            # Create dedicated pool for this URL
            if not self._pool:
                self._pool = await asyncpg.create_pool(self._database_url)
                self._owns_pool = True
            return self._pool
        
        else:
            # Use global pool (fallback for global API)
            return await get_global_pool()
    
    async def execute_query(self, query: str, *args):
        """Execute a query using the context's database connection."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def execute_many(self, query: str, *args):
        """Execute a query that returns multiple rows."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def close(self):
        """Close the database context and clean up resources."""
        if self._owns_pool and self._pool:
            await self._pool.close()
            self._pool = None
            self._owns_pool = False
    
    @property
    def database_url(self) -> Optional[str]:
        """Get the database URL if available."""
        if self._fastjob_instance:
            return self._fastjob_instance.settings.database_url
        return self._database_url
    
    def __repr__(self) -> str:
        if self._fastjob_instance:
            return f"DatabaseContext(instance={self._fastjob_instance})"
        elif self._database_url:
            return f"DatabaseContext(url={self._database_url})"
        else:
            return "DatabaseContext(global)"


# Context management for CLI commands
_current_context: Optional[DatabaseContext] = None


def set_current_context(context: DatabaseContext):
    """Set the current database context for CLI commands."""
    global _current_context
    _current_context = context


def get_current_context() -> DatabaseContext:
    """
    Get the current database context.
    
    Falls back to global API context if none is set.
    """
    global _current_context
    if _current_context is None:
        _current_context = DatabaseContext.from_global_api()
    return _current_context


def clear_current_context():
    """Clear the current database context."""
    global _current_context
    if _current_context:
        # Note: We don't await close() here since this is sync
        # The context will be cleaned up when the CLI command completes
        _current_context = None


async def get_context_pool() -> asyncpg.Pool:
    """
    Convenience function to get database pool from current context.
    
    This is the main function that Pro/Enterprise features should use
    instead of directly calling get_pool() from connection.py.
    """
    context = get_current_context()
    return await context.get_pool()


# Backwards compatibility - Pro/Enterprise features can use this directly
async def get_database_pool() -> asyncpg.Pool:
    """
    Get database pool with context awareness.
    
    Alias for get_context_pool() for better naming.
    """
    return await get_context_pool()