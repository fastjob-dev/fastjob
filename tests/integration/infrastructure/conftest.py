"""
Conftest for Infrastructure tests

These tests cover underlying systems (CLI, connections, LISTEN/NOTIFY, etc.)
that support both APIs and may use mixed patterns.
"""

import pytest
import os
from tests.db_utils import create_test_database, clear_table
from fastjob.db.connection import close_pool

# Ensure test database URL is set
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"


@pytest.fixture(autouse=True)
async def clean_infrastructure_state():
    """Clean infrastructure state before each test to ensure isolation."""
    # Ensure database exists and is clean
    await create_test_database()

    # Clean up any existing connections
    await close_pool()

    yield

    # Clean up after test - close all connections
    await close_pool()


@pytest.fixture
async def clean_db():
    """Additional fixture for tests that need explicit clean database state."""
    await create_test_database()
    return None