"""
Integration tests for --database-url parameter with core FastJob commands.

These tests verify that the database context system works correctly with
core FastJob CLI commands when using the --database-url parameter.
"""

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent


def run_cli_command(cmd_args, timeout=10, expect_success=True):
    """Run a CLI command and return the result."""
    full_cmd = ["python3", "-m", "fastjob.cli.main"] + cmd_args

    result = subprocess.run(
        full_cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=timeout
    )

    if expect_success and result.returncode != 0:
        pytest.fail(
            f"Command failed: {' '.join(full_cmd)}\n"
            f"Return code: {result.returncode}\n"
            f"Stdout: {result.stdout}\n"
            f"Stderr: {result.stderr}"
        )

    return result


@pytest.fixture(scope="session", autouse=True)
async def setup_test_databases():
    """Set up test databases for database URL integration tests."""
    test_databases = [
        "fastjob_db_url_test_1",
        "fastjob_db_url_test_2",
        "fastjob_db_url_test_3",
    ]

    # Create test databases
    for db_name in test_databases:
        subprocess.run(["createdb", db_name], check=False)

        # Set up each database with FastJob schema using the setup command
        db_url = f"postgresql://postgres@localhost/{db_name}"
        setup_result = subprocess.run(
            ["python3", "-m", "fastjob.cli.main", "setup", "--database-url", db_url],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )

        if setup_result.returncode != 0:
            print(f"Failed to setup {db_name}: {setup_result.stderr}")
            # Continue anyway, some tests might still work

    yield

    # Cleanup databases
    for db_name in test_databases:
        subprocess.run(["dropdb", db_name], check=False)


class TestDatabaseUrlIntegration:
    """Test database URL integration with core FastJob commands."""

    def test_setup_with_database_url(self):
        """Test that setup command works with --database-url parameter."""
        test_db_url = "postgresql://postgres@localhost/fastjob_db_url_test_1"

        result = run_cli_command(["setup", "--database-url", test_db_url])
        assert result.returncode == 0
        assert "Using instance-based configuration" in result.stdout or result.stderr
        assert "Applied" in result.stdout or "Database setup completed" in result.stdout

    def test_migrate_status_with_database_url(self):
        """Test that migrate-status command works with --database-url parameter."""
        test_db_url = "postgresql://postgres@localhost/fastjob_db_url_test_1"

        result = run_cli_command(["migrate-status", "--database-url", test_db_url])
        assert result.returncode == 0
        assert "Using instance-based configuration" in result.stdout or result.stderr

    def test_status_with_database_url(self):
        """Test that status command works with --database-url parameter."""
        test_db_url = "postgresql://postgres@localhost/fastjob_db_url_test_1"

        result = run_cli_command(["status", "--database-url", test_db_url])
        assert result.returncode == 0
        assert "Using instance-based configuration" in result.stdout or result.stderr

    def test_workers_with_database_url(self):
        """Test that workers command works with --database-url parameter."""
        test_db_url = "postgresql://postgres@localhost/fastjob_db_url_test_1"

        result = run_cli_command(["workers", "--database-url", test_db_url])
        assert result.returncode == 0
        assert "Using instance-based configuration" in result.stdout or result.stderr

    def test_start_worker_with_database_url(self):
        """Test that start command works with --database-url parameter."""
        test_db_url = "postgresql://postgres@localhost/fastjob_db_url_test_1"

        # Use --run-once to exit quickly
        result = run_cli_command(
            [
                "start",
                "--database-url",
                test_db_url,
                "--run-once",
                "--concurrency",
                "1",
            ],
            timeout=5,
        )
        assert result.returncode == 0
        assert "Using instance-based configuration" in result.stdout or result.stderr

    def test_multiple_database_urls_isolation(self):
        """Test that different --database-url parameters target different databases."""
        test_db_url_1 = "postgresql://postgres@localhost/fastjob_db_url_test_1"
        test_db_url_2 = "postgresql://postgres@localhost/fastjob_db_url_test_2"

        # Both should work independently
        result1 = run_cli_command(["status", "--database-url", test_db_url_1])
        result2 = run_cli_command(["status", "--database-url", test_db_url_2])

        assert result1.returncode == 0
        assert result2.returncode == 0

        # Both should show instance-based configuration
        assert "Using instance-based configuration" in result1.stdout or result1.stderr
        assert "Using instance-based configuration" in result2.stdout or result2.stderr


class TestDatabaseContextSystem:
    """Test the database context system directly."""

    def test_database_context_creation(self):
        """Test that database context can be created for different scenarios."""
        from fastjob import FastJob
        from fastjob.db.context import DatabaseContext

        # Test global API context
        global_context = DatabaseContext.from_global_api()
        assert global_context is not None

        # Test instance context
        instance = FastJob(database_url="postgresql://localhost/test")
        instance_context = DatabaseContext.from_instance(instance)
        assert instance_context is not None

        # Test direct URL context
        url_context = DatabaseContext.from_database_url("postgresql://localhost/test")
        assert url_context is not None

    @pytest.mark.asyncio
    async def test_context_manager_integration(self):
        """Test that context manager works with CLI commands."""
        from fastjob import FastJob
        from fastjob.db.context import (
            DatabaseContext,
            get_current_context,
            set_current_context,
        )

        # Create instance and context
        instance = FastJob(
            database_url="postgresql://postgres@localhost/fastjob_db_url_test_1"
        )
        context = DatabaseContext.from_instance(instance)

        # Set context
        set_current_context(context)

        # Get context should return the same instance
        current_context = get_current_context()
        assert current_context is context

        # Context should have the correct database URL
        assert (
            current_context.database_url
            == "postgresql://postgres@localhost/fastjob_db_url_test_1"
        )

    @pytest.mark.asyncio
    async def test_context_pool_access(self):
        """Test that context provides correct database pool access."""
        from fastjob import FastJob
        from fastjob.db.context import DatabaseContext

        # Create instance and context
        instance = FastJob(
            database_url="postgresql://postgres@localhost/fastjob_db_url_test_1"
        )
        context = DatabaseContext.from_instance(instance)

        # Should be able to get pool
        pool = await context.get_pool()
        assert pool is not None

        # Clean up
        await instance.close()


class TestBackwardsCompatibility:
    """Test that Global API usage is unchanged by new Instance API features."""

    def test_global_api_cli_commands_unchanged(self):
        """Test that Global API CLI commands work without --database-url."""
        # These should work exactly as before (using environment variables)
        original_env = os.environ.copy()

        try:
            # Set global database URL
            os.environ["FASTJOB_DATABASE_URL"] = (
                "postgresql://postgres@localhost/fastjob_db_url_test_1"
            )

            # Commands should work without --database-url parameter
            result = run_cli_command(["status"])
            assert result.returncode == 0
            assert "Using global API configuration" in result.stdout or result.stderr

            result = run_cli_command(["workers"])
            assert result.returncode == 0
            assert "Using global API configuration" in result.stdout or result.stderr

        finally:
            # Restore original environment
            os.environ.clear()
            os.environ.update(original_env)

    def test_global_api_python_imports_unchanged(self):
        """Test that Global API Python imports work unchanged."""
        # These imports should work exactly as before
        import fastjob
        from fastjob import FastJob
        from fastjob.db.context import DatabaseContext

        # Global API should still be available
        assert hasattr(fastjob, "job")
        assert hasattr(fastjob, "enqueue")

        # Instance API should also be available
        assert FastJob is not None
        assert DatabaseContext is not None
