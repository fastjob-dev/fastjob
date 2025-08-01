"""
Database connection helper utilities to reduce code duplication.

This module provides common patterns for database operations to reduce the
135+ repeated 'async with pool.acquire() as conn:' patterns across the codebase.
"""

import logging
from typing import Any, Callable, List, Optional, TypeVar
from contextlib import asynccontextmanager

import asyncpg

from fastjob.db.connection import get_pool

logger = logging.getLogger(__name__)

T = TypeVar("T")


@asynccontextmanager
async def get_connection(pool: Optional[asyncpg.Pool] = None):
    """
    Get a database connection from the pool.
    
    Args:
        pool: Optional pool to use. If None, uses the default pool.
        
    Yields:
        asyncpg.Connection: Database connection
    """
    if pool is None:
        pool = await get_pool()
    
    async with pool.acquire() as conn:
        yield conn


async def execute_with_connection(
    query: str,
    *args,
    pool: Optional[asyncpg.Pool] = None,
    set_timezone: bool = False,
) -> Any:
    """
    Execute a query with automatic connection management.
    
    Args:
        query: SQL query to execute
        *args: Query parameters
        pool: Optional pool to use
        set_timezone: Whether to set timezone to UTC
        
    Returns:
        Query result
    """
    async with get_connection(pool) as conn:
        if set_timezone:
            await conn.execute("SET timezone = 'UTC'")
        return await conn.execute(query, *args)


async def fetchrow_with_connection(
    query: str,
    *args,
    pool: Optional[asyncpg.Pool] = None,
    set_timezone: bool = False,
) -> Optional[asyncpg.Record]:
    """
    Fetch a single row with automatic connection management.
    
    Args:
        query: SQL query to execute
        *args: Query parameters
        pool: Optional pool to use
        set_timezone: Whether to set timezone to UTC
        
    Returns:
        Single row or None
    """
    async with get_connection(pool) as conn:
        if set_timezone:
            await conn.execute("SET timezone = 'UTC'")
        return await conn.fetchrow(query, *args)


async def fetchall_with_connection(
    query: str,
    *args,
    pool: Optional[asyncpg.Pool] = None,
    set_timezone: bool = False,
) -> List[asyncpg.Record]:
    """
    Fetch all rows with automatic connection management.
    
    Args:
        query: SQL query to execute
        *args: Query parameters
        pool: Optional pool to use
        set_timezone: Whether to set timezone to UTC
        
    Returns:
        List of rows
    """
    async with get_connection(pool) as conn:
        if set_timezone:
            await conn.execute("SET timezone = 'UTC'")
        return await conn.fetchall(query, *args)


async def fetchval_with_connection(
    query: str,
    *args,
    pool: Optional[asyncpg.Pool] = None,
    set_timezone: bool = False,
) -> Any:
    """
    Fetch a single value with automatic connection management.
    
    Args:
        query: SQL query to execute
        *args: Query parameters
        pool: Optional pool to use
        set_timezone: Whether to set timezone to UTC
        
    Returns:
        Single value
    """
    async with get_connection(pool) as conn:
        if set_timezone:
            await conn.execute("SET timezone = 'UTC'")
        return await conn.fetchval(query, *args)


async def execute_in_transaction(
    operations: Callable[[asyncpg.Connection], Any],
    pool: Optional[asyncpg.Pool] = None,
    set_timezone: bool = False,
) -> Any:
    """
    Execute operations within a transaction with automatic connection management.
    
    Args:
        operations: Async function that takes a connection and performs operations
        pool: Optional pool to use
        set_timezone: Whether to set timezone to UTC
        
    Returns:
        Result from operations function
    """
    async with get_connection(pool) as conn:
        if set_timezone:
            await conn.execute("SET timezone = 'UTC'")
        async with conn.transaction():
            return await operations(conn)


async def execute_batch_with_connection(
    queries: List[tuple],
    pool: Optional[asyncpg.Pool] = None,
    set_timezone: bool = False,
    use_transaction: bool = True,
) -> List[Any]:
    """
    Execute multiple queries with automatic connection management.
    
    Args:
        queries: List of (query, *args) tuples
        pool: Optional pool to use
        set_timezone: Whether to set timezone to UTC
        use_transaction: Whether to wrap in a transaction
        
    Returns:
        List of query results
    """
    async with get_connection(pool) as conn:
        if set_timezone:
            await conn.execute("SET timezone = 'UTC'")
            
        if use_transaction:
            async with conn.transaction():
                results = []
                for query_tuple in queries:
                    query = query_tuple[0]
                    args = query_tuple[1:] if len(query_tuple) > 1 else ()
                    result = await conn.execute(query, *args)
                    results.append(result)
                return results
        else:
            results = []
            for query_tuple in queries:
                query = query_tuple[0]
                args = query_tuple[1:] if len(query_tuple) > 1 else ()
                result = await conn.execute(query, *args)
                results.append(result)
            return results


class DatabaseHelper:
    """
    Database helper class for consistent database operations.
    
    This class provides a higher-level interface for common database patterns
    while maintaining the flexibility of direct connection usage when needed.
    """
    
    def __init__(self, pool: Optional[asyncpg.Pool] = None):
        """
        Initialize the database helper.
        
        Args:
            pool: Optional pool to use. If None, uses the default pool.
        """
        self.pool = pool
    
    async def get_connection(self):
        """Get a connection context manager."""
        return get_connection(self.pool)
    
    async def execute(
        self,
        query: str,
        *args,
        set_timezone: bool = False,
    ) -> Any:
        """Execute a query."""
        return await execute_with_connection(
            query, *args, pool=self.pool, set_timezone=set_timezone
        )
    
    async def fetchrow(
        self,
        query: str,
        *args,
        set_timezone: bool = False,
    ) -> Optional[asyncpg.Record]:
        """Fetch a single row."""
        return await fetchrow_with_connection(
            query, *args, pool=self.pool, set_timezone=set_timezone
        )
    
    async def fetchall(
        self,
        query: str,
        *args,
        set_timezone: bool = False,
    ) -> List[asyncpg.Record]:
        """Fetch all rows."""
        return await fetchall_with_connection(
            query, *args, pool=self.pool, set_timezone=set_timezone
        )
    
    async def fetchval(
        self,
        query: str,
        *args,
        set_timezone: bool = False,
    ) -> Any:
        """Fetch a single value."""
        return await fetchval_with_connection(
            query, *args, pool=self.pool, set_timezone=set_timezone
        )
    
    async def execute_in_transaction(
        self,
        operations: Callable[[asyncpg.Connection], Any],
        set_timezone: bool = False,
    ) -> Any:
        """Execute operations within a transaction."""
        return await execute_in_transaction(
            operations, pool=self.pool, set_timezone=set_timezone
        )
    
    async def execute_batch(
        self,
        queries: List[tuple],
        set_timezone: bool = False,
        use_transaction: bool = True,
    ) -> List[Any]:
        """Execute multiple queries."""
        return await execute_batch_with_connection(
            queries, pool=self.pool, set_timezone=set_timezone, use_transaction=use_transaction
        )


# Create a default instance for convenience
default_db = DatabaseHelper()

# Convenience functions that use the default instance
execute = default_db.execute
fetchrow = default_db.fetchrow
fetchall = default_db.fetchall
fetchval = default_db.fetchval
execute_transaction = default_db.execute_in_transaction
execute_batch = default_db.execute_batch