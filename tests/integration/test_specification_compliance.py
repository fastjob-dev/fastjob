"""
Test FastJob compliance with FASTJOB_AGENT_README_v2.md specification
"""

import pytest
import asyncio
import uuid
from datetime import datetime, timedelta
from pydantic import BaseModel

import fastjob
from fastjob.db.connection import get_pool, close_pool
from tests.db_utils import create_test_database, drop_test_database, clear_table

# Set test database
import os
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"


class JobArgs(BaseModel):
    message: str
    count: int = 1


@fastjob.job(retries=3)
async def basic_job(message: str):
    """Basic job as per specification"""
    return f"Processed: {message}"


@fastjob.job(retries=5, args_model=JobArgs, priority=50, queue="test")
async def advanced_job(message: str, count: int = 1):
    """Advanced job with validation, priority, and queue"""
    return f"Processed {count} times: {message}"


@pytest.mark.asyncio
async def test_free_features_compliance():
    """Test all Free Features (Phase 1 - MVP) compliance"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # ✅ PostgreSQL-based job persistence (JSON payload)
        job_id = await fastjob.enqueue(basic_job, message="test persistence")
        
        async with pool.acquire() as conn:
            job_record = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id))
            assert job_record is not None
            assert job_record["args"] is not None  # JSON payload
        
        # ✅ Simple DSL for job declaration & enqueue
        assert hasattr(fastjob, 'job')
        assert hasattr(fastjob, 'enqueue')
        
        # ✅ Embedded processor
        assert hasattr(fastjob, 'start_embedded_worker')
        assert hasattr(fastjob, 'stop_embedded_worker')
        
        # ✅ Retry mechanism and job status tracking
        from fastjob.core.processor import process_jobs
        async with pool.acquire() as conn:
            processed = await process_jobs(conn)
            assert processed is True
            
            job_record = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id))
            assert job_record["status"] == "done"
            assert job_record["attempts"] >= 0
            assert job_record["max_attempts"] == 3  # Retry mechanism
        
        # ✅ Internal DB connection pooling
        from fastjob.db.connection import _pool
        assert _pool is not None
        
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_pro_features_compliance():
    """Test Pro Features (Phase 2) compliance"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # ✅ Priority queues (numeric)
        high_priority_job = await fastjob.enqueue(
            advanced_job, 
            priority=10,  # High priority
            message="high priority", 
            count=1
        )
        
        low_priority_job = await fastjob.enqueue(
            advanced_job,
            priority=100,  # Low priority
            message="low priority",
            count=1
        )
        
        async with pool.acquire() as conn:
            # Check priority ordering in database
            jobs = await conn.fetch("""
                SELECT id, priority FROM fastjob_jobs 
                ORDER BY priority ASC
            """)
            assert len(jobs) == 2
            assert jobs[0]["priority"] <= jobs[1]["priority"]  # Priority ordering
        
        # ✅ Web dashboard (verify structure exists)
        try:
            from fastjob.dashboard.fastapi_app import create_dashboard_app
            app = create_dashboard_app()
            assert app is not None
        except ImportError:
            # FastAPI not installed - dashboard structure should still exist
            from fastjob.dashboard import app as dashboard_module
            assert dashboard_module is not None
        
        # ✅ Recurring jobs DSL (verify API exists)
        assert hasattr(fastjob, 'schedule')  # Crontab style
        assert hasattr(fastjob, 'every')     # Human style
        
        if fastjob.schedule and fastjob.every:
            # Test the DSL APIs exist and work
            cron_builder = fastjob.schedule("*/5 * * * *")
            assert hasattr(cron_builder, 'job')
            
            human_builder = fastjob.every("10m")
            assert hasattr(human_builder, 'do')
        
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio 
async def test_dsl_usage_examples_compliance():
    """Test that DSL usage examples from spec work exactly as documented"""
    await create_test_database()
    try:
        pool = await get_pool()
        await clear_table(pool)
        
        # Spec Example 1: Registering a Job
        @fastjob.job(retries=3)
        async def send_email(to: str, subject: str, body: str):
            return f"Email to {to}: {subject}"
        
        # Spec Example 2: Enqueuing a Job
        job_id = await fastjob.enqueue(
            send_email, 
            to="abc@example.com", 
            subject="Hi", 
            body="Body"
        )
        assert job_id is not None
        
        # Verify job was enqueued correctly
        async with pool.acquire() as conn:
            job_record = await conn.fetchrow("SELECT * FROM fastjob_jobs WHERE id = $1", uuid.UUID(job_id))
            assert job_record["job_name"] == "tests.test_specification_compliance.send_email"
            assert job_record["max_attempts"] == 3
        
        # Spec Example 3: Scheduling Jobs (Pro) - if available
        if fastjob.schedule and fastjob.every:
            # Test that the exact syntax from spec works
            try:
                every_builder = fastjob.every("10m")
                schedule_builder = fastjob.schedule("0 9 * * *")
                
                # These should not raise exceptions
                assert every_builder is not None
                assert schedule_builder is not None
            except Exception as e:
                pytest.fail(f"Pro scheduling DSL failed: {e}")
        
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_cli_commands_compliance():
    """Test CLI commands match specification"""
    # Test that CLI module exists and has correct structure
    from fastjob.cli.main import main
    assert main is not None
    
    # Test worker command exists
    from fastjob.core.processor import run_worker
    assert run_worker is not None
    
    # Test migration command exists
    from fastjob.db.migrations import run_migrations
    assert run_migrations is not None
    
    # Test dashboard command exists
    from fastjob.dashboard.fastapi_app import run_dashboard
    assert run_dashboard is not None


@pytest.mark.asyncio
async def test_database_schema_compliance():
    """Test database schema matches specification"""
    await create_test_database()
    try:
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            # Check table exists
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'fastjob_jobs'
                )
            """)
            assert table_exists is True
            
            # Check required columns exist
            columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'fastjob_jobs'
                ORDER BY column_name
            """)
            
            column_names = {col['column_name'] for col in columns}
            required_columns = {
                'id', 'job_name', 'args', 'status', 'attempts', 
                'max_attempts', 'queue', 'priority', 'scheduled_at',
                'last_error', 'created_at', 'updated_at'
            }
            
            assert required_columns.issubset(column_names), f"Missing columns: {required_columns - column_names}"
            
    finally:
        await close_pool()
        await drop_test_database()


@pytest.mark.asyncio
async def test_project_structure_compliance():
    """Test project structure matches specification"""
    import os
    
    # Check main directories exist
    base_path = "/Users/abhinav/Code/python/fastjob/fastjob"
    
    required_dirs = [
        "core",      # Task decorator, queue logic, processor loop
        "db",        # Postgres schema, migrations, query helpers  
        "dashboard", # Pro: web UI (FastAPI)
        "cli",       # CLI entrypoints
    ]
    
    for dir_name in required_dirs:
        dir_path = os.path.join(base_path, dir_name)
        assert os.path.isdir(dir_path), f"Required directory missing: {dir_name}"
    
    # Check key files exist
    required_files = [
        "core/registry.py",    # Task decorator
        "core/queue.py",       # Queue logic
        "core/processor.py",   # Processor loop
        "db/schema.sql",       # Postgres schema
        "db/migrations.py",    # Migrations
        "cli/main.py",         # CLI entrypoints
    ]
    
    for file_path in required_files:
        full_path = os.path.join(base_path, file_path)
        assert os.path.isfile(full_path), f"Required file missing: {file_path}"