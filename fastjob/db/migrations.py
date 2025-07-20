import asyncpg
import os
from .connection import get_pool

async def run_migrations(conn=None):
    """Run database migrations. If no connection provided, creates one."""
    if conn is None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await _execute_migrations(conn)
    else:
        await _execute_migrations(conn)

async def _execute_migrations(conn):
    """Execute the actual migration SQL"""
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r") as f:
        await conn.execute(f.read())