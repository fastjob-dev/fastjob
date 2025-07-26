import os
import subprocess
import asyncpg
from asyncpg.pool import Pool

from fastjob.db.migrations import run_migrations

TEST_DB_NAME = "fastjob_test"


async def create_test_database():
    db_url = f"postgresql://postgres@localhost/{TEST_DB_NAME}"
    os.environ["FASTJOB_DATABASE_URL"] = db_url

    # Only create if it doesn't exist
    try:
        subprocess.run(
            ["createdb", TEST_DB_NAME], check=True, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        # Database already exists, that's fine
        pass

    # Create a temporary pool for migrations
    temp_pool = await asyncpg.create_pool(db_url)
    async with temp_pool.acquire() as conn:
        await run_migrations(conn)
    await temp_pool.close()


async def drop_test_database():
    # Make dropping optional to avoid issues with concurrent tests
    try:
        subprocess.run(
            ["dropdb", "--if-exists", TEST_DB_NAME],
            check=False,
            stderr=subprocess.DEVNULL,
        )
    except:
        pass


async def clear_table(pool: Pool):
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE fastjob_jobs RESTART IDENTITY")
