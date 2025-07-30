"""
Conftest for Instance API tests

These tests use the instance-based FastJob API (app = FastJob(), app.job, etc.)
and create their own isolated FastJob instances.
"""

import pytest
import os
from tests.db_utils import create_test_database, clear_table
from fastjob.db.connection import close_pool

# Ensure test database URL is set
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"


@pytest.fixture(autouse=True)
async def clean_instance_api_state():
    """Clean instance API state before each test to ensure isolation."""
    # Ensure database exists and is clean
    await create_test_database()

    # Clean up any existing global connections (shouldn't be used, but be safe)
    await close_pool()

    yield

    # Clean up after test - close global connections
    await close_pool()


@pytest.fixture
async def clean_db():
    """Additional fixture for tests that need explicit clean database state."""
    await create_test_database()
    return None