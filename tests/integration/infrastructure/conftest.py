"""
Conftest for Infrastructure tests

These tests cover underlying systems (CLI, connections, LISTEN/NOTIFY, etc.)
that support both APIs and may use mixed patterns.
"""

import os

import pytest

from fastjob.db.connection import close_pool
from tests.db_utils import create_test_database

# Ensure test database URL is set
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"


@pytest.fixture(scope="session", autouse=True)
async def setup_infrastructure_database():
    """Set up test database once per test session."""
    await create_test_database()
    yield


@pytest.fixture(autouse=True)
async def clean_infrastructure_state():
    """Clean infrastructure state before each test to ensure isolation."""
    # Database already exists from session fixture, just clean up connections
    await close_pool()

    yield

    # Clean up after test - close all connections
    await close_pool()


@pytest.fixture
async def clean_db():
    """Additional fixture for tests that need explicit clean database state."""
    await create_test_database()
    return None
