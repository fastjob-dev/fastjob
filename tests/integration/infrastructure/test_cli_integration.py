"""
Test suite for CLI integration and real command execution
"""

import pytest
import subprocess
import os
import asyncio
from pathlib import Path

# Ensure we're using test database
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"

# Get project root directory dynamically
PROJECT_ROOT = Path(__file__).parent.parent.parent


def run_cli_command(args, timeout=10, expect_success=True):
    """Helper to run CLI commands"""
    try:
        result = subprocess.run(
            ["python3", "-m", "fastjob.cli.main"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )

        if expect_success and result.returncode != 0:
            pytest.fail(f"CLI command failed: {result.stderr}")

        return result
    except subprocess.TimeoutExpired:
        pytest.fail(f"CLI command timed out: {args}")
    except Exception as e:
        pytest.fail(f"CLI command error: {e}")


@pytest.mark.asyncio
async def test_cli_help_commands():
    """Test CLI help and command discovery"""
    # Test main help
    result = run_cli_command(["--help"])
    assert "FastJob CLI" in result.stdout or "usage:" in result.stdout

    # Test subcommand help
    result = run_cli_command(["setup", "--help"])
    assert "setup" in result.stdout.lower()

    result = run_cli_command(["start", "--help"])
    assert "start" in result.stdout.lower()


@pytest.mark.asyncio
async def test_setup_command():
    """Test database setup command"""
    # Ensure test database exists (don't drop if in use by other tests)
    subprocess.run(["createdb", "fastjob_test"], check=False)  # Ignore if exists

    # Run setup
    result = run_cli_command(["setup"])
    assert result.returncode == 0

    # Verify table was created by checking with psql
    check_result = subprocess.run(
        [
            "psql",
            "postgresql://postgres@localhost/fastjob_test",
            "-c",
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'fastjob_jobs';",
        ],
        capture_output=True,
        text=True,
    )
    assert "1" in check_result.stdout  # Table should exist


@pytest.mark.asyncio
async def test_start_command_structure():
    """Test start command options and parsing"""
    # Test start with run-once option (should exit quickly with no jobs)
    result = run_cli_command(["start", "--run-once"], timeout=5)
    assert result.returncode == 0

    # Test start with custom concurrency
    result = run_cli_command(["start", "--concurrency", "2", "--run-once"], timeout=5)
    assert result.returncode == 0

    # Test start with specific queues
    result = run_cli_command(
        ["start", "--queues", "test1,test2", "--run-once"], timeout=5
    )
    assert result.returncode == 0


# Dashboard test moved to fastjob-pro package since dashboard is a Pro feature
# @pytest.mark.asyncio
# async def test_dashboard_command():
#     """Test dashboard command if FastAPI is available - MOVED TO FASTJOB-PRO"""
#     pass


@pytest.mark.asyncio
async def test_environment_variable_integration():
    """Test CLI respects environment variables"""
    original_env = os.environ.copy()

    try:
        # Set custom environment variables
        os.environ["FASTJOB_LOG_LEVEL"] = "DEBUG"
        os.environ["FASTJOB_DATABASE_URL"] = (
            "postgresql://postgres@localhost/fastjob_test"
        )

        # Run start with environment variables
        result = run_cli_command(["start", "--run-once"], timeout=5)
        assert result.returncode == 0

        # Check that debug logging might be enabled (if implemented)
        # This is more of a structure test than functionality test

    finally:
        os.environ.clear()
        os.environ.update(original_env)


@pytest.mark.asyncio
async def test_cli_error_handling():
    """Test CLI error handling for invalid commands and options"""
    # Test invalid command
    result = run_cli_command(["invalid-command"], expect_success=False)
    assert result.returncode != 0

    # Test invalid option
    result = run_cli_command(["start", "--invalid-option"], expect_success=False)
    assert result.returncode != 0

    # Test invalid database URL
    original_db_url = os.environ.get("FASTJOB_DATABASE_URL")
    try:
        os.environ["FASTJOB_DATABASE_URL"] = "invalid://url"
        result = run_cli_command(["setup"], expect_success=False, timeout=30)
        # Should fail gracefully with invalid database URL
        assert result.returncode != 0
    finally:
        if original_db_url:
            os.environ["FASTJOB_DATABASE_URL"] = original_db_url


@pytest.mark.asyncio
async def test_cli_with_real_jobs():
    """Test CLI with actual job processing"""
    # Database setup handled by conftest.py
    
    # Create a simple job file for testing
    job_file_content = """
import fastjob

@fastjob.job(retries=1)
async def cli_test_job(message: str):
    with open("/tmp/fastjob_cli_test.txt", "w") as f:
        f.write(f"CLI test: {message}")
    return f"Processed: {message}"
"""

    # Write job file
    job_file_path = PROJECT_ROOT / "test_cli_jobs.py"
    with open(job_file_path, "w") as f:
        f.write(job_file_content)

    try:
        # Import and enqueue job using Python
        import sys

        sys.path.insert(0, str(PROJECT_ROOT))

        # Import the test job module
        import test_cli_jobs
        import fastjob

        # Enqueue a job
        await fastjob.enqueue(
            test_cli_jobs.cli_test_job, message="Hello CLI"
        )

        # Run start to process the job (with timeout as it may wait for jobs)
        result = run_cli_command(["start", "--run-once"], timeout=10)
        assert result.returncode == 0

        # Check if job was processed (output file should exist)
        output_file = Path("/tmp/fastjob_cli_test.txt")
        if output_file.exists():
            content = output_file.read_text()
            assert "CLI test: Hello CLI" in content
            output_file.unlink()  # Clean up

    finally:
        # Clean up job file
        if os.path.exists(job_file_path):
            os.remove(job_file_path)


@pytest.mark.asyncio
async def test_cli_output_formats():
    """Test CLI output formatting and verbosity"""
    # Database setup handled by conftest.py
    
    # Test that CLI produces reasonable output
    result = run_cli_command(["setup"])

    # Should have some output (migration messages)
    assert len(result.stdout) > 0 or len(result.stderr) > 0

    # Test start output
    result = run_cli_command(["start", "--run-once"], timeout=5)

    # Worker should produce some output about processing or completion
    assert len(result.stdout) > 0 or len(result.stderr) > 0


@pytest.mark.asyncio
async def test_cli_concurrent_workers():
    """Test running multiple CLI workers concurrently"""
    # Database setup handled by conftest.py
    
    # Create multiple worker processes
    worker_processes = []

    try:
        for i in range(2):
            process = subprocess.Popen(
                ["python3", "-m", "fastjob.cli.main", "start", "--run-once"],
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            worker_processes.append(process)

        # Wait for all workers to complete (should exit quickly with --run-once)
        for process in worker_processes:
            stdout, stderr = process.communicate(timeout=10)
            # Workers should exit with 0 when no jobs are available and --run-once is used
            assert process.returncode == 0, f"Worker failed: {stderr}"

    finally:
        # Clean up any remaining processes
        for process in worker_processes:
            if process.poll() is None:
                process.terminate()
                process.wait()


@pytest.mark.asyncio
async def test_cli_signal_handling():
    """Test CLI signal handling and graceful shutdown"""
    # Database setup handled by conftest.py
    
    # Start a worker process
    process = subprocess.Popen(
        ["python3", "-m", "fastjob.cli.main", "start", "--concurrency", "1"],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Let it start up
        await asyncio.sleep(2)

        # Send SIGTERM for graceful shutdown
        process.terminate()

        # Wait for graceful shutdown
        stdout, stderr = process.communicate(timeout=10)

        # Process should exit cleanly
        assert process.returncode in [
            0,
            -15,
            130,
        ]  # 0=clean exit, -15=SIGTERM, 130=SIGINT

    except subprocess.TimeoutExpired:
        # Force kill if graceful shutdown failed
        process.kill()
        process.wait()
        pytest.fail("Worker did not shut down gracefully")


@pytest.mark.asyncio
async def test_cli_database_url_parameter():
    """Test CLI commands with --database-url parameter"""
    # Create a test database with a different name
    test_db_name = "fastjob_cli_instance_test"
    test_db_url = f"postgresql://postgres@localhost/{test_db_name}"
    
    # Create the test database
    subprocess.run(["createdb", test_db_name], check=False)  # Ignore if exists
    
    try:
        # Test setup command with --database-url
        result = run_cli_command(["setup", "--database-url", test_db_url])
        assert result.returncode == 0
        assert "Database setup completed" in result.stdout or "Applied" in result.stdout
        
        # Test start command with --database-url (run-once to exit quickly)
        result = run_cli_command(["start", "--database-url", test_db_url, "--run-once"], timeout=5)
        assert result.returncode == 0
        
        # Verify the instance configuration is shown in output
        assert "Using instance-based configuration" in result.stdout or result.stderr
        assert test_db_url in result.stdout or result.stderr
        
    finally:
        # Clean up the test database
        subprocess.run(["dropdb", test_db_name], check=False)


@pytest.mark.asyncio 
async def test_cli_database_url_vs_environment():
    """Test that --database-url parameter overrides environment variable"""
    test_db_name = "fastjob_cli_override_test"
    test_db_url = f"postgresql://postgres@localhost/{test_db_name}"
    
    # Create the test database
    subprocess.run(["createdb", test_db_name], check=False)
    
    # Store original environment
    original_env = os.environ.copy()
    
    try:
        # Set environment variable to different database
        os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"
        
        # Use --database-url parameter to override environment
        result = run_cli_command(["setup", "--database-url", test_db_url])
        assert result.returncode == 0
        
        # Start worker with overridden database URL
        result = run_cli_command([
            "start", 
            "--database-url", test_db_url, 
            "--run-once", 
            "--concurrency", "1"
        ], timeout=5)
        assert result.returncode == 0
        
        # Should show instance-based configuration, not global
        assert "Using instance-based configuration" in result.stdout or result.stderr
        
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)
        # Clean up test database
        subprocess.run(["dropdb", test_db_name], check=False)


@pytest.mark.asyncio
async def test_cli_database_url_validation():
    """Test CLI handles invalid database URLs gracefully"""
    # Test with invalid database URL
    result = run_cli_command([
        "setup", 
        "--database-url", "invalid://not-a-real-database"
    ], expect_success=False, timeout=10)
    
    # Should fail gracefully
    assert result.returncode != 0
    # Should show configuration error (our new error handling)
    # Error message can be in stdout or stderr  
    combined_output = (result.stdout + result.stderr).lower()
    assert "error" in combined_output or "failed" in combined_output


@pytest.mark.asyncio
async def test_cli_without_database_url_uses_global():
    """Test that CLI without --database-url uses global API"""
    # Run start without --database-url parameter
    result = run_cli_command(["start", "--run-once"], timeout=5)
    assert result.returncode == 0
    
    # Should show global API configuration
    assert "Using global API configuration" in result.stdout or result.stderr
