import asyncio
import os
import subprocess
import asyncpg
from asyncpg.pool import Pool

from fastjob.db.migrations import run_migrations

TEST_DB_NAME = "fastjob_test"

async def create_test_database():
    os.environ["FASTJOB_DATABASE_URL"] = f"postgresql://postgres@localhost/{TEST_DB_NAME}"
    subprocess.run(["dropdb", "--if-exists", TEST_DB_NAME], check=True)
    subprocess.run(["createdb", TEST_DB_NAME], check=True)

    # Create a temporary pool for migrations
    temp_pool = await asyncpg.create_pool(f"postgresql://postgres@localhost/{TEST_DB_NAME}")
    async with temp_pool.acquire() as conn:
        await run_migrations(conn)
    await temp_pool.close()

async def drop_test_database():
    subprocess.run(["dropdb", TEST_DB_NAME], check=True)

async def clear_table(pool: Pool):
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE fastjob_jobs RESTART IDENTITY")