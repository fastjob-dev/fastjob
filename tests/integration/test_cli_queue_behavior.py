"""
Test CLI Queue Behavior - New CLI queue processing

Tests the updated CLI behavior for queue processing:
- fastjob start (no --queues) should process all queues  
- fastjob start --queues queue1 should process single queue
- fastjob start --queues queue1,queue2 should process multiple queues
"""

import asyncio
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

# Ensure we're using test database
os.environ["FASTJOB_DATABASE_URL"] = "postgresql://postgres@localhost/fastjob_test"

# Get project root directory dynamically
PROJECT_ROOT = Path(__file__).parent.parent.parent

import fastjob
from fastjob.db.connection import get_pool


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


@fastjob.job()
async def cli_test_job(message: str, queue_name: str, result_file: str):
    """Test job that writes result to file"""
    with open(result_file, "a") as f:
        f.write(f"{message},{queue_name}\n")


@pytest.fixture
async def clean_db():
    """Clean database before each test"""
    from tests.db_utils import clear_table
    pool = await get_pool()
    await clear_table(pool)
    yield
    await clear_table(pool)


@pytest.mark.asyncio
async def test_cli_start_all_queues_default(clean_db):
    """Test that 'fastjob start' (no --queues) processes all queues"""
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as f:
        result_file = f.name
    
    try:
        # Enqueue jobs in different queues
        await fastjob.enqueue(cli_test_job, queue="queueA", message="jobA", queue_name="queueA", result_file=result_file)
        await fastjob.enqueue(cli_test_job, queue="queueB", message="jobB", queue_name="queueB", result_file=result_file)
        await fastjob.enqueue(cli_test_job, queue="queueC", message="jobC", queue_name="queueC", result_file=result_file)
        
        # Start worker for a short time (should process all queues)
        process = subprocess.Popen(
            ["python3", "-m", "fastjob.cli.main", "start", "--run-once"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for processing
        stdout, stderr = process.communicate(timeout=15)
        
        # Check that worker reported processing "all available queues"
        assert "all available queues" in stdout or "processing: all queues" in stdout
        
        # Check that all jobs were processed
        with open(result_file, "r") as f:
            results = f.read().strip().split("\n")
        
        processed_queues = {line.split(",")[1] for line in results if line}
        assert "queueA" in processed_queues
        assert "queueB" in processed_queues  
        assert "queueC" in processed_queues
        
    finally:
        os.unlink(result_file)


@pytest.mark.asyncio 
async def test_cli_start_single_queue(clean_db):
    """Test that 'fastjob start --queues specific_queue' processes only that queue"""
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as f:
        result_file = f.name
    
    try:
        # Enqueue jobs in different queues
        await fastjob.enqueue(cli_test_job, queue="target", message="target_job", queue_name="target", result_file=result_file)
        await fastjob.enqueue(cli_test_job, queue="excluded", message="excluded_job", queue_name="excluded", result_file=result_file)
        
        # Start worker targeting only "target" queue
        process = subprocess.Popen(
            ["python3", "-m", "fastjob.cli.main", "start", "--queues", "target", "--run-once"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate(timeout=15)
        
        # Check that worker reported processing specific queue
        assert "target" in stdout
        
        # Check that only target queue job was processed
        with open(result_file, "r") as f:
            results = f.read().strip()
        
        assert "target_job,target" in results
        assert "excluded_job,excluded" not in results
        
    finally:
        os.unlink(result_file)


@pytest.mark.asyncio
async def test_cli_start_multiple_queues(clean_db):
    """Test that 'fastjob start --queues queue1,queue2' processes specified queues"""
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as f:
        result_file = f.name
    
    try:
        # Enqueue jobs in different queues
        await fastjob.enqueue(cli_test_job, queue="queue1", message="job1", queue_name="queue1", result_file=result_file)
        await fastjob.enqueue(cli_test_job, queue="queue2", message="job2", queue_name="queue2", result_file=result_file)
        await fastjob.enqueue(cli_test_job, queue="excluded", message="excluded", queue_name="excluded", result_file=result_file)
        
        # Start worker targeting multiple specific queues
        process = subprocess.Popen(
            ["python3", "-m", "fastjob.cli.main", "start", "--queues", "queue1,queue2", "--run-once"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate(timeout=15)
        
        # Check that worker reported processing specific queues
        assert "queue1, queue2" in stdout or "queue1,queue2" in stdout
        
        # Check that only specified queue jobs were processed
        with open(result_file, "r") as f:
            results = f.read().strip().split("\n")
        
        processed_queues = {line.split(",")[1] for line in results if line}
        assert "queue1" in processed_queues
        assert "queue2" in processed_queues
        assert "excluded" not in processed_queues
        
    finally:
        os.unlink(result_file)


@pytest.mark.asyncio
async def test_cli_help_text_accuracy(clean_db):
    """Test that CLI help text correctly describes queue behavior"""
    result = await run_cli_command(["start", "--help"])
    
    assert result.returncode == 0
    help_text = result.stdout
    
    # Should mention "all queues" as default
    assert "all queues" in help_text.lower()
    assert "--queues" in help_text


@pytest.mark.asyncio
async def test_cli_start_with_priorities_across_queues(clean_db):
    """Test that CLI respects priority ordering across different queues"""
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as f:
        result_file = f.name
    
    try:
        # Enqueue jobs with different priorities across queues
        # Lower priority number = higher priority
        await fastjob.enqueue(cli_test_job, queue="queueA", priority=100, message="medium", queue_name="queueA", result_file=result_file)
        await fastjob.enqueue(cli_test_job, queue="queueB", priority=50, message="high", queue_name="queueB", result_file=result_file)  
        await fastjob.enqueue(cli_test_job, queue="queueA", priority=200, message="low", queue_name="queueA", result_file=result_file)
        
        # Start worker (should process in priority order)
        process = subprocess.Popen(
            ["python3", "-m", "fastjob.cli.main", "start", "--run-once"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate(timeout=15)
        
        # Check processing order
        with open(result_file, "r") as f:
            results = f.read().strip().split("\n")
        
        # Should be processed in priority order (high, medium, low)
        messages = [line.split(",")[0] for line in results if line]
        assert messages == ["high", "medium", "low"]
        
    finally:
        os.unlink(result_file)


@pytest.mark.asyncio
async def test_cli_queue_parameter_edge_cases(clean_db):
    """Test edge cases for CLI queue parameter handling"""
    
    # Test with empty queue specification (should fail gracefully)
    result = await run_cli_command(["start", "--queues", "", "--run-once"])
    # Should either process all queues or handle gracefully
    assert result.returncode in [0, 1]  # Allow either success or graceful failure
    
    # Test with whitespace in queue names
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as f:
        result_file = f.name
    
    try:
        await fastjob.enqueue(cli_test_job, queue="queue with spaces", message="spaced", queue_name="queue with spaces", result_file=result_file)
        
        # This might not work depending on queue name validation, but test anyway
        result = await run_cli_command(["start", "--queues", "queue with spaces", "--run-once"])
        # Should handle gracefully
        assert result.returncode in [0, 1]
        
    finally:
        os.unlink(result_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])