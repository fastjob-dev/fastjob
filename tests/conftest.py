import asyncio
import os

import pytest

from fastjob.db.connection import close_pool
from tests.db_utils import clear_table, create_test_database

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

    # Configure global FastJob app to use test database consistently
    import fastjob

    fastjob.configure(database_url="postgresql://postgres@localhost/fastjob_test")

    # Get fresh pool and clear any existing jobs (use global app's pool for consistency)
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()
    await clear_table(app_pool)

    yield

    # Clean up after test - close both pools
    await close_pool()
    if global_app.is_initialized:
        await global_app.close()
