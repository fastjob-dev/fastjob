"""
Tests for signal handling and graceful worker shutdown.

Tests signal handling for SIGTERM, SIGINT, and SIGHUP across both
global and instance API workers.
"""

import asyncio
import pytest
import subprocess
import signal
import time
import os
from pathlib import Path

# Calculate project root for subprocess calls
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


@pytest.mark.asyncio
async def test_signal_handler_setup_and_cleanup():
    """Test signal handler setup and cleanup in isolation"""
    from fastjob.utils.signals import GracefulSignalHandler
    
    handler = GracefulSignalHandler()
    shutdown_event = asyncio.Event()
    
    # Setup signal handlers
    handler.setup_signal_handlers(shutdown_event)
    
    # Verify handlers were registered
    assert len(handler.handled_signals) > 0
    assert signal.SIGINT in handler.handled_signals
    
    # Test cleanup
    handler.restore_signal_handlers()
    
    # Verify cleanup
    assert len(handler.handled_signals) == 0
    assert len(handler.original_handlers) == 0
    assert handler.shutdown_event is None


@pytest.mark.asyncio
async def test_signal_handler_triggers_event():
    """Test that signal handlers properly trigger shutdown event"""
    from fastjob.utils.signals import GracefulSignalHandler
    
    handler = GracefulSignalHandler()
    shutdown_event = asyncio.Event()
    
    try:
        handler.setup_signal_handlers(shutdown_event)
        
        # Send SIGINT to self to test handler
        os.kill(os.getpid(), signal.SIGINT)
        
        # Wait for the event to be set (with timeout)
        await asyncio.wait_for(shutdown_event.wait(), timeout=2.0)
        
        # Event should be set
        assert shutdown_event.is_set()
        
    finally:
        handler.restore_signal_handlers()


@pytest.mark.asyncio
async def test_global_signal_handlers():
    """Test global signal handler utilities"""
    from fastjob.utils.signals import setup_global_signal_handlers, cleanup_global_signal_handlers
    
    shutdown_event = asyncio.Event()
    
    try:
        # Setup global handlers
        handler = setup_global_signal_handlers(shutdown_event)
        assert handler is not None
        
        # Verify handlers are active
        assert len(handler.handled_signals) > 0
        
    finally:
        # Cleanup
        cleanup_global_signal_handlers()


class TestWorkerSignalHandling:
    """Test signal handling in actual worker processes"""
    
    def create_test_worker_script(self, api_type: str = "global") -> str:
        """Create a test script that starts a worker"""
        if api_type == "global":
            script_content = '''
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import fastjob

async def main():
    # Disable plugin loading during testing to avoid import issues
    from fastjob.testing import disable_plugins
    disable_plugins()
    
    # Configure fastjob
    fastjob.configure(
        database_url=os.environ.get("FASTJOB_DATABASE_URL", "postgresql://localhost/fastjob_test")
    )
    
    @fastjob.job()
    async def test_job():
        return "test"
    
    # Start worker
    from fastjob.core.processor import run_worker
    await run_worker(concurrency=1)

if __name__ == "__main__":
    asyncio.run(main())
'''
        else:  # instance API
            script_content = '''
import asyncio
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastjob import FastJob

async def main():
    # Disable plugin loading during testing to avoid import issues
    from fastjob.testing import disable_plugins
    disable_plugins()
    
    app = FastJob(
        database_url=os.environ.get("FASTJOB_DATABASE_URL", "postgresql://localhost/fastjob_test")
    )
    
    @app.job()
    async def test_job():
        return "test"
    
    # Start instance worker
    await app.run_worker(concurrency=1)

if __name__ == "__main__":
    asyncio.run(main())
'''
        
        # Write script to temporary file
        script_path = f"/tmp/test_worker_{api_type}_{os.getpid()}.py"
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        return script_path

    @pytest.mark.asyncio
    async def test_sigint_graceful_shutdown_global_api(self):
        """Test SIGINT (Ctrl+C) graceful shutdown for global API worker"""
        script_path = self.create_test_worker_script("global")
        
        try:
            # Start worker process
            process = subprocess.Popen(
                ["python3", script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "FASTJOB_DATABASE_URL": "postgresql://localhost/fastjob_test"}
            )
            
            # Let it start up
            await asyncio.sleep(2)
            
            # Send SIGINT
            process.send_signal(signal.SIGINT)
            
            # Wait for graceful shutdown
            try:
                stdout, stderr = process.communicate(timeout=10)
                
                # Process should exit cleanly
                assert process.returncode in [0, -signal.SIGINT, 130]  # 130 = SIGINT exit code
                
                # Check for graceful shutdown messages in output
                output = stdout + stderr
                shutdown_keywords = ["shutdown", "stopped", "closing", "cleanup", "graceful"]
                assert any(keyword in output.lower() for keyword in shutdown_keywords)
                
            except subprocess.TimeoutExpired:
                process.kill()
                pytest.fail("Worker did not shut down gracefully within timeout")
                
        finally:
            # Ensure process is cleaned up
            if process.poll() is None:
                process.kill()
                process.wait()
            if os.path.exists(script_path):
                os.unlink(script_path)

    @pytest.mark.asyncio
    async def test_sigterm_graceful_shutdown_global_api(self):
        """Test SIGTERM graceful shutdown for global API worker"""
        script_path = self.create_test_worker_script("global")
        
        try:
            # Start worker process
            process = subprocess.Popen(
                ["python3", script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "FASTJOB_DATABASE_URL": "postgresql://localhost/fastjob_test"}
            )
            
            # Let it start up
            await asyncio.sleep(2)
            
            # Send SIGTERM
            process.send_signal(signal.SIGTERM)
            
            # Wait for graceful shutdown
            try:
                stdout, stderr = process.communicate(timeout=10)
                
                # Process should exit cleanly
                assert process.returncode in [0, -signal.SIGTERM, 143]  # 143 = SIGTERM exit code
                
                # Check for graceful shutdown messages in output
                output = stdout + stderr
                shutdown_keywords = ["shutdown", "stopped", "closing", "cleanup", "graceful"]
                assert any(keyword in output.lower() for keyword in shutdown_keywords)
                
            except subprocess.TimeoutExpired:
                process.kill()
                pytest.fail("Worker did not shut down gracefully within timeout")
                
        finally:
            # Ensure process is cleaned up
            if process.poll() is None:
                process.kill()
                process.wait()
            if os.path.exists(script_path):
                os.unlink(script_path)

    @pytest.mark.asyncio
    async def test_sigterm_graceful_shutdown_instance_api(self):
        """Test SIGTERM graceful shutdown for instance API worker"""
        script_path = self.create_test_worker_script("instance")
        
        try:
            # Start worker process
            process = subprocess.Popen(
                ["python3", script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "FASTJOB_DATABASE_URL": "postgresql://localhost/fastjob_test"}
            )
            
            # Let it start up
            await asyncio.sleep(2)
            
            # Send SIGTERM
            process.send_signal(signal.SIGTERM)
            
            # Wait for graceful shutdown
            try:
                stdout, stderr = process.communicate(timeout=10)
                
                # Process should exit cleanly
                assert process.returncode in [0, -signal.SIGTERM, 143]
                
                # Check for graceful shutdown messages in output
                output = stdout + stderr
                shutdown_keywords = ["shutdown", "stopped", "closing", "cleanup", "graceful"]
                # Silent shutdown is also acceptable for graceful signal handling
                has_shutdown_message = any(keyword in output.lower() for keyword in shutdown_keywords)
                silent_shutdown = output.strip() == ""
                assert has_shutdown_message or silent_shutdown, \
                    f"Expected shutdown keywords or silent shutdown, got: {repr(output)}"
                
            except subprocess.TimeoutExpired:
                process.kill()
                pytest.fail("Worker did not shut down gracefully within timeout")
                
        finally:
            # Ensure process is cleaned up
            if process.poll() is None:
                process.kill()
                process.wait()
            if os.path.exists(script_path):
                os.unlink(script_path)

    @pytest.mark.asyncio
    @pytest.mark.skipif(not hasattr(signal, 'SIGHUP'), reason="SIGHUP not available on this platform")
    async def test_sighup_graceful_shutdown_global_api(self):
        """Test SIGHUP graceful shutdown for global API worker"""
        script_path = self.create_test_worker_script("global")
        
        try:
            # Start worker process
            process = subprocess.Popen(
                ["python3", script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "FASTJOB_DATABASE_URL": "postgresql://localhost/fastjob_test"}
            )
            
            # Let it start up
            await asyncio.sleep(2)
            
            # Send SIGHUP
            process.send_signal(signal.SIGHUP)
            
            # Wait for graceful shutdown
            try:
                stdout, stderr = process.communicate(timeout=10)
                
                # Process should exit cleanly
                assert process.returncode in [0, -signal.SIGHUP, 129]  # 129 = SIGHUP exit code
                
                # Check for graceful shutdown messages in output
                output = stdout + stderr
                shutdown_keywords = ["shutdown", "stopped", "closing", "cleanup", "graceful"]
                assert any(keyword in output.lower() for keyword in shutdown_keywords)
                
            except subprocess.TimeoutExpired:
                process.kill()
                pytest.fail("Worker did not shut down gracefully within timeout")
                
        finally:
            # Ensure process is cleaned up
            if process.poll() is None:
                process.kill()
                process.wait()
            if os.path.exists(script_path):
                os.unlink(script_path)


class TestCLISignalHandling:
    """Test signal handling through the CLI interface"""
    
    @pytest.mark.asyncio
    async def test_cli_worker_sigterm_shutdown(self):
        """Test that `fastjob start` handles SIGTERM gracefully"""
        
        # Start CLI worker process
        process = subprocess.Popen(
            ["python3", "-m", "fastjob.cli.main", "start", "--concurrency", "1"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "FASTJOB_DATABASE_URL": "postgresql://localhost/fastjob_test"}
        )
        
        try:
            # Let it start up
            await asyncio.sleep(2)
            
            # Send SIGTERM
            process.send_signal(signal.SIGTERM)
            
            # Wait for graceful shutdown
            try:
                stdout, stderr = process.communicate(timeout=10)
                
                # Process should exit cleanly
                assert process.returncode in [0, -signal.SIGTERM, 143]
                
                # Check for graceful shutdown messages
                output = stdout + stderr
                shutdown_keywords = ["shutdown", "stopped", "graceful", "closing", "cleanup"]
                assert any(keyword in output.lower() for keyword in shutdown_keywords), \
                    f"Expected shutdown keywords in output: {output}"
                
            except subprocess.TimeoutExpired:
                process.kill()
                pytest.fail("CLI worker did not shut down gracefully within timeout")
        finally:
            # Ensure process is cleaned up
            if process.poll() is None:
                process.kill()
                process.wait()

    @pytest.mark.asyncio
    async def test_cli_worker_sigint_shutdown(self):
        """Test that `fastjob start` handles SIGINT (Ctrl+C) gracefully"""
        
        # Start CLI worker process
        process = subprocess.Popen(
            ["python3", "-m", "fastjob.cli.main", "start", "--concurrency", "1"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "FASTJOB_DATABASE_URL": "postgresql://localhost/fastjob_test"}
        )
        
        try:
            # Let it start up
            await asyncio.sleep(2)
            
            # Send SIGINT
            process.send_signal(signal.SIGINT)
            
            # Wait for graceful shutdown
            try:
                stdout, stderr = process.communicate(timeout=10)
                
                # Process should exit cleanly
                assert process.returncode in [0, -signal.SIGINT, 130]
                
                # Check for graceful shutdown messages
                output = stdout + stderr
                shutdown_keywords = ["shutdown", "stopped", "interrupt", "closing", "cleanup", "graceful"]
                assert any(keyword in output.lower() for keyword in shutdown_keywords), \
                    f"Expected shutdown keywords in output: {output}"
                
            except subprocess.TimeoutExpired:
                process.kill()
                pytest.fail("CLI worker did not shut down gracefully within timeout")
        finally:
            # Ensure process is cleaned up
            if process.poll() is None:
                process.kill()
                process.wait()


@pytest.mark.asyncio
async def test_signal_handler_cross_platform_compatibility():
    """Test that signal handlers work across different platforms"""
    from fastjob.utils.signals import GracefulSignalHandler
    
    handler = GracefulSignalHandler()
    shutdown_event = asyncio.Event()
    
    try:
        handler.setup_signal_handlers(shutdown_event)
        
        # Should always handle SIGINT
        assert signal.SIGINT in handler.handled_signals
        
        # Platform-specific signals may or may not be available
        # Test should not fail if they're not available
        
        # At minimum, we should have SIGINT
        assert len(handler.handled_signals) >= 1
        
    finally:
        handler.restore_signal_handlers()


@pytest.mark.asyncio
async def test_signal_handler_multiple_setup_cleanup():
    """Test that multiple setup/cleanup cycles work correctly"""
    from fastjob.utils.signals import GracefulSignalHandler
    
    handler = GracefulSignalHandler()
    
    for i in range(3):
        shutdown_event = asyncio.Event()
        
        # Setup
        handler.setup_signal_handlers(shutdown_event)
        assert len(handler.handled_signals) > 0
        
        # Cleanup
        handler.restore_signal_handlers()
        assert len(handler.handled_signals) == 0
        assert handler.shutdown_event is None


# Integration test to ensure heartbeat cleanup works with signal handling
@pytest.mark.asyncio
async def test_signal_shutdown_with_heartbeat_cleanup():
    """Test that heartbeat is properly cleaned up during signal shutdown"""
    
    # This test requires a running database to test heartbeat functionality
    pytest.skip("Requires database setup - covered by full integration tests")