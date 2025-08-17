"""
Test compliance with FastJob feature specification
"""

import os
import uuid

import pytest

import fastjob

# Use test database
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"


# Test job definitions
@fastjob.job(retries=3)
async def basic_job(message: str):
    return f"Basic: {message}"


@fastjob.job(retries=2, priority=50, queue="test")
async def advanced_job(message: str, count: int):
    return f"Advanced: {message} x{count}"


@pytest.mark.asyncio
async def test_free_features_compliance():
    """Test all Free Features (Phase 1 - MVP) compliance"""

    # ✅ PostgreSQL-based job persistence (JSON payload)
    job_id = await fastjob.enqueue(basic_job, message="test persistence")

    # Use global app pool for consistency
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()

    async with app_pool.acquire() as conn:
        job_record = await conn.fetchrow(
            "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id)
        )
        assert job_record is not None
        assert (
            job_record["job_name"]
            == "tests.integration.global_api.test_specification_compliance.basic_job"
        )
        assert '"message": "test persistence"' in job_record["args"]

    # ✅ Job processing with retry mechanism
    processed = await fastjob.run_worker(run_once=True)
    assert processed

    # Verify job completed
    async with app_pool.acquire() as conn:
        job_record = await conn.fetchrow(
            "SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id)
        )
        assert job_record["status"] == "done"
        assert job_record["max_attempts"] == 4  # retries=3 -> max_attempts=4

    # ✅ Internal DB connection pooling
    from fastjob.db.connection import get_pool

    pool = await get_pool()
    assert pool is not None


@pytest.mark.asyncio
async def test_pro_features_compliance():
    """Test Pro Features (Phase 2) compliance"""

    # ✅ Priority queues (numeric)
    await fastjob.enqueue(advanced_job, priority=10, message="high priority", count=1)

    await fastjob.enqueue(advanced_job, priority=100, message="low priority", count=1)

    # Verify priority ordering in database
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()

    async with app_pool.acquire() as conn:
        jobs = await conn.fetch(
            "SELECT priority FROM fastjob_jobs WHERE status = 'queued' ORDER BY priority ASC"
        )
        priorities = [job["priority"] for job in jobs]
        assert priorities == [10, 100]  # High priority first

    # ✅ Scheduling API exists
    assert hasattr(fastjob, "schedule")


@pytest.mark.asyncio
async def test_dsl_usage_examples_compliance():
    """Test that DSL usage examples from spec work exactly as documented"""

    # Spec Example 1: Registering a Job
    @fastjob.job(retries=3)
    async def send_email(to: str, subject: str, body: str):
        return f"Email to {to}: {subject}"

    # Spec Example 2: Enqueuing a Job
    job_id = await fastjob.enqueue(
        send_email, to="user@example.com", subject="Hello", body="Test message"
    )

    # Verify job was enqueued
    status = await fastjob.get_job_status(job_id)
    assert status is not None
    assert status["status"] == "queued"

    # Spec Example 3: Scheduling a Job (basic)
    from datetime import datetime, timedelta

    future_time = datetime.now() + timedelta(minutes=30)

    scheduled_job_id = await fastjob.schedule(
        send_email,
        run_at=future_time,
        to="user@example.com",
        subject="Scheduled",
        body="Scheduled message",
    )

    # Verify job was scheduled
    scheduled_status = await fastjob.get_job_status(scheduled_job_id)
    assert scheduled_status is not None
    assert scheduled_status["status"] == "queued"
    assert scheduled_status["scheduled_at"] is not None


@pytest.mark.asyncio
async def test_cli_commands_compliance():
    """Test CLI commands match specification"""
    # Test that CLI module exists and has correct structure
    from fastjob.cli.main import main

    assert main is not None

    # Test CLI commands exist
    from fastjob.cli.commands.core import register_core_commands
    from fastjob.cli.registry import get_cli_registry

    # Register core commands and verify they exist
    register_core_commands()
    registry = get_cli_registry()
    commands = registry.get_all_commands()
    command_names = [cmd.name for cmd in commands]

    # Test database setup command (was "migrate")
    assert "setup" in command_names

    # Test worker start command (was "worker")
    assert "start" in command_names

    # Verify command structure includes expected features
    start_cmd = next((cmd for cmd in commands if cmd.name == "start"), None)
    assert start_cmd is not None
    assert start_cmd.help == "Start FastJob worker"


@pytest.mark.asyncio
async def test_database_schema_compliance():
    """Test database schema matches specification"""

    # Use global app pool for consistency
    global_app = fastjob._get_global_app()
    app_pool = await global_app.get_pool()

    async with app_pool.acquire() as conn:
        # Check table exists
        table_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'fastjob_jobs'
            )
            """
        )
        assert table_exists

        # Check required columns exist
        columns = await conn.fetch(
            """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'fastjob_jobs'
            """
        )

        column_names = {col["column_name"] for col in columns}
        required_columns = {
            "id",
            "job_name",
            "args",
            "status",
            "queue",
            "priority",
            "attempts",
            "max_attempts",
            "scheduled_at",
            "last_error",
            "created_at",
            "updated_at",
        }

        assert required_columns.issubset(
            column_names
        ), f"Missing columns: {required_columns - column_names}"


@pytest.mark.asyncio
async def test_project_structure_compliance():
    """Test project structure matches specification"""
    # Check main directories exist
    base_path = os.path.dirname(fastjob.__file__)

    required_dirs = [
        "core",  # Task decorator, queue logic, processor loop
        "cli",  # CLI commands
        "db",  # Database utilities
    ]

    for dir_name in required_dirs:
        dir_path = os.path.join(base_path, dir_name)
        assert os.path.isdir(dir_path), f"Required directory missing: {dir_name}"

    # Check key modules exist
    assert hasattr(fastjob, "job")
    assert hasattr(fastjob, "enqueue")
    assert hasattr(fastjob, "schedule")
    assert hasattr(fastjob, "run_worker")
    assert hasattr(fastjob, "get_job_status")
    assert hasattr(fastjob, "cancel_job")
    assert hasattr(fastjob, "retry_job")
    assert hasattr(fastjob, "delete_job")
    assert hasattr(fastjob, "list_jobs")
    assert hasattr(fastjob, "get_queue_stats")
