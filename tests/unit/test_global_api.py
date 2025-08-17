"""
Tests for the global convenience API
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import fastjob
from fastjob import FastJob


@pytest.fixture(autouse=True)
def reset_global_app():
    """Reset global app state before each test"""
    fastjob._global_app = None
    yield
    if fastjob._global_app and fastjob._global_app.is_initialized:
        asyncio.run(fastjob._global_app.close())
    fastjob._global_app = None


class TestGlobalAPI:
    """Test the global convenience API functions"""

    def test_get_global_app_creates_singleton(self):
        """Test that _get_global_app creates and returns same instance"""
        app1 = fastjob._get_global_app()
        app2 = fastjob._get_global_app()

        assert isinstance(app1, FastJob)
        assert isinstance(app2, FastJob)
        assert app1 is app2  # Same instance

    def test_configure_creates_new_global_app(self):
        """Test that configure() creates a new global app with settings"""
        # Get initial app
        app1 = fastjob._get_global_app()

        # Configure with new settings
        fastjob.configure(database_url="postgresql://test@localhost/test_db")

        # Should get new app instance
        app2 = fastjob._get_global_app()

        assert app1 is not app2  # Different instances
        assert app2.settings.database_url == "postgresql://test@localhost/test_db"

    def test_job_decorator_registers_with_global_app(self):
        """Test that @fastjob.job() registers with global app"""
        fastjob.configure(database_url="postgresql://test@localhost/test_db")

        @fastjob.job(retries=3, queue="test")
        async def test_job(message: str):
            return f"Processed: {message}"

        # Check job is registered in global app
        app = fastjob._get_global_app()
        job_name = "tests.unit.test_global_api.test_job"
        job_meta = app.get_job_registry().get_job(job_name)

        assert job_meta is not None
        assert job_meta["retries"] == 3
        assert job_meta["queue"] == "test"

    def test_job_decorator_returns_callable_function(self):
        """Test that job decorator returns a callable function"""

        @fastjob.job()
        async def test_job(x: int, y: int):
            return x + y

        # Should be callable (may be wrapped)
        assert callable(test_job)
        # Note: The decorator may wrap the function, changing its signature
        # The important thing is that it's still callable

    @pytest.mark.asyncio
    async def test_global_enqueue_uses_global_app(self):
        """Test that fastjob.enqueue() uses the global app"""
        fastjob.configure(database_url="postgresql://test@localhost/test_db")

        @fastjob.job()
        async def test_job(message: str):
            return message

        # Mock the global app's enqueue method
        app = fastjob._get_global_app()
        with patch.object(app, "enqueue", new_callable=AsyncMock) as mock_enqueue:
            mock_enqueue.return_value = "test-job-id"

            # Call global enqueue
            job_id = await fastjob.enqueue(test_job, message="test")

            # Should have called app.enqueue
            mock_enqueue.assert_called_once_with(test_job, message="test")
            assert job_id == "test-job-id"

    @pytest.mark.asyncio
    async def test_global_schedule_uses_global_app(self):
        """Test that fastjob.schedule() uses the global app"""
        from datetime import datetime, timedelta

        @fastjob.job()
        async def test_job(message: str):
            return message

        # Mock the global enqueue function since schedule() calls enqueue() internally
        with patch("fastjob.enqueue", new_callable=AsyncMock) as mock_enqueue:
            mock_enqueue.return_value = "scheduled-job-id"

            # Call global schedule
            run_at = datetime.now() + timedelta(hours=1)
            job_id = await fastjob.schedule(test_job, run_at=run_at, message="test")

            # Should have called enqueue with scheduled_at parameter
            mock_enqueue.assert_called_once_with(
                test_job, scheduled_at=run_at, message="test"
            )
            assert job_id == "scheduled-job-id"

    @pytest.mark.asyncio
    async def test_global_run_worker_uses_global_app(self):
        """Test that fastjob.run_worker() uses the global app"""
        fastjob.configure(database_url="postgresql://test@localhost/test_db")

        # Mock the global app's run_worker method
        app = fastjob._get_global_app()
        with patch.object(app, "run_worker", new_callable=AsyncMock) as mock_run_worker:

            # Call global run_worker
            await fastjob.run_worker(concurrency=2, run_once=True, queues=["test"])

            # Should have called app.run_worker
            mock_run_worker.assert_called_once_with(
                concurrency=2, run_once=True, queues=["test"]
            )

    def test_global_api_isolation_from_instances(self):
        """Test that global API and instance API are isolated"""
        # Configure global app
        fastjob.configure(database_url="postgresql://global@localhost/global_db")

        # Create instance app
        instance_app = FastJob(
            database_url="postgresql://instance@localhost/instance_db"
        )

        # Register jobs in both
        @fastjob.job()
        async def global_job():
            return "global"

        @instance_app.job()
        async def instance_job():
            return "instance"

        # Check isolation
        global_app = fastjob._get_global_app()

        # Global app should have global_job but not instance_job
        global_registry = global_app.get_job_registry()
        assert (
            global_registry.get_job("tests.unit.test_global_api.global_job") is not None
        )
        assert (
            global_registry.get_job("tests.unit.test_global_api.instance_job") is None
        )

        # Instance app should have instance_job but not global_job
        instance_registry = instance_app.get_job_registry()
        assert (
            instance_registry.get_job("tests.unit.test_global_api.instance_job")
            is not None
        )
        assert (
            instance_registry.get_job("tests.unit.test_global_api.global_job") is None
        )

    def test_global_api_configuration_persistence(self):
        """Test that global app configuration persists across calls"""
        # Configure global app
        test_config = {
            "database_url": "postgresql://persistent@localhost/persistent_db",
            "default_concurrency": 8,
            "result_ttl": 600,
        }
        fastjob.configure(**test_config)

        # Get app multiple times
        app1 = fastjob._get_global_app()
        app2 = fastjob._get_global_app()

        # Should be same instance with same config
        assert app1 is app2
        assert app1.settings.database_url == test_config["database_url"]
        assert app1.settings.default_concurrency == test_config["default_concurrency"]
        assert app1.settings.result_ttl == test_config["result_ttl"]

    def test_global_api_exports_correctly(self):
        """Test that global API functions are properly exported"""
        # Check that all global functions are in __all__
        expected_exports = [
            "FastJob",
            "job",
            "enqueue",
            "schedule",
            "run_worker",
            "configure",
            "is_dev_mode",
            "has_plugin_feature",
            "get_plugin_status",
            "diagnose_plugins",
        ]

        for export in expected_exports:
            assert export in fastjob.__all__, f"{export} not in __all__"
            assert hasattr(fastjob, export), f"{export} not accessible"

    def test_job_decorator_without_configure(self):
        """Test that job decorator works without explicit configure()"""
        # Don't call configure() - should use default settings

        @fastjob.job()
        async def default_job():
            return "default"

        # Should create global app with default settings
        app = fastjob._get_global_app()
        assert app is not None
        assert app.settings.database_url is not None  # Should have some default

        # Job should be registered
        job_meta = app.get_job_registry().get_job(
            "tests.unit.test_global_api.default_job"
        )
        assert job_meta is not None
