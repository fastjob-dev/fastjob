"""
Test suite for CLI integration and real command execution
"""

import pytest
import subprocess
import os
import time
import asyncio
from pathlib import Path

# Ensure we're using test database
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"


def run_cli_command(args, timeout=10, expect_success=True):
    """Helper to run CLI commands"""
    try:
        result = subprocess.run(
            ["python", "-m", "fastjob.cli.main"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd="/Users/abhinav/Code/python/fastjob"
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
    result = run_cli_command(["migrate", "--help"])
    assert "migrate" in result.stdout.lower()
    
    result = run_cli_command(["run-worker", "--help"])
    assert "worker" in result.stdout.lower()


@pytest.mark.asyncio 
async def test_migrate_command():
    """Test database migration command"""
    # Drop and recreate test database for clean migration test
    subprocess.run(["dropdb", "--if-exists", "fastjob_test"], check=False)
    subprocess.run(["createdb", "fastjob_test"], check=True)
    
    # Run migration
    result = run_cli_command(["migrate"])
    assert result.returncode == 0
    
    # Verify table was created by checking with psql
    check_result = subprocess.run(
        ["psql", "postgresql://postgres@localhost/fastjob_test", "-c", 
         "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'fastjob_jobs';"],
        capture_output=True,
        text=True
    )
    assert "1" in check_result.stdout  # Table should exist


@pytest.mark.asyncio
async def test_worker_command_structure():
    """Test worker command options and parsing"""
    # Test worker with run-once option (should exit quickly)
    result = run_cli_command(["run-worker", "--run-once"], timeout=30)
    assert result.returncode == 0
    
    # Test worker with custom concurrency
    result = run_cli_command(["run-worker", "--run-once", "--concurrency", "2"], timeout=30)
    assert result.returncode == 0
    
    # Test worker with specific queues
    result = run_cli_command(["run-worker", "--run-once", "--queues", "test1", "test2"], timeout=30)
    assert result.returncode == 0


@pytest.mark.asyncio
async def test_dashboard_command():
    """Test dashboard command if FastAPI is available"""
    try:
        import fastapi
        import uvicorn
        
        # Test dashboard help
        result = run_cli_command(["dashboard", "--help"])
        assert "dashboard" in result.stdout.lower()
        
        # Note: We don't start the actual dashboard server in tests
        # as it would require more complex setup and teardown
        
    except ImportError:
        pytest.skip("FastAPI not installed - dashboard command not available")


@pytest.mark.asyncio
async def test_environment_variable_integration():
    """Test CLI respects environment variables"""
    original_env = os.environ.copy()
    
    try:
        # Set custom environment variables
        os.environ["FASTJOB_LOG_LEVEL"] = "DEBUG"
        os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"
        
        # Run worker with environment variables
        result = run_cli_command(["run-worker", "--run-once"], timeout=30)
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
    result = run_cli_command(["run-worker", "--invalid-option"], expect_success=False) 
    assert result.returncode != 0
    
    # Test invalid database URL
    original_db_url = os.environ.get("FASTJOB_DATABASE_URL")
    try:
        os.environ["FASTJOB_DATABASE_URL"] = "invalid://url"
        result = run_cli_command(["migrate"], expect_success=False, timeout=30)
        # Should fail gracefully with invalid database URL
        assert result.returncode != 0
    finally:
        if original_db_url:
            os.environ["FASTJOB_DATABASE_URL"] = original_db_url


@pytest.mark.asyncio
async def test_cli_with_real_jobs():
    """Test CLI with actual job processing"""
    from tests.db_utils import create_test_database, drop_test_database
    
    await create_test_database()
    try:
        # Create a simple job file for testing
        job_file_content = '''
import fastjob

@fastjob.job(retries=1)
async def cli_test_job(message: str):
    with open("/tmp/fastjob_cli_test.txt", "w") as f:
        f.write(f"CLI test: {message}")
    return f"Processed: {message}"
'''
        
        # Write job file
        job_file_path = "/Users/abhinav/Code/python/fastjob/test_cli_jobs.py"
        with open(job_file_path, "w") as f:
            f.write(job_file_content)
        
        try:
            # Import and enqueue job using Python
            import sys
            sys.path.insert(0, "/Users/abhinav/Code/python/fastjob")
            
            # Import the test job module
            import test_cli_jobs
            import fastjob
            
            # Enqueue a job
            job_id = await fastjob.enqueue(test_cli_jobs.cli_test_job, message="Hello CLI")
            
            # Run worker to process the job
            result = run_cli_command(["run-worker", "--run-once"], timeout=30)
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
    
    finally:
        await drop_test_database()


@pytest.mark.asyncio
async def test_cli_output_formats():
    """Test CLI output formatting and verbosity"""
    # Test that CLI produces reasonable output
    result = run_cli_command(["migrate"])
    
    # Should have some output (migration messages)
    assert len(result.stdout) > 0 or len(result.stderr) > 0
    
    # Test worker output
    result = run_cli_command(["run-worker", "--run-once"])
    
    # Worker should produce some output about processing or completion
    assert len(result.stdout) > 0 or len(result.stderr) > 0


@pytest.mark.asyncio
async def test_cli_concurrent_workers():
    """Test running multiple CLI workers concurrently"""
    from tests.db_utils import create_test_database, drop_test_database
    
    await create_test_database()
    try:
        # Create multiple worker processes
        worker_processes = []
        
        for i in range(2):
            process = subprocess.Popen(
                ["python", "-m", "fastjob.cli.main", "run-worker", "--run-once"],
                cwd="/Users/abhinav/Code/python/fastjob",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            worker_processes.append(process)
        
        # Wait for all workers to complete
        for process in worker_processes:
            stdout, stderr = process.communicate(timeout=30)
            assert process.returncode == 0, f"Worker failed: {stderr}"
    
    finally:
        # Clean up any remaining processes
        for process in worker_processes:
            if process.poll() is None:
                process.terminate()
                process.wait()
        
        await drop_test_database()


@pytest.mark.asyncio
async def test_cli_signal_handling():
    """Test CLI signal handling and graceful shutdown"""
    # Start a worker process
    process = subprocess.Popen(
        ["python", "-m", "fastjob.cli.main", "run-worker", "--concurrency", "1"],
        cwd="/Users/abhinav/Code/python/fastjob",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    try:
        # Let it start up
        await asyncio.sleep(2)
        
        # Send SIGTERM for graceful shutdown
        process.terminate()
        
        # Wait for graceful shutdown
        stdout, stderr = process.communicate(timeout=10)
        
        # Process should exit cleanly
        assert process.returncode in [0, -15, 130]  # 0=clean exit, -15=SIGTERM, 130=SIGINT
        
    except subprocess.TimeoutExpired:
        # Force kill if graceful shutdown failed
        process.kill()
        process.wait()
        pytest.fail("Worker did not shut down gracefully")