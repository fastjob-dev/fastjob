"""
Test suite for health.py module - comprehensive coverage for production health monitoring.
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastjob.health import (
    HealthStatus,
    HealthCheck,
    HealthMonitor,
    check_database_health,
    check_job_processing_health,
    check_system_resources,
    get_health_status,
    is_healthy,
    is_ready,
    add_health_check,
    setup_default_health_checks,
    start_health_monitoring,
    stop_health_monitoring,
    cli_health_check,
    cli_readiness_check,
    _health_monitor,
)


class MockAsyncContextManager:
    """Proper async context manager for mocking."""
    
    def __init__(self, return_value):
        self.return_value = return_value
    
    async def __aenter__(self):
        return self.return_value
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class MockPool:
    """Mock pool that returns proper async context manager."""
    
    def __init__(self, connection_mock):
        self.connection_mock = connection_mock
    
    def acquire(self):
        return MockAsyncContextManager(self.connection_mock)


class TestHealthStatus:
    """Test HealthStatus enum values."""

    def test_health_status_values(self):
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestHealthCheck:
    """Test HealthCheck component."""

    def test_health_check_initialization(self):
        check_func = AsyncMock()
        check = HealthCheck(
            name="test_check",
            check_func=check_func,
            timeout=10.0,
            critical=False,
            interval=60.0,
        )

        assert check.name == "test_check"
        assert check.check_func == check_func
        assert check.timeout == 10.0
        assert check.critical is False
        assert check.interval == 60.0
        assert check.last_check is None
        assert check.last_status == HealthStatus.UNKNOWN
        assert check.last_message == "Not checked yet"
        assert check.last_duration == 0.0

    def test_health_check_defaults(self):
        check_func = AsyncMock()
        check = HealthCheck(name="test", check_func=check_func)

        assert check.timeout == 5.0
        assert check.critical is True
        assert check.interval == 30.0


class TestHealthMonitor:
    """Test HealthMonitor system."""

    @pytest.fixture
    def monitor(self):
        monitor = HealthMonitor()
        yield monitor
        # Cleanup
        monitor._monitoring = False
        if monitor._monitor_task:
            monitor._monitor_task.cancel()

    async def test_add_check(self, monitor):
        check_func = AsyncMock()
        monitor.add_check(
            name="test_check",
            check_func=check_func,
            timeout=5.0,
            critical=True,
        )

        assert "test_check" in monitor.checks
        check = monitor.checks["test_check"]
        assert check.name == "test_check"
        assert check.check_func == check_func
        assert check.timeout == 5.0
        assert check.critical is True

    async def test_run_check_tuple_result(self, monitor):
        """Test run_check with tuple return value."""
        check_func = AsyncMock(return_value=(HealthStatus.HEALTHY, "All good"))
        check = HealthCheck("test", check_func)

        status, message, duration = await monitor.run_check(check)

        assert status == HealthStatus.HEALTHY
        assert message == "All good"
        assert duration > 0

    async def test_run_check_boolean_result(self, monitor):
        """Test run_check with boolean return value."""
        check_func = AsyncMock(return_value=True)
        check = HealthCheck("test", check_func)

        status, message, duration = await monitor.run_check(check)

        assert status == HealthStatus.HEALTHY
        assert message == "Check passed"
        assert duration > 0

    async def test_run_check_boolean_false_result(self, monitor):
        """Test run_check with boolean False return value."""
        check_func = AsyncMock(return_value=False)
        check = HealthCheck("test", check_func)

        status, message, duration = await monitor.run_check(check)

        assert status == HealthStatus.UNHEALTHY
        assert message == "Check failed"
        assert duration > 0

    async def test_run_check_string_result(self, monitor):
        """Test run_check with string return value."""
        check_func = AsyncMock(return_value="System OK")
        check = HealthCheck("test", check_func)

        status, message, duration = await monitor.run_check(check)

        assert status == HealthStatus.HEALTHY
        assert message == "System OK"
        assert duration > 0

    async def test_run_check_timeout(self, monitor):
        """Test run_check with timeout."""
        async def slow_check():
            await asyncio.sleep(10)
            return True
        
        check = HealthCheck("test", slow_check, timeout=0.1)

        status, message, duration = await monitor.run_check(check)

        assert status == HealthStatus.UNHEALTHY
        assert "timed out" in message
        assert duration >= 0.1

    async def test_run_check_exception(self, monitor):
        """Test run_check with exception."""
        check_func = AsyncMock(side_effect=ValueError("Test error"))
        check = HealthCheck("test", check_func)

        status, message, duration = await monitor.run_check(check)

        assert status == HealthStatus.UNHEALTHY
        assert "Check failed: Test error" in message
        assert duration > 0

    async def test_check_health_all_healthy(self, monitor):
        """Test check_health with all checks healthy."""
        check1 = AsyncMock(return_value=(HealthStatus.HEALTHY, "Check 1 OK"))
        check2 = AsyncMock(return_value=(HealthStatus.HEALTHY, "Check 2 OK"))

        monitor.add_check("check1", check1, critical=True)
        monitor.add_check("check2", check2, critical=False)

        result = await monitor.check_health()

        assert result["status"] == HealthStatus.HEALTHY.value
        assert result["message"] == "All health checks passed"
        assert len(result["checks"]) == 2
        assert result["checks"]["check1"]["status"] == HealthStatus.HEALTHY.value
        assert result["checks"]["check2"]["status"] == HealthStatus.HEALTHY.value

    async def test_check_health_critical_failure(self, monitor):
        """Test check_health with critical failure."""
        check1 = AsyncMock(return_value=(HealthStatus.UNHEALTHY, "Critical failure"))
        check2 = AsyncMock(return_value=(HealthStatus.HEALTHY, "Check 2 OK"))

        monitor.add_check("check1", check1, critical=True)
        monitor.add_check("check2", check2, critical=False)

        result = await monitor.check_health()

        assert result["status"] == HealthStatus.UNHEALTHY.value
        assert "Critical health checks failed: check1" in result["message"]
        assert result["checks"]["check1"]["critical"] is True

    async def test_check_health_non_critical_failure(self, monitor):
        """Test check_health with non-critical failure."""
        check1 = AsyncMock(return_value=(HealthStatus.HEALTHY, "Check 1 OK"))
        check2 = AsyncMock(return_value=(HealthStatus.UNHEALTHY, "Non-critical failure"))

        monitor.add_check("check1", check1, critical=True)
        monitor.add_check("check2", check2, critical=False)

        result = await monitor.check_health()

        assert result["status"] == HealthStatus.DEGRADED.value
        assert result["message"] == "Some non-critical checks failed"

    async def test_check_health_degraded_status(self, monitor):
        """Test check_health with degraded status."""
        check1 = AsyncMock(return_value=(HealthStatus.DEGRADED, "Degraded"))

        monitor.add_check("check1", check1, critical=False)

        result = await monitor.check_health()

        assert result["status"] == HealthStatus.DEGRADED.value

    async def test_check_health_specific_check(self, monitor):
        """Test check_health with specific check name."""
        check1 = AsyncMock(return_value=(HealthStatus.HEALTHY, "Check 1 OK"))
        check2 = AsyncMock(return_value=(HealthStatus.HEALTHY, "Check 2 OK"))

        monitor.add_check("check1", check1)
        monitor.add_check("check2", check2)

        result = await monitor.check_health("check1")

        assert len(result["checks"]) == 1
        assert "check1" in result["checks"]
        assert "check2" not in result["checks"]
        check1.assert_called_once()
        check2.assert_not_called()

    async def test_check_health_nonexistent_check(self, monitor):
        """Test check_health with nonexistent check name."""
        result = await monitor.check_health("nonexistent")

        assert result["status"] == HealthStatus.UNKNOWN.value
        assert "not found" in result["message"]
        assert result["checks"] == {}

    async def test_start_stop_monitoring(self, monitor):
        """Test start and stop monitoring."""
        async def test_check():
            return (HealthStatus.HEALTHY, "OK")
        
        monitor.add_check("test", test_check)

        # Start monitoring
        await monitor.start_monitoring(interval=0.1)
        assert monitor._monitoring is True
        assert monitor._monitor_task is not None

        # Let it run briefly
        await asyncio.sleep(0.2)

        # Stop monitoring
        await monitor.stop_monitoring()
        assert monitor._monitoring is False
        # Task should be None or cancelled after stop
        assert monitor._monitor_task is None or monitor._monitor_task.cancelled()

    async def test_start_monitoring_already_running(self, monitor):
        """Test starting monitoring when already running."""
        async def test_check():
            return (HealthStatus.HEALTHY, "OK")
        
        monitor.add_check("test", test_check)

        await monitor.start_monitoring(interval=0.1)
        first_task = monitor._monitor_task

        # Try to start again
        await monitor.start_monitoring(interval=0.1)
        second_task = monitor._monitor_task

        # Should be the same task
        assert first_task is second_task

        await monitor.stop_monitoring()

    async def test_stop_monitoring_not_running(self, monitor):
        """Test stopping monitoring when not running."""
        # Should not raise exception
        await monitor.stop_monitoring()
        assert monitor._monitoring is False
        assert monitor._monitor_task is None


class TestHealthCheckFunctions:
    """Test individual health check functions."""

    @patch("fastjob.health.get_pool")
    async def test_check_database_health_success(self, mock_get_pool):
        """Test successful database health check."""
        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.fetchval.side_effect = [1, 1, 100]  # Basic check, tables exist, job count
        
        mock_pool = MockPool(mock_conn)
        mock_get_pool.return_value = mock_pool

        status, message = await check_database_health()

        assert status == HealthStatus.HEALTHY
        assert "100 jobs in queue" in message

    @patch("fastjob.health.get_pool")
    async def test_check_database_health_wrong_result(self, mock_get_pool):
        """Test database health check with wrong query result."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = 2  # Wrong result

        mock_pool = MockPool(mock_conn)
        mock_get_pool.return_value = mock_pool

        status, message = await check_database_health()

        assert status == HealthStatus.UNHEALTHY
        assert "unexpected result" in message

    @patch("fastjob.health.get_pool")
    async def test_check_database_health_no_tables(self, mock_get_pool):
        """Test database health check with missing tables."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.side_effect = [1, 0]  # Basic check OK, no tables

        mock_pool = MockPool(mock_conn)
        mock_get_pool.return_value = mock_pool

        status, message = await check_database_health()

        assert status == HealthStatus.UNHEALTHY
        assert "run migrations" in message

    @patch("fastjob.health.get_pool")
    async def test_check_database_health_exception(self, mock_get_pool):
        """Test database health check with exception."""
        mock_get_pool.side_effect = Exception("Connection failed")

        status, message = await check_database_health()

        assert status == HealthStatus.UNHEALTHY
        assert "Connection failed" in message

    @patch("fastjob.health.get_pool")
    async def test_check_job_processing_health_stuck_jobs(self, mock_get_pool):
        """Test job processing health with stuck jobs."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.side_effect = [150, 10, 5, 20]  # stuck, recent, failed, total

        mock_pool = MockPool(mock_conn)
        mock_get_pool.return_value = mock_pool

        status, message = await check_job_processing_health()

        assert status == HealthStatus.DEGRADED
        assert "150 jobs may be stuck" in message

    @patch("fastjob.health.get_pool")
    async def test_check_job_processing_health_high_failure_rate(self, mock_get_pool):
        """Test job processing health with high failure rate."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.side_effect = [50, 10, 15, 20]  # stuck, recent, failed, total

        mock_pool = MockPool(mock_conn)
        mock_get_pool.return_value = mock_pool

        status, message = await check_job_processing_health()

        assert status == HealthStatus.DEGRADED
        assert "High failure rate: 75.0%" in message

    @patch("fastjob.health.get_pool")
    async def test_check_job_processing_health_healthy(self, mock_get_pool):
        """Test healthy job processing."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.side_effect = [10, 50, 2, 20]  # stuck, recent, failed, total

        mock_pool = MockPool(mock_conn)
        mock_get_pool.return_value = mock_pool

        status, message = await check_job_processing_health()

        assert status == HealthStatus.HEALTHY
        assert "50 recent updates" in message

    @patch("fastjob.health.get_pool")
    async def test_check_job_processing_health_exception(self, mock_get_pool):
        """Test job processing health check with exception."""
        mock_get_pool.side_effect = Exception("Database error")

        status, message = await check_job_processing_health()

        assert status == HealthStatus.UNHEALTHY
        assert "Database error" in message

    async def test_check_system_resources_healthy(self):
        """Test healthy system resources."""
        mock_psutil = MagicMock()
        mock_psutil.virtual_memory.return_value = MagicMock(percent=50.0)
        mock_psutil.disk_usage.return_value = MagicMock(percent=60.0)
        mock_psutil.cpu_percent.return_value = 30.0

        with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs: mock_psutil if name == "psutil" else __import__(name, *args, **kwargs)):
            status, message = await check_system_resources()

        assert status == HealthStatus.HEALTHY
        assert "CPU: 30.0%" in message
        assert "Mem: 50.0%" in message
        assert "Disk: 60.0%" in message

    async def test_check_system_resources_high_memory(self):
        """Test high memory usage."""
        mock_psutil = MagicMock()
        mock_psutil.virtual_memory.return_value = MagicMock(percent=95.0)

        with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs: mock_psutil if name == "psutil" else __import__(name, *args, **kwargs)):
            status, message = await check_system_resources()

        assert status == HealthStatus.DEGRADED
        assert "High memory usage: 95.0%" in message

    async def test_check_system_resources_high_disk(self):
        """Test high disk usage."""
        mock_psutil = MagicMock()
        mock_psutil.virtual_memory.return_value = MagicMock(percent=50.0)
        mock_psutil.disk_usage.return_value = MagicMock(percent=95.0)

        with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs: mock_psutil if name == "psutil" else __import__(name, *args, **kwargs)):
            status, message = await check_system_resources()

        assert status == HealthStatus.DEGRADED
        assert "High disk usage: 95.0%" in message

    async def test_check_system_resources_high_cpu(self):
        """Test high CPU usage."""
        mock_psutil = MagicMock()
        mock_psutil.virtual_memory.return_value = MagicMock(percent=50.0)
        mock_psutil.disk_usage.return_value = MagicMock(percent=60.0)
        mock_psutil.cpu_percent.return_value = 98.0

        with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs: mock_psutil if name == "psutil" else __import__(name, *args, **kwargs)):
            status, message = await check_system_resources()

        assert status == HealthStatus.DEGRADED
        assert "High CPU usage: 98.0%" in message

    async def test_check_system_resources_no_psutil(self):
        """Test system resources check without psutil."""
        with patch.dict("sys.modules", {"psutil": None}):
            status, message = await check_system_resources()

        assert status == HealthStatus.UNKNOWN
        assert "psutil not available" in message

    async def test_check_system_resources_exception(self):
        """Test system resources check with exception."""
        mock_psutil = MagicMock()
        mock_psutil.virtual_memory.side_effect = Exception("System error")

        with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs: mock_psutil if name == "psutil" else __import__(name, *args, **kwargs)):
            status, message = await check_system_resources()

        assert status == HealthStatus.UNHEALTHY
        assert "System error" in message


class TestHealthAPIFunctions:
    """Test high-level health API functions."""

    @pytest.fixture(autouse=True)
    def cleanup_global_monitor(self):
        """Clean up global monitor state between tests."""
        _health_monitor.checks.clear()
        _health_monitor._monitoring = False
        if _health_monitor._monitor_task:
            _health_monitor._monitor_task.cancel()
        yield
        _health_monitor.checks.clear()
        _health_monitor._monitoring = False
        if _health_monitor._monitor_task:
            _health_monitor._monitor_task.cancel()

    @patch("fastjob.health.check_database_health")
    @patch("fastjob.health.check_job_processing_health")
    @patch("fastjob.health.check_system_resources")
    async def test_get_health_status_auto_setup(
        self, mock_resources, mock_processing, mock_database
    ):
        """Test get_health_status with automatic setup."""
        mock_database.return_value = (HealthStatus.HEALTHY, "DB OK")
        mock_processing.return_value = (HealthStatus.HEALTHY, "Processing OK")
        mock_resources.return_value = (HealthStatus.HEALTHY, "Resources OK")

        result = await get_health_status()

        assert result["status"] == HealthStatus.HEALTHY.value
        assert len(result["checks"]) == 3
        assert "database" in result["checks"]
        assert "job_processing" in result["checks"]
        assert "system_resources" in result["checks"]

    async def test_add_health_check_api(self):
        """Test add_health_check API function."""
        check_func = AsyncMock(return_value=(HealthStatus.HEALTHY, "Custom OK"))

        add_health_check("custom_check", check_func, timeout=10.0, critical=False)

        assert "custom_check" in _health_monitor.checks
        check = _health_monitor.checks["custom_check"]
        assert check.timeout == 10.0
        assert check.critical is False

    @patch("fastjob.health.get_health_status")
    async def test_is_healthy_true(self, mock_get_health):
        """Test is_healthy returns True for healthy status."""
        mock_get_health.return_value = {"status": "healthy"}

        result = await is_healthy()

        assert result is True

    @patch("fastjob.health.get_health_status")
    async def test_is_healthy_degraded(self, mock_get_health):
        """Test is_healthy returns True for degraded status."""
        mock_get_health.return_value = {"status": "degraded"}

        result = await is_healthy()

        assert result is True

    @patch("fastjob.health.get_health_status")
    async def test_is_healthy_false(self, mock_get_health):
        """Test is_healthy returns False for unhealthy status."""
        mock_get_health.return_value = {"status": "unhealthy"}

        result = await is_healthy()

        assert result is False

    @patch("fastjob.health.get_pool")
    async def test_is_ready_success(self, mock_get_pool):
        """Test is_ready success."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.side_effect = [1, 1]  # Basic check, tables exist

        mock_pool = MockPool(mock_conn)
        mock_get_pool.return_value = mock_pool

        result = await is_ready()

        assert result is True

    @patch("fastjob.health.get_pool")
    async def test_is_ready_no_tables(self, mock_get_pool):
        """Test is_ready with no tables."""
        mock_conn = AsyncMock()
        mock_conn.fetchval.side_effect = [1, 0]  # Basic check OK, no tables

        mock_pool = MockPool(mock_conn)
        mock_get_pool.return_value = mock_pool

        result = await is_ready()

        assert result is False

    @patch("fastjob.health.get_pool")
    async def test_is_ready_exception(self, mock_get_pool):
        """Test is_ready with exception."""
        mock_get_pool.side_effect = Exception("Connection failed")

        result = await is_ready()

        assert result is False

    async def test_start_stop_health_monitoring_api(self):
        """Test start/stop health monitoring API functions."""
        # Mock the health check functions to avoid actual system checks
        with patch("fastjob.health.check_database_health") as mock_db, \
             patch("fastjob.health.check_job_processing_health") as mock_proc, \
             patch("fastjob.health.check_system_resources") as mock_res:
            
            mock_db.return_value = (HealthStatus.HEALTHY, "DB OK")
            mock_proc.return_value = (HealthStatus.HEALTHY, "Proc OK")
            mock_res.return_value = (HealthStatus.HEALTHY, "Res OK")

            await start_health_monitoring(interval=0.1)
            assert _health_monitor._monitoring is True

            # Let it run briefly
            await asyncio.sleep(0.2)

            await stop_health_monitoring()
            assert _health_monitor._monitoring is False


class TestCLIFunctions:
    """Test CLI health check functions."""

    @pytest.fixture(autouse=True)
    def cleanup_global_monitor(self):
        """Clean up global monitor state between tests."""
        _health_monitor.checks.clear()
        _health_monitor._monitoring = False
        if _health_monitor._monitor_task:
            _health_monitor._monitor_task.cancel()
        yield
        _health_monitor.checks.clear()
        _health_monitor._monitoring = False
        if _health_monitor._monitor_task:
            _health_monitor._monitor_task.cancel()

    @patch("fastjob.health.get_health_status")
    @patch("builtins.print")
    async def test_cli_health_check_healthy_verbose(self, mock_print, mock_get_health):
        """Test CLI health check with healthy status and verbose output."""
        mock_get_health.return_value = {
            "status": "healthy",
            "message": "All checks passed",
            "timestamp": "2023-01-01T12:00:00",
            "checks": {
                "database": {
                    "status": "healthy",
                    "message": "DB OK",
                    "duration_ms": 50.0,
                    "critical": True,
                }
            },
        }

        exit_code = await cli_health_check(verbose=True)

        assert exit_code == 0
        # Verify print was called (detailed verification would require mocking the color functions)
        assert mock_print.call_count > 0

    @patch("fastjob.health.get_health_status")
    @patch("builtins.print")
    async def test_cli_health_check_unhealthy(self, mock_print, mock_get_health):
        """Test CLI health check with unhealthy status."""
        mock_get_health.return_value = {
            "status": "unhealthy",
            "message": "Critical failure",
            "timestamp": "2023-01-01T12:00:00",
            "checks": {},
        }

        exit_code = await cli_health_check(verbose=False)

        assert exit_code == 1

    @patch("fastjob.health.get_health_status")
    async def test_cli_health_check_exception(self, mock_get_health):
        """Test CLI health check with exception."""
        mock_get_health.side_effect = Exception("Health check failed")

        exit_code = await cli_health_check()

        assert exit_code == 1

    @patch("fastjob.health.is_ready")
    async def test_cli_readiness_check_ready(self, mock_is_ready):
        """Test CLI readiness check when ready."""
        mock_is_ready.return_value = True

        exit_code = await cli_readiness_check()

        assert exit_code == 0

    @patch("fastjob.health.is_ready")
    async def test_cli_readiness_check_not_ready(self, mock_is_ready):
        """Test CLI readiness check when not ready."""
        mock_is_ready.return_value = False

        exit_code = await cli_readiness_check()

        assert exit_code == 1

    @patch("fastjob.health.is_ready")
    async def test_cli_readiness_check_exception(self, mock_is_ready):
        """Test CLI readiness check with exception."""
        mock_is_ready.side_effect = Exception("Readiness check failed")

        exit_code = await cli_readiness_check()

        assert exit_code == 1


class TestSetupDefaultHealthChecks:
    """Test default health checks setup."""

    @pytest.fixture(autouse=True)
    def cleanup_global_monitor(self):
        """Clean up global monitor state between tests."""
        _health_monitor.checks.clear()
        yield
        _health_monitor.checks.clear()

    def test_setup_default_health_checks(self):
        """Test that default health checks are set up correctly."""
        setup_default_health_checks()

        assert len(_health_monitor.checks) == 3
        assert "database" in _health_monitor.checks
        assert "job_processing" in _health_monitor.checks
        assert "system_resources" in _health_monitor.checks

        # Verify database check is critical
        db_check = _health_monitor.checks["database"]
        assert db_check.critical is True
        assert db_check.timeout == 5.0

        # Verify job processing check is non-critical
        proc_check = _health_monitor.checks["job_processing"]
        assert proc_check.critical is False
        assert proc_check.timeout == 10.0

        # Verify system resources check is non-critical
        res_check = _health_monitor.checks["system_resources"]
        assert res_check.critical is False
        assert res_check.timeout == 3.0