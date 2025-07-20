"""
Database connection management
"""

import asyncpg
from typing import Optional

from fastjob.settings import FASTJOB_DATABASE_URL

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the global connection pool"""
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