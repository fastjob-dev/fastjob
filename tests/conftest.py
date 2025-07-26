import asyncio
import pytest
import os
from tests.db_utils import create_test_database, clear_table
from fastjob.db.connection import get_pool, close_pool
from fastjob.core.registry import clear_registry

# Ensure test database URL is set
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_test_database():
    """Set up test database once for the entire test session."""
    await create_test_database()
    yield
    # Don't drop database here to avoid issues with concurrent tests


@pytest.fixture(autouse=True)
async def clean_test_state():
    """Clean test state before each test to ensure isolation."""
    # Ensure database exists and is clean
    await create_test_database()

    # Clean up any existing connections
    await close_pool()

    # Don't clear job registry - let tests manage their own jobs
    # clear_registry()  # This causes issues with job re-registration

    # Get fresh pool and clear any existing jobs
    pool = await get_pool()
    await clear_table(pool)

    yield

    # Clean up after test
    await close_pool()
