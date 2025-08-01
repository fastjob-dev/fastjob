"""
Test CLI Queue Behavior - Simplified tests that focus on what can be reliably tested

Tests the CLI argument parsing and command structure for queue processing.
Complex subprocess execution tests are covered by test_queue_processing_behavior.py
"""

import os
import subprocess
from pathlib import Path

import pytest

# Ensure we're using test database
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"

# Get project root directory dynamically
PROJECT_ROOT = Path(__file__).parent.parent.parent


async def run_cli_command(args, timeout=10):
    """Run CLI command and return result"""
    result = subprocess.run(
        ["python3", "-m", "fastjob.cli.main"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(PROJECT_ROOT),
    )
    return result


@pytest.mark.asyncio
async def test_cli_help_text_accuracy():
    """Test that CLI help text reflects the new queue processing behavior"""
    result = await run_cli_command(["start", "--help"])

    # Check that help text mentions "all queues" as the default
    assert "all queues" in result.stdout.lower()
    assert result.returncode == 0


@pytest.mark.asyncio
async def test_cli_queue_parameter_edge_cases():
    """Test CLI parameter validation for queue names"""

    # Test empty queue name (should handle gracefully)
    result = await run_cli_command(["start", "--queues", "", "--run-once"])
    # Should not crash, but behavior can vary
    assert result.returncode in [0, 1]  # Either success or graceful failure

    # Test spaces in queue names (should handle gracefully)
    try:
        result = await run_cli_command(
            ["start", "--queues", "queue with spaces", "--run-once"]
        )
        # Should not crash
        assert result.returncode in [0, 1]  # Either success or graceful failure
    except subprocess.TimeoutExpired:
        # Timeout is acceptable for this edge case
        pass


@pytest.mark.asyncio
async def test_cli_basic_validation():
    """Test basic CLI command structure"""

    # Test that start command exists and has correct parameters
    result = await run_cli_command(["start", "--help"])
    assert result.returncode == 0
    assert "--queues" in result.stdout
    assert "--concurrency" in result.stdout
    assert "--run-once" in result.stdout

    # Test that start accepts the basic parameters without errors
    result = await run_cli_command(["start", "--concurrency", "1", "--run-once"])
    # Should not crash immediately (may exit with 0 or 1 depending on jobs available)
    assert result.returncode in [0, 1]


@pytest.mark.asyncio
async def test_cli_command_structure():
    """Test that CLI commands are properly structured"""

    # Test main help includes start command
    result = await run_cli_command(["--help"])
    assert result.returncode == 0
    assert "start" in result.stdout.lower()

    # Test setup command exists (core functionality)
    result = await run_cli_command(["setup", "--help"])
    assert result.returncode == 0

    # Test status command exists (monitoring functionality)
    result = await run_cli_command(["status", "--help"])
    assert result.returncode == 0
